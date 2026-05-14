import uuid
import numpy as np
from datetime import datetime, timedelta
from fastapi import APIRouter, File, UploadFile, HTTPException, Form
from app.cv_utils import get_face_embedding, compare_faces
from app.database import SessionLocal
from app.models import Employee, Card, LivenessSession

router = APIRouter()

SESSION_TTL_MINUTES = 10
MATCHES_NEEDED   = 4     # кадров с совпадением (~2-3 сек)
VARIANCE_NEEDED  = 0.02  # разброс: у вас 0.023 на 4-м кадре; статичное фото <0.01


@router.post("/start_liveness")
def start_liveness(card_uid: str):
    db = SessionLocal()
    try:
        cutoff = datetime.now() - timedelta(minutes=SESSION_TTL_MINUTES)
        db.query(LivenessSession).filter(LivenessSession.timestamp < cutoff).delete()
        db.commit()

        normalized_uid = card_uid.strip()
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
        frame_embedding = get_face_embedding(content)

        face_match = False
        dist = 1.0
        if frame_embedding is not None:
            target_embedding = np.array(sess.embedding_json)
            face_match, dist = compare_faces(target_embedding, frame_embedding)
        else:
            print(f"[FACE] no face in frame (session={session_id[:8]})")

        # ── Variance-based liveness ───────────────────────────────────────────
        # Живое лицо чуть двигается → дистанции скачут (диапазон >0.08).
        # Статичное фото → дистанции одинаковые (диапазон <0.03).
        # Поля last_ear / min_ear_closed переиспользуются как max_dist / min_dist.
        if face_match:
            match_count = (sess.blink_count or 0) + 1
            sess.blink_count = match_count

            cur_max = sess.last_ear if sess.last_ear is not None else dist
            cur_min = sess.min_ear_closed if sess.min_ear_closed is not None else dist
            new_max = max(cur_max, dist)
            new_min = min(cur_min, dist)
            sess.last_ear = new_max
            sess.min_ear_closed = new_min

            variance = new_max - new_min
            print(f"[LIVE] match={match_count}/{MATCHES_NEEDED}  dist={dist:.4f}  range={variance:.4f}/{VARIANCE_NEEDED}")

            if match_count >= MATCHES_NEEDED and variance >= VARIANCE_NEEDED:
                sess.passed = True
                db.commit()
                return {"status": "finished"}

        db.commit()

        match_count = sess.blink_count or 0
        cur_max = sess.last_ear or 0.0
        cur_min = sess.min_ear_closed or 0.0
        variance = (cur_max - cur_min) if match_count > 1 else 0.0

        return {
            "status": "processing",
            "face_found": frame_embedding is not None,
            "face_matched": face_match,
            "match_count": match_count,
        }
    finally:
        db.close()
