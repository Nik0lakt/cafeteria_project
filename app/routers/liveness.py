import uuid
import numpy as np
from datetime import datetime, timedelta
from fastapi import APIRouter, File, UploadFile, HTTPException, Form
from app.cv_utils import get_face_embedding_and_ear, compare_faces, EAR_CLOSE_THRESHOLD, EAR_OPEN_THRESHOLD, EAR_MIN_BLINK
from app.database import SessionLocal
from app.models import Employee, Card, LivenessSession

router = APIRouter()

SESSION_TTL_MINUTES = 10
FACE_MATCHES_NEEDED = 3   # кадров с совпадением лица для подтверждения личности
BLINKS_NEEDED       = 1   # моргание для подтверждения живого человека


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
        frame_embedding, ear = get_face_embedding_and_ear(content)

        # ── Совпадение лица ───────────────────────────────────────────────────
        face_match = False
        if frame_embedding is not None:
            target_embedding = np.array(sess.embedding_json)
            face_match = compare_faces(target_embedding, frame_embedding)
        else:
            print(f"[FACE] no face in frame (session={session_id[:8]})")

        # Накапливаем совпадения в blink_count (временно), используем last_ear как face_match_count
        face_match_count = int(sess.last_ear or 0)
        if face_match:
            face_match_count += 1
            sess.last_ear = float(face_match_count)
            print(f"[MATCH] face confirmed {face_match_count}/{FACE_MATCHES_NEEDED}")

        face_confirmed = face_match_count >= FACE_MATCHES_NEEDED

        # ── EAR бликинг: open → close → open = 1 моргание ────────────────────
        blink_count = sess.blink_count or 0
        if ear is not None:
            print(f"[EAR] ear={ear:.4f}  closed={sess.eye_closed}  min={sess.min_ear_closed}  blinks={blink_count}")
            if not sess.eye_closed and ear < EAR_CLOSE_THRESHOLD:
                sess.eye_closed = True
                sess.min_ear_closed = ear
            elif sess.eye_closed:
                if ear < (sess.min_ear_closed or ear):
                    sess.min_ear_closed = ear
                if ear > EAR_OPEN_THRESHOLD:
                    min_reached = sess.min_ear_closed or 1.0
                    if min_reached < EAR_MIN_BLINK:
                        blink_count += 1
                        sess.blink_count = blink_count
                        print(f"[BLINK] засчитано #{blink_count}, min_ear={min_reached:.4f}")
                    else:
                        print(f"[BLINK] слишком мелкое, min_ear={min_reached:.4f} (нужно < {EAR_MIN_BLINK})")
                    sess.eye_closed = False
                    sess.min_ear_closed = None

        # ── Условие прохождения: личность + живой человек ────────────────────
        if face_confirmed and blink_count >= BLINKS_NEEDED:
            sess.passed = True
            db.commit()
            return {"status": "finished"}

        db.commit()
        return {
            "status": "processing",
            "face_found": frame_embedding is not None,
            "face_confirmed": face_confirmed,
            "blink_count": blink_count,
        }
    finally:
        db.close()
