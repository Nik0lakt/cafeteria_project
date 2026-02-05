import os, pickle
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models import Employee, Card, Transaction, WorkDay, RoleSetting
from app.cv_utils import get_face_embedding
from pydantic import BaseModel
from datetime import date, timedelta
from typing import List, Optional

router = APIRouter()
PHOTOS_DIR = "/app/static/photos"

class EmployeeCreate(BaseModel):
    full_name: str
    role: str
    card_uid: str
    telegram_id: Optional[str] = None
    month_limit_rub: int

class EmployeeUpdate(BaseModel):
    full_name: str
    role: str
    month_limit_rub: int
    card_uid: str
    telegram_id: Optional[str] = None

class SchedulePreset(BaseModel):
    work_days: int
    rest_days: int

class GlobalAction(BaseModel):
    target_date: date
    action_type: str 
    target_role: str # "ALL" или название конкретной роли

class RoleUpdate(BaseModel):
    role_name: str
    subsidy_rub: float

@router.get("/employees")
def list_employees(db: Session = Depends(get_db)):
    emps = db.query(Employee).all()
    results = []
    for e in emps:
        card = db.query(Card).filter(Card.employee_id == e.id).first()
        used_today_kop = db.query(func.sum(Transaction.subsidy_part_kopecks)).filter(
            Transaction.employee_id == e.id, func.date(Transaction.created_at) == date.today()
        ).scalar() or 0
        results.append({
            "id": e.id, "full_name": e.full_name, "role": e.role,
            "month_limit_rub": e.month_limit_rub, "daily_used": used_today_kop / 100,
            "has_face": e.face_embedding is not None, "card_uid": card.uid if card else "N/A",
            "telegram_id": e.telegram_id
        })
    return results

# --- Управление ролями ---
@router.post("/role_settings")
def add_role(data: RoleUpdate, db: Session = Depends(get_db)):
    if db.query(RoleSetting).filter(RoleSetting.role_name == data.role_name).first():
        raise HTTPException(400, "Role exists")
    db.add(RoleSetting(role_name=data.role_name, subsidy_rub=data.subsidy_rub))
    db.commit()
    return {"status": "success"}

@router.get("/role_settings")
def get_role_settings(db: Session = Depends(get_db)):
    return db.query(RoleSetting).all()

@router.put("/role_settings")
def update_role_setting(data: RoleUpdate, db: Session = Depends(get_db)):
    setting = db.query(RoleSetting).filter(RoleSetting.role_name == data.role_name).first()
    if setting: setting.subsidy_rub = data.subsidy_rub; db.commit()
    return {"status": "success"}

@router.delete("/role_settings/{role_name}")
def delete_role(role_name: str, db: Session = Depends(get_db)):
    role = db.query(RoleSetting).filter(RoleSetting.role_name == role_name).first()
    if not role: raise HTTPException(404, "Role not found")
    db.delete(role)
    db.commit()
    return {"status": "success"}

# --- Глобальное управление днями ---
@router.post("/schedule/global_action")
def global_action(data: GlobalAction, db: Session = Depends(get_db)):
    q = db.query(Employee)
    if data.target_role != "ALL":
        q = q.filter(Employee.role == data.target_role)
    
    for emp in q.all():
        ex = db.query(WorkDay).filter(WorkDay.employee_id == emp.id, WorkDay.date == data.target_date).first()
        if data.action_type == "holiday" and ex: 
            db.delete(ex)
        elif data.action_type == "work" and not ex: 
            db.add(WorkDay(employee_id=emp.id, date=data.target_date))
    db.commit()
    return {"status": "success"}

# --- Остальные роуты без изменений ---
@router.post("/schedule/{emp_id}/reset")
def reset_schedule(emp_id: int, db: Session = Depends(get_db)):
    db.query(WorkDay).filter(WorkDay.employee_id == emp_id).delete()
    db.commit(); return {"status": "success"}

@router.post("/schedule/{emp_id}/preset")
def set_preset(emp_id: int, data: SchedulePreset, db: Session = Depends(get_db)):
    db.query(WorkDay).filter(WorkDay.employee_id == emp_id).delete()
    curr = date.today() + timedelta(days=(7 - date.today().weekday()) % 7)
    end = curr + timedelta(days=365)
    while curr < end:
        for _ in range(data.work_days):
            if curr < end: db.add(WorkDay(employee_id=emp_id, date=curr)); curr += timedelta(days=1)
        curr += timedelta(days=data.rest_days)
    db.commit(); return {"status": "success"}

@router.post("/schedule/{emp_id}/toggle")
def toggle_day(emp_id: int, target_date: date, db: Session = Depends(get_db)):
    ex = db.query(WorkDay).filter(WorkDay.employee_id == emp_id, WorkDay.date == target_date).first()
    if ex: db.delete(ex)
    else: db.add(WorkDay(employee_id=emp_id, date=target_date))
    db.commit(); return {"status": "success"}

@router.get("/schedule/{emp_id}")
def get_schedule(emp_id: int, db: Session = Depends(get_db)):
    days = db.query(WorkDay).filter(WorkDay.employee_id == emp_id).all()
    return [d.date.isoformat() for d in days]

@router.post("/employees")
def create_employee(data: EmployeeCreate, db: Session = Depends(get_db)):
    emp = Employee(full_name=data.full_name, role=data.role, month_limit_rub=data.month_limit_rub, telegram_id=data.telegram_id)
    db.add(emp); db.commit(); db.refresh(emp)
    db.add(Card(uid=data.card_uid.strip(), employee_id=emp.id)); db.commit()
    return {"id": emp.id}

@router.put("/employees/{emp_id}")
def update_employee(emp_id: int, data: EmployeeUpdate, db: Session = Depends(get_db)):
    emp = db.query(Employee).filter(Employee.id == emp_id).first()
    if not emp: raise HTTPException(404, "Not found")
    emp.full_name, emp.role, emp.month_limit_rub, emp.telegram_id = data.full_name, data.role, data.month_limit_rub, data.telegram_id
    card = db.query(Card).filter(Card.employee_id == emp_id).first()
    if card: card.uid = data.card_uid.strip()
    db.commit(); return {"status": "success"}

@router.delete("/employees/{emp_id}")
def delete_employee(emp_id: int, db: Session = Depends(get_db)):
    db.query(Transaction).filter(Transaction.employee_id == emp_id).delete()
    db.query(Card).filter(Card.employee_id == emp_id).delete()
    db.query(WorkDay).filter(WorkDay.employee_id == emp_id).delete()
    db.query(Employee).filter(Employee.id == emp_id).delete()
    db.commit(); return {"status": "success"}

@router.post("/enroll_face")
async def enroll_face(card_uid: str = Form(...), file: UploadFile = File(...), db: Session = Depends(get_db)):
    content = await file.read()
    os.makedirs(PHOTOS_DIR, exist_ok=True)
    with open(os.path.join(PHOTOS_DIR, f"{card_uid.strip()}.jpg"), "wb") as f: f.write(content)
    emb = get_face_embedding(content)
    if emb is None: raise HTTPException(400, "No face")
    card = db.query(Card).filter(Card.uid == card_uid.strip()).first()
    emp = db.query(Employee).filter(Employee.id == card.employee_id).first()
    emp.face_embedding = pickle.dumps(emb); db.commit()
    return {"status": "success"}

@router.get("/employee_info")
def get_info(card_uid: str, db: Session = Depends(get_db)):
    card = db.query(Card).filter(Card.uid == card_uid.strip()).first()
    if not card: raise HTTPException(404, "Not found")
    emp = db.query(Employee).filter(Employee.id == card.employee_id).first()
    return {"name": emp.full_name, "role": emp.role, "has_face": emp.face_embedding is not None}
