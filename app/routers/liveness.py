import uuid
import numpy as np
from datetime import datetime
from fastapi import APIRouter, File, UploadFile, HTTPException, Form
from app.cv_utils import get_face_embedding, compare_faces
from app.database import SessionLocal
from app.models import Employee, Card, LivenessSession

router = APIRouter()

LIVENESS_SESSIONS = {}


@router.post("/start_liveness")
def start_liveness(card_uid: str):
    session_id = str(uuid.uuid4())

    normalized_uid = card_uid.strip()

    LIVENESS_SESSIONS[session_id] = {
        "uid": normalized_uid,
        "passed": False,
        "frames_processed": 0,
    }

    db = SessionLocal()
    try:
        db_session = LivenessSession(
            id=session_id,
            card_uid=normalized_uid,
            timestamp=datetime.now(),
        )
        db.add(db_session)
        db.commit()
    except Exception as e:
        print(f"ERROR: Failed to save session to DB: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error")
    finally:
        db.close()

    return {"session_id": session_id}


@router.post("/liveness_frame")
async def liveness_frame(session_id: str = Form(...), file: UploadFile = File(...)):
    if session_id not in LIVENESS_SESSIONS:
        raise HTTPException(status_code=404, detail="Session not found in RAM")

    sess = LIVENESS_SESSIONS[session_id]

    if sess["passed"]:
        return {"status": "finished"}

    db = SessionLocal()
    try:
        card = db.query(Card).filter(Card.uid == sess["uid"]).first()
        if not card:
            raise HTTPException(status_code=404, detail="Card not found in DB")

        emp = db.query(Employee).filter(Employee.id == card.employee_id).first()
        if not emp or not emp.face_embedding_json:
            raise HTTPException(status_code=400, detail="No face enrolled")

        content = await file.read()
        frame_embedding = get_face_embedding(content)

        if frame_embedding is not None:
            target_embedding = np.array(emp.face_embedding_json)
            if compare_faces(target_embedding, frame_embedding):
                sess["passed"] = True
                db.query(LivenessSession).filter(
                    LivenessSession.id == session_id
                ).update({"passed": True})
                db.commit()
                return {"status": "finished"}

        sess["frames_processed"] += 1
        return {"status": "processing"}
    finally:
        db.close()
