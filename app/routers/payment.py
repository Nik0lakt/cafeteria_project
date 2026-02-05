import os
import urllib.request, json, base64, os
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models import Employee, Card, Transaction, WorkDay, RoleSetting
from app.routers.liveness import LIVENESS_SESSIONS
from pydantic import BaseModel
from datetime import date
from typing import List, Optional

router = APIRouter()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
print(f"--- DEBUG: TOKEN LOADED: {bool(TELEGRAM_BOT_TOKEN)}", flush=True)
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID") 

class OrderItem(BaseModel):
    name: str
    price: int

class PaymentRequest(BaseModel):
    session_id: str
    amount_rub: int
    items: Optional[List[OrderItem]] = []
    is_manual: bool = False
    live_frame_base64: Optional[str] = None

def send_tg_msg(chat_id, text):
    if not chat_id: return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    try: urllib.request.urlopen(req, timeout=5)
    except: pass

def send_tg_report(chat_id, db_photo_path, live_photo_b64, caption):
    if not chat_id: return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMediaGroup"
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    media = [{"type": "photo", "media": "attach://p1", "caption": caption, "parse_mode": "HTML"}, {"type": "photo", "media": "attach://p2"}]
    live_bytes = base64.b64decode(live_photo_b64.split(",")[1])
    with open(db_photo_path, "rb") as f: db_bytes = f.read()
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n',
        f'--{boundary}\r\nContent-Disposition: form-data; name="media"\r\n\r\n{json.dumps(media)}\r\n',
        f'--{boundary}\r\nContent-Disposition: form-data; name="p1"; filename="1.jpg"\r\nContent-Type: image/jpeg\r\n\r\n'.encode('ascii'),
        db_bytes, b'\r\n',
        f'--{boundary}\r\nContent-Disposition: form-data; name="p2"; filename="2.jpg"\r\nContent-Type: image/jpeg\r\n\r\n'.encode('ascii'),
        live_bytes, f'\r\n--{boundary}--\r\n'.encode('ascii')
    ]
    body = b''.join([p if isinstance(p, bytes) else p.encode('utf-8') for p in parts])
    req = urllib.request.Request(url, data=body, headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})
    try: urllib.request.urlopen(req, timeout=15)
    except: pass

@router.post("/pay")
def pay(data: PaymentRequest, db: Session = Depends(get_db)):
    sess = LIVENESS_SESSIONS.get(data.session_id)
    if not sess: raise HTTPException(404, "Session not found")
    card = db.query(Card).filter(Card.uid == sess["uid"]).first()
    emp = db.query(Employee).filter(Employee.id == card.employee_id).first()

    is_work_day = db.query(WorkDay).filter(WorkDay.employee_id == emp.id, WorkDay.date == date.today()).first() is not None
    role_set = db.query(RoleSetting).filter(RoleSetting.role_name == emp.role).first()
    subsidy_limit_kop = (role_set.subsidy_rub * 100) if (role_set and is_work_day) else 0

    total_bill_kop = data.amount_rub * 100
    applied_subsidy_kop = 0
    
    if subsidy_limit_kop > 0:
        used_today_kop = db.query(func.sum(Transaction.subsidy_part_kopecks)).filter(Transaction.employee_id == emp.id, func.date(Transaction.created_at) == date.today()).scalar() or 0
        available_subsidy_kop = max(0, subsidy_limit_kop - used_today_kop)
        applied_subsidy_kop = min(total_bill_kop, available_subsidy_kop)

    withdraw_rub = (total_bill_kop - applied_subsidy_kop) / 100

    # ПРОВЕРКА НА ОСТАТОК СРЕДСТВ
    if emp.month_limit_rub < withdraw_rub:
        raise HTTPException(status_code=400, detail="Недостаточно средств на лимите")

    emp.month_limit_rub -= withdraw_rub
    db.add(Transaction(employee_id=emp.id, amount_total_kopecks=total_bill_kop, subsidy_part_kopecks=int(applied_subsidy_kop), limit_part_kopecks=int(total_bill_kop - applied_subsidy_kop), status="COMPLETED"))
    db.commit()

    counts = {}
    for i in data.items:
        if i.name not in counts: counts[i.name] = {"c": 0, "p": i.price}
        counts[i.name]["c"] += 1
    items_html = "".join([f"• {n}{f' ({v[chr(99)]} шт.)' if v[chr(99)]>1 else ''} — {v['p']*v[chr(99)]} руб.\n" for n,v in counts.items()])

    user_receipt = (
        f"✅ <b>Оплата успешно проведена</b>\n"
        f"👤 {emp.full_name}\n\n"
        f"🛒 <b>Состав заказа:</b>\n{items_html}\n"
        f"💵 Сумма: {data.amount_rub} руб.\n"
        f"🎁 Дотация: {applied_subsidy_kop/100} руб.\n"
        f"💳 С лимита: {withdraw_rub} руб.\n"
        f"💰 <b>Остаток: {round(emp.month_limit_rub, 2)} руб.</b>"
    )
    send_tg_msg(emp.telegram_id, user_receipt)

    if data.is_manual and data.live_frame_base64:
        db_photo = f"/app/static/photos/{sess['uid']}.jpg"
        if os.path.exists(db_photo):
            caption = (
                f"⚠️ <b>ВНИМАНИЕ: РУЧНАЯ ОПЛАТА</b>\n"
                f"━━━━━━━━━━━━━━━\n"
                f"👤 <b>{emp.full_name}</b>\n"
                f"💵 Сумма: {data.amount_rub} руб.\n"
                f"🎁 Дотация: {applied_subsidy_kop/100} руб.\n"
                f"🛒 <b>Заказ:</b>\n{items_html}\n"
                f"📍 Статус: Подтверждено кассиром"
            )
            send_tg_report(ADMIN_CHAT_ID, db_photo, data.live_frame_base64, caption)

    LIVENESS_SESSIONS.pop(data.session_id, None)
    return {"status": "success", "remaining_limit": round(emp.month_limit_rub, 2)}
