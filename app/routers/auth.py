import os
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import PRIVATE_PHOTOS_DIR
from app.cv_utils import get_face_embedding
from app.database import get_db
from app.models import AppSetting, Card, Employee, LivenessSession, RoleSetting, Transaction, WorkDay
from app.security import (
    ALGORITHM,
    SECRET_KEY,
    create_access_token,
    get_current_admin,
    get_current_terminal,
    verify_password,
)

router = APIRouter()
PHOTOS_DIR = PRIVATE_PHOTOS_DIR


class LoginRequest(BaseModel):
    password: str


class EmployeeCreate(BaseModel):
    full_name: str
    role: str
    card_uid: str
    telegram_id: Optional[str] = None
    month_limit_rub: int
    limit_reset_day: int = 28


class EmployeeUpdate(BaseModel):
    full_name: str
    role: str
    month_limit_rub: int
    card_uid: str
    telegram_id: Optional[str] = None
    limit_reset_day: int = 28


class SchedulePreset(BaseModel):
    work_days: int
    rest_days: int


class GlobalAction(BaseModel):
    target_date: date
    action_type: str
    target_role: str


class RoleUpdate(BaseModel):
    role_name: str
    subsidy_rub: float


# --- АВТОРИЗАЦИЯ (без JWT-зависимости) ---
@router.post("/login")
async def login(data: LoginRequest = Body(...)):
    admin_hash = os.getenv("ADMIN_PASSWORD_HASH", "")
    if not admin_hash or not verify_password(data.password, admin_hash):
        return {"success": False}
    token = create_access_token({"sub": "admin", "role": "admin"})
    return {"success": True, "token": token}


# --- СОТРУДНИКИ ---
@router.get("/employees", dependencies=[Depends(get_current_admin)])
def list_employees(db: Session = Depends(get_db)):
    emps = db.query(Employee).all()
    results = []
    for e in emps:
        card = db.query(Card).filter(Card.employee_id == e.id).first()
        used_today_kop = db.query(func.sum(Transaction.subsidy_part_kopecks)).filter(
            Transaction.employee_id == e.id,
            func.date(Transaction.created_at) == date.today()
        ).scalar() or 0
        results.append({
            "id": e.id,
            "full_name": e.full_name,
            "role": e.role,
            "month_limit_rub": e.month_limit_kopecks / 100,
            "daily_used": used_today_kop / 100,
            "has_face": e.face_embedding_json is not None,
            "card_uid": card.uid if card else "N/A",
            "telegram_id": e.telegram_id,
            "limit_reset_day": e.limit_reset_day if e.limit_reset_day is not None else 28,
        })
    return results


@router.post("/employees", dependencies=[Depends(get_current_admin)])
def create_employee(data: EmployeeCreate, db: Session = Depends(get_db)):
    if not data.full_name.strip():
        raise HTTPException(status_code=400, detail="Полное имя не может быть пустым")
    if not data.card_uid.strip():
        raise HTTPException(status_code=400, detail="UID карты не может быть пустым")
    emp = Employee(
        full_name=data.full_name,
        role=data.role,
        month_limit_kopecks=data.month_limit_rub * 100,
        telegram_id=data.telegram_id,
        limit_reset_day=data.limit_reset_day,
    )
    db.add(emp)
    db.commit()
    db.refresh(emp)
    db.add(Card(uid=data.card_uid.strip(), employee_id=emp.id))
    db.commit()
    return {"id": emp.id}


@router.put("/employees/{emp_id}", dependencies=[Depends(get_current_admin)])
def update_employee(emp_id: int, data: EmployeeUpdate, db: Session = Depends(get_db)):
    emp = db.query(Employee).filter(Employee.id == emp_id).first()
    if not emp:
        raise HTTPException(404, "Not found")
    emp.full_name = data.full_name
    emp.role = data.role
    emp.month_limit_kopecks = data.month_limit_rub * 100
    emp.telegram_id = data.telegram_id
    emp.limit_reset_day = data.limit_reset_day
    card = db.query(Card).filter(Card.employee_id == emp_id).first()
    if card:
        card.uid = data.card_uid.strip()
    db.commit()
    return {"status": "success"}


@router.delete("/employees/{emp_id}", dependencies=[Depends(get_current_admin)])
def delete_employee(emp_id: int, db: Session = Depends(get_db)):
    db.query(Transaction).filter(Transaction.employee_id == emp_id).delete()
    db.query(Card).filter(Card.employee_id == emp_id).delete()
    db.query(WorkDay).filter(WorkDay.employee_id == emp_id).delete()
    db.query(Employee).filter(Employee.id == emp_id).delete()
    db.commit()
    return {"status": "success"}


# --- РОЛИ ---
@router.post("/role_settings", dependencies=[Depends(get_current_admin)])
def add_role(data: RoleUpdate, db: Session = Depends(get_db)):
    if db.query(RoleSetting).filter(RoleSetting.role_name == data.role_name).first():
        raise HTTPException(400, "Role exists")
    db.add(RoleSetting(role_name=data.role_name, subsidy_rub=data.subsidy_rub))
    db.commit()
    return {"status": "success"}


@router.get("/role_settings", dependencies=[Depends(get_current_admin)])
def get_role_settings(db: Session = Depends(get_db)):
    return db.query(RoleSetting).all()


@router.put("/role_settings", dependencies=[Depends(get_current_admin)])
def update_role_setting(data: RoleUpdate, db: Session = Depends(get_db)):
    setting = db.query(RoleSetting).filter(RoleSetting.role_name == data.role_name).first()
    if setting:
        setting.subsidy_rub = data.subsidy_rub
        db.commit()
    return {"status": "success"}


@router.delete("/role_settings/{role_name}", dependencies=[Depends(get_current_admin)])
def delete_role(role_name: str, db: Session = Depends(get_db)):
    role = db.query(RoleSetting).filter(RoleSetting.role_name == role_name).first()
    if not role:
        raise HTTPException(404, "Role not found")
    db.delete(role)
    db.commit()
    return {"status": "success"}


# --- РАСПИСАНИЕ ---
@router.post("/schedule/global_action", dependencies=[Depends(get_current_admin)])
def global_action(data: GlobalAction, db: Session = Depends(get_db)):
    q = db.query(Employee)
    if data.target_role != "ALL":
        q = q.filter(Employee.role == data.target_role)
    for emp in q.all():
        ex = db.query(WorkDay).filter(
            WorkDay.employee_id == emp.id, WorkDay.date == data.target_date
        ).first()
        if data.action_type == "holiday" and ex:
            db.delete(ex)
        elif data.action_type == "work" and not ex:
            db.add(WorkDay(employee_id=emp.id, date=data.target_date))
    db.commit()
    return {"status": "success"}


@router.post("/schedule/{emp_id}/reset", dependencies=[Depends(get_current_admin)])
def reset_schedule(emp_id: int, db: Session = Depends(get_db)):
    db.query(WorkDay).filter(WorkDay.employee_id == emp_id).delete()
    db.commit()
    return {"status": "success"}


@router.post("/schedule/{emp_id}/preset", dependencies=[Depends(get_current_admin)])
def set_preset(emp_id: int, data: SchedulePreset, db: Session = Depends(get_db)):
    db.query(WorkDay).filter(WorkDay.employee_id == emp_id).delete()
    curr = date.today() + timedelta(days=(7 - date.today().weekday()) % 7)
    end = curr + timedelta(days=365)
    while curr < end:
        for _ in range(data.work_days):
            if curr < end:
                db.add(WorkDay(employee_id=emp_id, date=curr))
                curr += timedelta(days=1)
        curr += timedelta(days=data.rest_days)
    db.commit()
    return {"status": "success"}


@router.post("/schedule/{emp_id}/toggle", dependencies=[Depends(get_current_admin)])
def toggle_day(emp_id: int, target_date: date, db: Session = Depends(get_db)):
    ex = db.query(WorkDay).filter(
        WorkDay.employee_id == emp_id, WorkDay.date == target_date
    ).first()
    if ex:
        db.delete(ex)
    else:
        db.add(WorkDay(employee_id=emp_id, date=target_date))
    db.commit()
    return {"status": "success"}


@router.get("/schedule/{emp_id}", dependencies=[Depends(get_current_admin)])
def get_schedule(emp_id: int, db: Session = Depends(get_db)):
    days = db.query(WorkDay).filter(WorkDay.employee_id == emp_id).all()
    return [d.date.isoformat() for d in days]


# --- БИОМЕТРИЯ (без pickle) ---
@router.post("/enroll_face", dependencies=[Depends(get_current_admin)])
async def enroll_face(
    card_uid: str = Form(...), file: UploadFile = File(...), db: Session = Depends(get_db)
):
    content = await file.read()
    os.makedirs(PHOTOS_DIR, exist_ok=True)
    with open(os.path.join(PHOTOS_DIR, f"{card_uid.strip()}.jpg"), "wb") as f:
        f.write(content)
    emb = get_face_embedding(content)
    if emb is None:
        raise HTTPException(400, "No face detected")
    card = db.query(Card).filter(Card.uid == card_uid.strip()).first()
    if not card:
        raise HTTPException(404, "Card not found")
    emp = db.query(Employee).filter(Employee.id == card.employee_id).first()
    emp.face_embedding_json = emb.tolist()
    db.commit()
    return {"status": "success"}


@router.get("/employee_info")
def get_info(
    card_uid: str,
    terminal: dict = Depends(get_current_terminal),
    db: Session = Depends(get_db),
):
    card = db.query(Card).filter(Card.uid == card_uid.strip()).first()
    if not card:
        raise HTTPException(404, "Not found")
    emp = db.query(Employee).filter(Employee.id == card.employee_id).first()
    return {
        "name": emp.full_name,
        "role": emp.role,
        "has_face": emp.face_embedding_json is not None,
    }


@router.get("/photos/{filename}")
def get_photo(
    filename: str,
    token: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Отдаёт фото из private_photos.
    Доступ: admin JWT (token=) ИЛИ валидная liveness-сессия совпадающая по card_uid (session_id=).
    """
    authorized = False

    # Вариант 1: admin JWT
    if token:
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            authorized = payload.get("sub") is not None and payload.get("role") == "admin"
        except JWTError:
            pass

    # Вариант 2: сессия — для терминала оплаты (session_id совпадает с uid файла)
    if not authorized and session_id:
        sess = db.query(LivenessSession).filter(LivenessSession.id == session_id).first()
        if sess:
            uid_from_file = filename.replace(".jpg", "").strip()
            authorized = sess.card_uid.strip() == uid_from_file

    if not authorized:
        raise HTTPException(status_code=403, detail="Unauthorized")

    path = PHOTOS_DIR / filename
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Photo not found")
    return FileResponse(path, media_type="image/jpeg")


# ── App Settings ──────────────────────────────────────────────────────────────

class AppSettingUpdate(BaseModel):
    value: str


@router.get("/app_settings")
def get_app_settings(db: Session = Depends(get_db)):
    """Публичный эндпоинт — возвращает глобальные настройки системы."""
    settings = db.query(AppSetting).all()
    return {s.key: s.value for s in settings}


@router.put("/app_settings/{key}", dependencies=[Depends(get_current_admin)])
def update_app_setting(key: str, data: AppSettingUpdate, db: Session = Depends(get_db)):
    setting = db.query(AppSetting).filter(AppSetting.key == key).first()
    if setting:
        setting.value = data.value
    else:
        db.add(AppSetting(key=key, value=data.value))
    db.commit()
    return {"key": key, "value": data.value}
