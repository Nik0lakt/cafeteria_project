import uuid
import numpy as np
from datetime import datetime, timedelta
from fastapi import APIRouter, File, UploadFile, HTTPException, Form
from app.cv_utils import get_face_embedding_and_ear, compare_faces, EAR_CLOSE_THRESHOLD, EAR_OPEN_THRESHOLD, EAR_MIN_BLINK
from app.database import SessionLocal
from app.models import Employee, Card, LivenessSession

router = APIRouter()

SESSION_TTL_MINUTES = 10


@router.post("/start_liveness")
def start_liveness(card_uid: str):
    db = SessionLocal()
    try:
        # Удаляем протухшие сессии (Fix 4: auto-cleanup)
        cutoff = datetime.now() - timedelta(minutes=SESSION_TTL_MINUTES)
        db.query(LivenessSession).filter(LivenessSession.timestamp < cutoff).delete()
        db.commit()

        normalized_uid = card_uid.strip()

        # Загружаем embedding один раз здесь (Fix 3: cache)
        card = db.query(Card).filter(Card.uid == normalized_uid).first()
        if not card:
            raise HTTPException(status_code=404, detail="Card not found")
        emp = db.query(Employee).filter(Employee.id == card.employee_id).first()
        if not emp or not emp.face_embedding_json:
            raise HTTPException(status_code=400, detail="No face enrolled")

        session_id = str(uuid.uuid4())
        db.add(LivenessSession(
            id=session_id,
            card_uid=normalized_uid,
            timestamp=datetime.now(),
            passed=False,
            embedding_json=emp.face_embedding_json,
        ))
        db.commit()
        return {"session_id": session_id}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"ERROR start_liveness: {e}")
        raise HTTPException(status_code=500, detail="Database error")
    finally:
        db.close()


@router.post("/liveness_frame")
async def liveness_frame(session_id: str = Form(...), file: UploadFile = File(...)):
    # Fix 2: читаем только из БД — никакого RAM-словаря
    db = SessionLocal()
    try:
        sess = db.query(LivenessSession).filter(LivenessSession.id == session_id).first()
        if not sess:
            raise HTTPException(status_code=404, detail="Session not found")
        if sess.passed:
            return {"status": "finished"}
        if not sess.embedding_json:
            raise HTTPException(status_code=400, detail="No face enrolled")

        content = await file.read()
        frame_embedding, ear = get_face_embedding_and_ear(content)

        # Face match check
        face_match = False
        if frame_embedding is not None:
            target_embedding = np.array(sess.embedding_json)
            face_match = compare_faces(target_embedding, frame_embedding)

        # EAR blink tracking: open→close→open = 1 blink, засчитывается только если min EAR < EAR_MIN_BLINK
        if ear is not None:
            print(f"[EAR] ear={ear:.4f}  closed={sess.eye_closed}  min_closed={sess.min_ear_closed}  blinks={sess.blink_count}")
            if not sess.eye_closed and ear < EAR_CLOSE_THRESHOLD:
                # Начало фазы закрытия
                sess.eye_closed = True
                sess.min_ear_closed = ear
            elif sess.eye_closed:
                # Обновляем минимум пока глаз закрыт
                if ear < (sess.min_ear_closed or ear):
                    sess.min_ear_closed = ear
                if ear > EAR_OPEN_THRESHOLD:
                    # Глаз открылся — проверяем глубину закрытия
                    min_reached = sess.min_ear_closed or 1.0
                    if min_reached < EAR_MIN_BLINK:
                        sess.blink_count = (sess.blink_count or 0) + 1
                        print(f"[BLINK] засчитано #{sess.blink_count}, min_ear={min_reached:.4f}")
                    else:
                        print(f"[BLINK] отклонено (неглубокое), min_ear={min_reached:.4f}")
                    sess.eye_closed = False
                    sess.min_ear_closed = None
            sess.last_ear = ear

        if face_match and sess.blink_count >= 2:
            sess.passed = True
            db.commit()
            return {"status": "finished"}

        db.commit()
        return {
            "status": "processing",
            "face_found": frame_embedding is not None,
            "blink_count": sess.blink_count or 0,
        }
    finally:
        db.close()
