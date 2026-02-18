import os
import urllib.request, json, base64
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models import Employee, Card, Transaction, WorkDay, RoleSetting, LivenessSession
from pydantic import BaseModel
from datetime import date, datetime, time # Импортируем время
from typing import List, Optional

router = APIRouter()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
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

# ... (функции send_tg_msg и send_tg_report остаются без изменений) ...
def send_tg_msg(chat_id, text):
    if not chat_id or not TELEGRAM_BOT_TOKEN: return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    try: urllib.request.urlopen(req, timeout=5)
    except: pass

def send_tg_report(chat_id, db_photo_path, live_photo_b64, caption):
    if not chat_id or not TELEGRAM_BOT_TOKEN: return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMediaGroup"
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    try:
        live_bytes = base64.b64decode(live_photo_b64.split(",")[1])
        with open(db_photo_path, "rb") as f: db_bytes = f.read()
    except: return
    media = [{"type": "photo", "media": "attach://p1", "caption": caption, "parse_mode": "HTML"}, {"type": "photo", "media": "attach://p2"}]
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
    sess = db.query(LivenessSession).filter(LivenessSession.id == data.session_id).first()
    if not sess: raise HTTPException(404, "Сессия не найдена")

    card = db.query(Card).filter(Card.uid == sess.card_uid).first()
    emp = db.query(Employee).filter(Employee.id == card.employee_id).first()

    # 1. Считаем лимит дотации для должности
    is_work_day = db.query(WorkDay).filter(WorkDay.employee_id == emp.id, WorkDay.date == date.today()).first() is not None
    role_set = db.query(RoleSetting).filter(RoleSetting.role_name == emp.role).first()
    daily_subsidy_limit_kop = float(role_set.subsidy_rub * 100) if (role_set and is_work_day) else 0.0

    total_bill_kop = float(data.amount_rub * 100)
    applied_subsidy_kop = 0.0

    if daily_subsidy_limit_kop > 0:
        # 2. ФИКС: Считаем сумму потраченного строго с начала текущих суток
        start_of_today = datetime.combine(date.today(), time.min)
        
        raw_used = db.query(func.sum(Transaction.subsidy_part_kopecks)).filter(
            Transaction.employee_id == emp.id,
            Transaction.created_at >= start_of_today
        ).scalar()
        
        used_today_kop = float(raw_used) if raw_used is not None else 0.0
        
        # 3. Вычисляем доступный остаток дотации
        available_today_kop = max(0.0, daily_subsidy_limit_kop - used_today_kop)
        applied_subsidy_kop = min(total_bill_kop, available_today_kop)

    withdraw_rub = (total_bill_kop - applied_subsidy_kop) / 100.0

    if emp.month_limit_rub < withdraw_rub:
        raise HTTPException(status_code=400, detail="Недостаточно личных средств")

    # 4. Сохраняем транзакцию с ЯВНЫМ указанием времени
    new_tx = Transaction(
        employee_id=emp.id,
        amount_total_kopecks=int(total_bill_kop),
        subsidy_part_kopecks=int(applied_subsidy_kop),
        limit_part_kopecks=int(total_bill_kop - applied_subsidy_kop),
        status="COMPLETED",
        created_at=datetime.now() # Явно ставим время сервера
    )
    
    emp.month_limit_rub -= withdraw_rub
    db.add(new_tx)
    db.delete(sess)
    db.commit()

    # --- АГРЕГАЦИЯ ТОВАРОВ ---
    counts = {}
    for i in data.items:
        if i.name not in counts: counts[i.name] = {"qty": 0, "price": i.price}
        counts[i.name]["qty"] += 1
    
    items_html = ""
    for name, v in counts.items():
        qty = v["qty"]
        items_html += f"• {name}{f' ({qty} шт.)' if qty > 1 else ''} — {v['price'] * qty} руб.\n"

    # --- ЧЕК ---
    user_receipt = (
        f"💳 <b>Оплата принята</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🛒 <b>Состав заказа:</b>\n{items_html}"
        f"━━━━━━━━━━━━━━━\n"
        f"💰 Сумма: {float(data.amount_rub):.2f} ₽\n"
        f"🥗 Дотация: {float(applied_subsidy_kop/100):.2f} ₽\n"
        f"💳 Из лимита: {float(withdraw_rub):.2f} ₽\n\n"
        f"📉 <b>Остаток: {round(emp.month_limit_rub, 1)} ₽</b>"
    )
    send_tg_msg(emp.telegram_id, user_receipt)

    if data.is_manual and data.live_frame_base64:
        db_photo = f"/app/static/photos/{sess.card_uid}.jpg"
        if os.path.exists(db_photo):
            admin_caption = (f"⚠️ <b>РУЧНАЯ ОПЛАТА</b>\n━━━━━━━━━━━━━━━\n👤 <b>{emp.full_name}</b>\n"
                             f"💵 Сумма: {data.amount_rub} ₽\n🛒 <b>Заказ:</b>\n{items_html}")
            send_tg_report(ADMIN_CHAT_ID, db_photo, data.live_frame_base64, admin_caption)

    return {"status": "success", "remaining_limit": round(emp.month_limit_rub, 2)}
