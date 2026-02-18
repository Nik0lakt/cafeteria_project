from fastapi import APIRouter, File, UploadFile, HTTPException, Form
import uuid
import pickle
from datetime import datetime
from app.cv_utils import get_face_embedding, compare_faces
from app.database import SessionLocal
from app.models import Employee, Card, LivenessSession  # Добавили LivenessSession

router = APIRouter()

# Оставляем словарь для обработки кадров (чтобы не менять структуру БД прямо сейчас)
LIVENESS_SESSIONS = {}

@router.post("/start_liveness")
def start_liveness(card_uid: str):
    session_id = str(uuid.uuid4())
    
    # 1. Сохраняем в память (для работы проверки лица)
    LIVENESS_SESSIONS[session_id] = {
        "uid": card_uid.strip(),
        "passed": False,
        "frames_processed": 0
    }

    # 2. ФИКС: Сохраняем в Базу Данных (чтобы оплата увидела сессию)
    db = SessionLocal()
    try:
        # Создаем запись, которую ждет payment.py
        db_session = LivenessSession(
            id=session_id,
            card_uid=card_uid.strip(),
            timestamp=datetime.now()
        )
        db.add(db_session)
        db.commit()
        print(f"DEBUG: Session {session_id} created in DB for {card_uid}")
    except Exception as e:
        print(f"ERROR: Failed to save session to DB: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error")
    finally:
        db.close()

    return {"session_id": session_id}

@router.post("/liveness_frame")
async def liveness_frame(session_id: str = Form(...), file: UploadFile = File(...)):
    # Проверка в памяти работает быстрее для потока видео
    if session_id not in LIVENESS_SESSIONS:
        raise HTTPException(status_code=404, detail="Session not found in RAM")

    sess = LIVENESS_SESSIONS[session_id]
    
    # Если лицо уже подтверждено, не грузим БД лишний раз
    if sess["passed"]:
        return {"status": "finished"}

    db = SessionLocal()
    try:
        card = db.query(Card).filter(Card.uid == sess["uid"]).first()
        if not card:
            raise HTTPException(status_code=404, detail="Card not found in DB")

        emp = db.query(Employee).filter(Employee.id == card.employee_id).first()
        if not emp or not emp.face_embedding:
            raise HTTPException(status_code=400, detail="No face enrolled")

        content = await file.read()
        frame_embedding = get_face_embedding(content)

        if frame_embedding is not None:
            target_embedding = pickle.loads(emp.face_embedding)
            if compare_faces(target_embedding, frame_embedding):
                sess["passed"] = True
                return {"status": "finished"}

        sess["frames_processed"] += 1
        return {"status": "processing"}
    finally:
        db.close()
