import os
import urllib.request, json, base64
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models import CashDesk, Employee, Category, Product, Card, Transaction, WorkDay, RoleSetting, LivenessSession
from pydantic import BaseModel
from datetime import date, datetime, time
from typing import List, Optional
import csv
import io
from datetime import date, datetime, timedelta
from fastapi import Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func


router = APIRouter()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")

class OrderItem(BaseModel):
    name: str
    price: int

class ExternalPaymentRequest(BaseModel):
    cash_desk_id: str
    amount_rub: float
    items: Optional[List[OrderItem]] = []
    payment_method: str

class PaymentRequest(BaseModel):
    session_id: str
    amount_rub: int
    items: Optional[List[OrderItem]] = []
    is_manual: bool = False
    live_frame_base64: Optional[str] = None
    cash_desk_id: Optional[str] = "unknown"

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

@router.post("/pay_external")
def pay_external(data: ExternalPaymentRequest, db: Session = Depends(get_db)):
    total_bill_kop = int(data.amount_rub * 100)
    
    new_tx = Transaction(
        employee_id=None,
        amount_total_kopecks=total_bill_kop,
        subsidy_part_kopecks=0,
        limit_part_kopecks=total_bill_kop,
        status="COMPLETED",
        created_at=datetime.now(),
        cash_desk_id=data.cash_desk_id,
        payment_method=data.payment_method,
        items=[item.dict() for item in data.items]
    )
    db.add(new_tx)
    db.commit()

    counts = {}
    for i in data.items:
        if i.name not in counts: counts[i.name] = {"qty": 0, "price": i.price}
        counts[i.name]["qty"] += 1
    items_html = "".join([f"• {name} ({v['qty']} шт.) — {v['price']*v['qty']} руб.\n" for name, v in counts.items()])

    method_name = "БАНКОВСКОЙ КАРТОЙ" if data.payment_method == 'bank_card' else "НАЛИЧНЫМИ"
    admin_caption = (
        f"💳 <b>ОПЛАТА {method_name}</b>\n"
        f"🖥 Касса: {data.cash_desk_id}\n"
        f"💵 Сумма: {data.amount_rub} ₽\n"
        f"🛒 <b>Заказ:</b>\n{items_html}"
    )
    send_tg_msg(ADMIN_CHAT_ID, admin_caption)
    return {"status": "success"}

@router.post("/pay")
def pay(data: PaymentRequest, db: Session = Depends(get_db)):
    sess = db.query(LivenessSession).filter(LivenessSession.id == data.session_id).first()
    if not sess: raise HTTPException(404, "Сессия не найдена")

    card = db.query(Card).filter(Card.uid == sess.card_uid).first()
    emp = db.query(Employee).filter(Employee.id == card.employee_id).first()

    is_work_day = db.query(WorkDay).filter(WorkDay.employee_id == emp.id, WorkDay.date == date.today()).first() is not None
    role_set = db.query(RoleSetting).filter(RoleSetting.role_name == emp.role).first()
    daily_subsidy_limit_kop = float(role_set.subsidy_rub * 100) if (role_set and is_work_day) else 0.0

    total_bill_kop = float(data.amount_rub * 100)
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
        raise HTTPException(status_code=400, detail="Недостаточно личных средств")

    new_tx = Transaction(
        employee_id=emp.id,
        amount_total_kopecks=int(total_bill_kop),
        subsidy_part_kopecks=int(applied_subsidy_kop),
        limit_part_kopecks=int(total_bill_kop - applied_subsidy_kop),
        status="COMPLETED",
        created_at=datetime.now(),
        cash_desk_id=data.cash_desk_id,
        payment_method="internal",
        items=[item.dict() for item in data.items]
    )
    
    emp.month_limit_rub -= withdraw_rub
    db.add(new_tx)
    db.delete(sess)
    db.commit()

    counts = {}
    for i in data.items:
        if i.name not in counts: counts[i.name] = {"qty": 0, "price": i.price}
        counts[i.name]["qty"] += 1
    
    items_html = ""
    for name, v in counts.items():
        qty = v["qty"]
        items_html += f"• {name}{f' ({qty} шт.)' if qty > 1 else ''} — {v['price'] * qty} руб.\n"

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
                             f"🖥 Касса: {data.cash_desk_id}\n"
                             f"💵 Сумма: {data.amount_rub} ₽\n🛒 <b>Заказ:</b>\n{items_html}")
            send_tg_report(ADMIN_CHAT_ID, db_photo, data.live_frame_base64, admin_caption)

    return {"status": "success", "remaining_limit": round(emp.month_limit_rub, 2)}

class CashDeskCreate(BaseModel):
    login: str
    description: str
    password: str

class CashDeskLogin(BaseModel):
    login: str

@router.post("/verify_cash_desk")
def verify_cash_desk(data: CashDeskLogin, db: Session = Depends(get_db)):
    desk = db.query(CashDesk).filter(CashDesk.login == data.login).first()
    if not desk:
        raise HTTPException(status_code=401, detail="Касса не найдена")
    return {"status": "ok", "login": desk.login, "description": desk.description}

@router.get("/cash_desks")
def get_cash_desks(db: Session = Depends(get_db)):
    return db.query(CashDesk).all()

@router.post("/cash_desks")
def add_cash_desk(data: CashDeskCreate, db: Session = Depends(get_db)):
    if db.query(CashDesk).filter(CashDesk.login == data.login).first():
        raise HTTPException(status_code=400, detail="Логин занят")
    new_desk = CashDesk(login=data.login, description=data.description, password=data.password)
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

class CategoryCreate(BaseModel):
    name: str

class ProductCreate(BaseModel):
    name: str
    price: int
    category_id: int

class DeskPassword(BaseModel):
    password: str

class VerifyDeskPassword(BaseModel):
    login: str
    password: str

@router.get("/categories")
def get_categories(db: Session = Depends(get_db)):
    return db.query(Category).all()

@router.post("/categories")
def add_category(data: CategoryCreate, db: Session = Depends(get_db)):
    cat = Category(name=data.name)
    db.add(cat)
    db.commit()
    return {"status": "ok"}

@router.delete("/categories/{cat_id}")
def delete_category(cat_id: int, db: Session = Depends(get_db)):
    db.query(Product).filter(Product.category_id == cat_id).delete()
    db.query(Category).filter(Category.id == cat_id).delete()
    db.commit()
    return {"status": "ok"}

@router.get("/products")
def get_products(db: Session = Depends(get_db)):
    return db.query(Product).all()

@router.post("/products")
def add_product(data: ProductCreate, db: Session = Depends(get_db)):
    p = Product(name=data.name, price=data.price, category_id=data.category_id)
    db.add(p)
    db.commit()
    return {"status": "ok"}

@router.delete("/products/{p_id}")
def delete_product(p_id: int, db: Session = Depends(get_db)):
    db.query(Product).filter(Product.id == p_id).delete()
    db.commit()
    return {"status": "ok"}


@router.put("/products/{p_id}")
def edit_product(p_id: int, data: ProductCreate, db: Session = Depends(get_db)):
    p = db.query(Product).filter(Product.id == p_id).first()
    if p:
        p.name = data.name
        p.price = data.price
        p.category_id = data.category_id
        db.commit()
        return {"status": "ok"}
    raise HTTPException(404, "Товар не найден")

@router.post("/verify_desk_password")
def verify_desk_password(data: VerifyDeskPassword, db: Session = Depends(get_db)):
    desk = db.query(CashDesk).filter(CashDesk.login == data.login).first()
    if desk and desk.password == data.password:
        return {"status": "ok"}
    raise HTTPException(403, "Неверный пароль")

@router.put("/cash_desks/{desk_id}/password")
def update_desk_password(desk_id: int, data: DeskPassword, db: Session = Depends(get_db)):
    desk = db.query(CashDesk).filter(CashDesk.id == desk_id).first()
    if desk:
        desk.password = data.password
        db.commit()
        return {"status": "ok"}
    raise HTTPException(404, "Касса не найдена")

@router.get("/statistics/chart")
def get_statistics_chart(
    start_date: str = Query(...),
    end_date: str = Query(...),
    payment_methods: Optional[List[str]] = Query(None),
    cash_desks: Optional[List[str]] = Query(None),
    db: Session = Depends(get_db)
):
    try:
        # Базовый запрос: сумма по дням
        query = db.query(
            func.date(Transaction.created_at).label('day'),
            func.sum(Transaction.amount_total_kopecks).label('total')
        ).filter(
            func.date(Transaction.created_at) >= start_date,
            func.date(Transaction.created_at) <= end_date
        )

        # Фильтр методов оплаты (internal, cash, bank_card)
        if payment_methods:
            methods = [m for m in payment_methods if m and m.strip()]
            if methods:
                query = query.filter(Transaction.payment_method.in_(methods))
        
        # Фильтр касс: пробуем искать и как числа, и как строки
        if cash_desks:
            desks = [d for d in cash_desks if d and d.strip()]
            if desks:
                # SQLite поймет сравнение строки с числом, если мы передадим список строк
                query = query.filter(Transaction.cash_desk_id.in_(desks))

        results = query.group_by(func.date(Transaction.created_at)).order_by('day').all()

        labels = []
        data = []
        for row in results:
            labels.append(str(row[0])) # Дата YYYY-MM-DD
            # ПРАВИЛО: float() перед делением на 100
            val = float(row[1] or 0) / 100.0
            data.append(val)

        # Это появится в терминале твоего сервера (для отладки)
        print(f"--- STATS DEBUG ---")
        print(f"Period: {start_date} to {end_date}")
        print(f"Methods: {payment_methods} | Desks: {cash_desks}")
        print(f"Found: {len(results)} days of data")

        return {"labels": labels, "data": data}
    except Exception as e:
        print(f"CRITICAL STATS ERROR: {e}")
        return {"labels": [], "data": [], "error": str(e)}

@router.get("/statistics/export")
def export_statistics_csv(
    start_date: date = Query(...),
    end_date: date = Query(...),
    db: Session = Depends(get_db)
):
    # Выгружаем транзакции за период
    transactions = db.query(Transaction).filter(
        func.date(Transaction.created_at) >= start_date,
        func.date(Transaction.created_at) <= end_date
    ).all()

    # Используем StringIO для создания CSV
    stream = io.StringIO()
    writer = csv.writer(stream, delimiter=';', dialect='excel')

    # Заголовки колонок
    writer.writerow(["ID", "Дата", "Касса", "Метод", "Сумма (РУБ)"])

    for t in transactions:
        # Конвертируем копейки в рубли через float
        rubles = float(t.amount_total_kopecks) / 100.0 if t.amount_total_kopecks else 0.0
        writer.writerow([
            t.id,
            t.created_at.strftime("%Y-%m-%d %H:%M") if t.created_at else "",
            t.cash_desk_id,
            t.payment_method,
            f"{rubles:.2f}".replace('.', ',') # Запятая лучше для русского Excel
        ])

    # ВАЖНО: Добавляем BOM (u'\ufeff') и кодируем в utf-8-sig для Excel
    content = u'\ufeff' + stream.getvalue()
    
    return StreamingResponse(
        iter([content.encode("utf-8-sig")]), 
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": f"attachment; filename=export_{start_date}_{end_date}.csv"}
    )
