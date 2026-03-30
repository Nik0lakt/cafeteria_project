import os
import urllib.request, json, base64
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models import CashDesk, Employee, Category, Product, Card, Transaction, WorkDay, RoleSetting, LivenessSession, CashDeskProduct
from pydantic import BaseModel
from datetime import date, datetime, time, timedelta
from typing import List, Optional
import csv
import io
from fastapi.responses import StreamingResponse

router = APIRouter()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")

# --- СХЕМЫ ДАННЫХ ---

class OrderItem(BaseModel):
    product_id: int
    quantity: int

class ExternalPaymentRequest(BaseModel):
    cash_desk_id: str
    items: List[OrderItem]
    payment_method: str

class PaymentRequest(BaseModel):
    session_id: str
    items: List[OrderItem]
    is_manual: bool = False
    live_frame_base64: Optional[str] = None
    cash_desk_id: Optional[str] = "unknown"

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

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

def calculate_secure_total(db: Session, cash_desk_login: str, items: List[OrderItem]):
    total_kop = 0
    detailed_items = []
    desk = db.query(CashDesk).filter(CashDesk.login == cash_desk_login).first()
    if not desk:
        raise HTTPException(status_code=400, detail="Касса не найдена")
    for item in items:
        mapping = db.query(CashDeskProduct).filter(
            CashDeskProduct.product_id == item.product_id,
            CashDeskProduct.cash_desk_id == desk.id
        ).first()
        product = db.query(Product).filter(Product.id == item.product_id).first()
        if not product: continue
        price = mapping.price if mapping else product.price
        total_kop += (price * item.quantity * 100)
        detailed_items.append({"name": product.name, "price": price, "qty": item.quantity})
    return int(total_kop), detailed_items

# --- РОУТЫ ОПЛАТЫ ---

@router.post("/pay_external")
def pay_external(data: ExternalPaymentRequest, db: Session = Depends(get_db)):
    total_bill_kop, detailed_items = calculate_secure_total(db, data.cash_desk_id, data.items)
    if not detailed_items or total_bill_kop <= 0:
        raise HTTPException(status_code=400, detail="Заказ пуст")
    new_tx = Transaction(
        employee_id=None,
        amount_total_kopecks=total_bill_kop,
        subsidy_part_kopecks=0,
        limit_part_kopecks=total_bill_kop,
        status="COMPLETED",
        created_at=datetime.now(),
        cash_desk_id=data.cash_desk_id,
        payment_method=data.payment_method,
        items=detailed_items
    )
    db.add(new_tx)
    db.commit()
    return {"status": "success", "total_paid": total_bill_kop / 100}

@router.post("/pay")
def pay(data: PaymentRequest, db: Session = Depends(get_db)):
    sess = db.query(LivenessSession).filter(LivenessSession.id == data.session_id).first()
    if not sess: raise HTTPException(404, "Сессия не найдена")
    card = db.query(Card).filter(Card.uid == sess.card_uid).first()
    if not card: raise HTTPException(404, "Карта не найдена")
    emp = db.query(Employee).filter(Employee.id == card.employee_id).first()

    total_bill_kop, detailed_items = calculate_secure_total(db, data.cash_desk_id, data.items)
    if not detailed_items or total_bill_kop <= 0:
        raise HTTPException(status_code=400, detail="Список товаров пуст")

    is_work_day = db.query(WorkDay).filter(WorkDay.employee_id == emp.id, WorkDay.date == date.today()).first() is not None
    role_set = db.query(RoleSetting).filter(RoleSetting.role_name == emp.role).first()
    daily_subsidy_limit_kop = float(role_set.subsidy_rub * 100) if (role_set and is_work_day) else 0.0

    applied_subsidy_kop = 0.0
    if daily_subsidy_limit_kop > 0:
        start_of_today = datetime.combine(date.today(), time.min)
        raw_used = db.query(func.sum(Transaction.subsidy_part_kopecks)).filter(
            Transaction.employee_id == emp.id,
            Transaction.created_at >= start_of_today
        ).scalar()
        used_today_kop = float(raw_used) if raw_used is not None else 0.0
        available_today_kop = max(0.0, daily_subsidy_limit_kop - used_today_kop)
        applied_subsidy_kop = min(total_bill_kop, available_today_kop)

    withdraw_rub = (total_bill_kop - applied_subsidy_kop) / 100.0
    if emp.month_limit_rub < withdraw_rub:
        raise HTTPException(status_code=400, detail="Недостаточно средств")

    new_tx = Transaction(
        employee_id=emp.id,
        amount_total_kopecks=int(total_bill_kop),
        subsidy_part_kopecks=int(applied_subsidy_kop),
        limit_part_kopecks=int(total_bill_kop - applied_subsidy_kop),
        status="COMPLETED",
        created_at=datetime.now(),
        cash_desk_id=data.cash_desk_id,
        payment_method="internal",
        items=detailed_items
    )
    emp.month_limit_rub -= withdraw_rub
    db.add(new_tx)
    db.delete(sess)
    db.commit()

    items_html = "".join([f"• {i['name']} (x{i['qty']}) — {i['price'] * i['qty']} руб.\n" for i in detailed_items])
    user_receipt = (
        f"💳 <b>Оплата принята</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🛒 <b>Заказ:</b>\n{items_html}"
        f"━━━━━━━━━━━━━━━\n"
        f"💰 Сумма: {total_bill_kop/100:.2f} ₽\n"
        f"🥗 Дотация: {applied_subsidy_kop/100:.2f} ₽\n"
        f"💳 Из лимита: {withdraw_rub:.2f} ₽\n\n"
        f"📉 <b>Остаток: {round(emp.month_limit_rub, 1)} ₽</b>"
    )
    send_tg_msg(emp.telegram_id, user_receipt)

    if data.is_manual and data.live_frame_base64:
        db_photo = f"/app/static/photos/{sess.card_uid}.jpg"
        if os.path.exists(db_photo):
            admin_caption = (
                f"⚠️ <b>РУЧНАЯ ОПЛАТА</b>\n"
                f"━━━━━━━━━━━━━━━\n"
                f"👤 <b>{emp.full_name}</b>\n"
                f"🖥 Касса: {data.cash_desk_id}\n"
                f"💵 Сумма: {total_bill_kop/100:.2f} ₽\n"
                f"🛒 <b>Заказ:</b>\n{items_html}"
            )
            send_tg_report(ADMIN_CHAT_ID, db_photo, data.live_frame_base64, admin_caption)

    return {"status": "success", "remaining_limit": round(emp.month_limit_rub, 2)}

# --- АДМИНКА И ТОВАРЫ ---

@router.post("/verify_cash_desk")
def verify_cash_desk(data: dict, db: Session = Depends(get_db)):
    desk = db.query(CashDesk).filter(CashDesk.login == data.get("login")).first()
    if not desk: raise HTTPException(status_code=401, detail="Касса не найдена")
    return {"status": "ok", "login": desk.login, "id": desk.id}

@router.get("/cash_desks")
def get_cash_desks(db: Session = Depends(get_db)):
    return db.query(CashDesk).all()

@router.post("/cash_desks")
def add_cash_desk(data: dict, db: Session = Depends(get_db)):
    new_desk = CashDesk(login=data.get("login"), description=data.get("description"), password=data.get("password"))
    db.add(new_desk)
    db.commit()
    return {"status": "success"}

@router.delete("/cash_desks/{desk_id}")
def delete_cash_desk(desk_id: int, db: Session = Depends(get_db)):
    desk = db.query(CashDesk).filter(CashDesk.id == desk_id).first()
    if desk:
        db.delete(desk)
        db.commit()
    return {"status": "success"}

@router.get("/categories")
def get_categories(cash_desk_login: Optional[str] = None, db: Session = Depends(get_db)):
    if cash_desk_login:
        return db.query(Category).join(CashDesk).filter(CashDesk.login == cash_desk_login).all()
    return db.query(Category).all()

@router.post("/categories")
def add_category(data: dict, db: Session = Depends(get_db)):
    desk_id = data.get("cash_desk_id")
    if not desk_id:
        raise HTTPException(status_code=400, detail="Не указан ID кассы")
    cat = Category(name=data.get("name"), cash_desk_id=desk_id)
    db.add(cat)
    db.commit()
    return {"status": "ok"}

@router.get("/products")
def get_products(cash_desk_login: Optional[str] = None, db: Session = Depends(get_db)):
    if cash_desk_login:
        desk = db.query(CashDesk).filter(CashDesk.login == cash_desk_login).first()
        if not desk: return []
        mappings = db.query(CashDeskProduct).filter(CashDeskProduct.cash_desk_id == desk.id).all()
        result = []
        for m in mappings:
            prod = db.query(Product).filter(Product.id == m.product_id).first()
            if prod:
                result.append({"id": prod.id, "name": prod.name, "price": m.price, "category_id": prod.category_id})
        return result
    return db.query(Product).all()

@router.post("/products")
def add_product(data: dict, db: Session = Depends(get_db)):
    new_p = Product(name=data.get("name"), price=data.get("price"), category_id=data.get("category_id"))
    db.add(new_p)
    db.commit()
    db.refresh(new_p)
    if data.get("cash_desk_ids"):
        for d_id in data.get("cash_desk_ids"):
            db.add(CashDeskProduct(cash_desk_id=d_id, product_id=new_p.id, price=data.get("price")))
        db.commit()
    return {"status": "ok"}

@router.post("/verify_desk_password")
def verify_desk_password(data: dict, db: Session = Depends(get_db)):
    desk = db.query(CashDesk).filter(CashDesk.login == data.get("login")).first()
    if desk and desk.password == data.get("password"): return {"status": "ok"}
    raise HTTPException(403, "Неверный пароль")

# --- СТАТИСТИКА И ЭКСПОРТ ---

@router.get("/statistics/export")
def export_statistics_csv(start_date: date = Query(...), end_date: date = Query(...), db: Session = Depends(get_db)):
    transactions = db.query(Transaction).filter(
        func.date(Transaction.created_at) >= start_date,
        func.date(Transaction.created_at) <= end_date
    ).order_by(Transaction.created_at.desc()).all()
    stream = io.StringIO()
    writer = csv.writer(stream, delimiter=';', dialect='excel')
    writer.writerow(["ID", "Дата", "Сотрудник", "Касса", "Метод", "Сумма (РУБ)", "Состав заказа"])
    for t in transactions:
        rubles = float(t.amount_total_kopecks) / 100.0 if t.amount_total_kopecks else 0.0
        item_summary = {}
        if t.items and isinstance(t.items, list):
            for item in t.items:
                name = item.get('name', 'Товар')
                qty = item.get('qty', 1)
                item_summary[name] = item_summary.get(name, 0) + qty
        items_str = ", ".join([f"{name} x{qty}" for name, qty in item_summary.items()])
        emp_name = t.employee.full_name if t.employee else "Внешняя оплата"
        writer.writerow([
            t.id, t.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            emp_name, t.cash_desk_id, t.payment_method,
            f"{rubles:.2f}".replace('.', ','), items_str
        ])
    content = u'\ufeff' + stream.getvalue()
    return StreamingResponse(
        iter([content.encode("utf-8-sig")]), 
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": f"attachment; filename=report.csv"}
    )

