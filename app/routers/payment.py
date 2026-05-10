import os
import urllib.request
import json
import base64
import csv
import io
import random
import string
from datetime import date, datetime, time, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel

from app.database import get_db
from app.models import (
    CashDesk, Employee, Category, Product, Card,
    Transaction, WorkDay, RoleSetting, LivenessSession, CashDeskProduct,
)
from app.security import hash_password, verify_password

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


class AdminLoginRequest(BaseModel):
    password: str


class UserLoginRequest(BaseModel):
    card_uid: Optional[str] = None
    login: Optional[str] = None
    password: Optional[str] = None


# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def send_tg_msg(chat_id, text):
    if not chat_id or not TELEGRAM_BOT_TOKEN:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass


def send_tg_report(chat_id, db_photo_path, live_photo_b64, caption):
    if not chat_id or not TELEGRAM_BOT_TOKEN:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMediaGroup"
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    try:
        live_bytes = base64.b64decode(live_photo_b64.split(",")[1])
        with open(db_photo_path, "rb") as f:
            db_bytes = f.read()
    except Exception:
        return
    media = [
        {"type": "photo", "media": "attach://p1", "caption": caption, "parse_mode": "HTML"},
        {"type": "photo", "media": "attach://p2"},
    ]
    parts = [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{chat_id}\r\n",
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"media\"\r\n\r\n{json.dumps(media)}\r\n",
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"p1\"; filename=\"1.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n".encode("ascii"),
        db_bytes, b"\r\n",
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"p2\"; filename=\"2.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n".encode("ascii"),
        live_bytes,
        f"\r\n--{boundary}--\r\n".encode("ascii"),
    ]
    body = b"".join([p if isinstance(p, bytes) else p.encode("utf-8") for p in parts])
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        urllib.request.urlopen(req, timeout=15)
    except Exception:
        pass


def calculate_secure_total(db: Session, cash_desk_login: str, items: List[OrderItem]):
    total_kop = 0
    detailed_items = []
    desk = db.query(CashDesk).filter(CashDesk.login == cash_desk_login).first()
    if not desk:
        raise HTTPException(status_code=400, detail="Касса не найдена")
    for item in items:
        mapping = db.query(CashDeskProduct).filter(
            CashDeskProduct.product_id == item.product_id,
            CashDeskProduct.cash_desk_id == desk.id,
        ).first()
        product = db.query(Product).filter(Product.id == item.product_id).first()
        if not product:
            continue
        price = mapping.price if mapping else product.price
        total_kop += price * item.quantity * 100
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
        items=detailed_items,
    )
    db.add(new_tx)
    db.commit()
    return {"status": "success", "total_paid": total_bill_kop / 100}


@router.post("/user/toggle_notifications/{emp_id}")
def toggle_notifications(emp_id: int, db: Session = Depends(get_db)):
    emp = db.query(Employee).filter(Employee.id == emp_id).first()
    if not emp:
        raise HTTPException(404)
    emp.notifications_enabled = not emp.notifications_enabled
    db.commit()
    return {"enabled": emp.notifications_enabled}


@router.post("/pay")
def pay(data: PaymentRequest, db: Session = Depends(get_db)):
    sess = db.query(LivenessSession).filter(LivenessSession.id == data.session_id).first()
    if not sess:
        raise HTTPException(404, "Сессия не найдена")
    card = db.query(Card).filter(Card.uid == sess.card_uid.strip()).first()
    if not card:
        raise HTTPException(404, "Карта не найдена")
    emp = db.query(Employee).filter(Employee.id == card.employee_id).first()

    total_bill_kop, detailed_items = calculate_secure_total(db, data.cash_desk_id, data.items)
    if not detailed_items or total_bill_kop <= 0:
        raise HTTPException(status_code=400, detail="Список товаров пуст")

    is_work_day = (
        db.query(WorkDay)
        .filter(WorkDay.employee_id == emp.id, WorkDay.date == date.today())
        .first()
    ) is not None
    role_set = db.query(RoleSetting).filter(RoleSetting.role_name == emp.role).first()
    daily_subsidy_limit_kop = (
        int(round(role_set.subsidy_rub * 100)) if (role_set and is_work_day) else 0
    )

    applied_subsidy_kop = 0
    if daily_subsidy_limit_kop > 0:
        start_of_today = datetime.combine(date.today(), time.min)
        raw_used = db.query(func.sum(Transaction.subsidy_part_kopecks)).filter(
            Transaction.employee_id == emp.id,
            Transaction.created_at >= start_of_today,
        ).scalar()
        used_today_kop = int(raw_used) if raw_used is not None else 0
        available_today_kop = max(0, daily_subsidy_limit_kop - used_today_kop)
        applied_subsidy_kop = min(total_bill_kop, available_today_kop)

    withdraw_kopecks = total_bill_kop - applied_subsidy_kop
    if emp.month_limit_kopecks < withdraw_kopecks:
        raise HTTPException(status_code=400, detail="Недостаточно средств")

    new_tx = Transaction(
        employee_id=emp.id,
        amount_total_kopecks=total_bill_kop,
        subsidy_part_kopecks=applied_subsidy_kop,
        limit_part_kopecks=withdraw_kopecks,
        status="COMPLETED",
        created_at=datetime.now(),
        cash_desk_id=data.cash_desk_id,
        payment_method="internal",
        items=detailed_items,
    )
    emp.month_limit_kopecks -= withdraw_kopecks
    db.add(new_tx)
    db.delete(sess)
    db.commit()

    items_html = "".join(
        [f"• {i['name']} (x{i['qty']}) — {i['price'] * i['qty']} руб.\n" for i in detailed_items]
    )
    user_receipt = (
        f"💳 <b>Оплата принята</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🛒 <b>Заказ:</b>\n{items_html}"
        f"━━━━━━━━━━━━━━━\n"
        f"💰 Сумма: {total_bill_kop / 100:.2f} ₽\n"
        f"🥗 Дотация: {applied_subsidy_kop / 100:.2f} ₽\n"
        f"💳 Из лимита: {withdraw_kopecks / 100:.2f} ₽\n\n"
        f"📉 <b>Остаток: {emp.month_limit_kopecks / 100:.2f} ₽</b>"
    )

    if emp.notifications_enabled:
        send_tg_msg(emp.telegram_id, user_receipt)

    if data.is_manual and data.live_frame_base64:
        db_photo = f"/app/static/photos/{sess.card_uid}.jpg"
        if os.path.exists(db_photo):
            admin_caption = (
                f"⚠️ <b>РУЧНАЯ ОПЛАТА</b>\n"
                f"━━━━━━━━━━━━━━━\n"
                f"👤 <b>{emp.full_name}</b>\n"
                f"🖥 Касса: {data.cash_desk_id}\n"
                f"💵 Сумма: {total_bill_kop / 100:.2f} ₽\n"
                f"🛒 <b>Заказ:</b>\n{items_html}"
            )
            send_tg_report(ADMIN_CHAT_ID, db_photo, data.live_frame_base64, admin_caption)

    return {"status": "success", "remaining_limit": emp.month_limit_kopecks / 100}


# --- КАССЫ ---

@router.post("/verify_cash_desk")
def verify_cash_desk(data: dict, db: Session = Depends(get_db)):
    from app import cashiers_db as cdb
    desk_login    = data.get("login", "").strip()
    cashier_login = data.get("cashier_login", "").strip()

    desk = db.query(CashDesk).filter(CashDesk.login == desk_login).first()
    if not desk:
        raise HTTPException(status_code=401, detail="Касса не найдена")

    assigned = desk.assigned_cashier_logins or []
    if assigned:
        if not cashier_login:
            raise HTTPException(status_code=401, detail="Требуется логин кассира")
        if cashier_login not in assigned:
            raise HTTPException(status_code=403, detail="Этот кассир не закреплён за данной кассой")
        cashier = cdb.get_cashier_by_login(cashier_login)
        if not cashier:
            raise HTTPException(status_code=401, detail="Кассир не найден в базе")
        return {"status": "ok", "login": desk.login, "id": desk.id,
                "cashier_name": cashier["name"], "cashier_login": cashier_login}

    return {"status": "ok", "login": desk.login, "id": desk.id,
            "cashier_name": None, "cashier_login": None}


@router.get("/cash_desks")
def get_cash_desks(db: Session = Depends(get_db)):
    return [
        {
            "id": d.id,
            "login": d.login,
            "description": d.description,
            "assigned_cashier_logins": d.assigned_cashier_logins or [],
        }
        for d in db.query(CashDesk).all()
    ]


@router.post("/cash_desks")
def add_cash_desk(data: dict, db: Session = Depends(get_db)):
    raw_password = data.get("password", "")
    db.add(CashDesk(
        login=data.get("login"),
        description=data.get("description"),
        hashed_password=hash_password(raw_password) if raw_password else None,
    ))
    db.commit()
    return {"status": "success"}


@router.put("/cash_desks/{desk_id}")
def update_cash_desk(desk_id: int, data: dict, db: Session = Depends(get_db)):
    desk = db.query(CashDesk).filter(CashDesk.id == desk_id).first()
    if not desk:
        raise HTTPException(status_code=404, detail="Касса не найдена")
    if "description" in data:
        desk.description = data["description"]
    if "assigned_cashier_logins" in data:
        desk.assigned_cashier_logins = data["assigned_cashier_logins"] or []
    if data.get("new_password"):
        desk.hashed_password = hash_password(data["new_password"])
    db.commit()
    return {"status": "success"}


@router.delete("/cash_desks/{desk_id}")
def delete_cash_desk(desk_id: int, db: Session = Depends(get_db)):
    desk = db.query(CashDesk).filter(CashDesk.id == desk_id).first()
    if desk:
        db.delete(desk)
        db.commit()
    return {"status": "success"}


# --- КАТЕГОРИИ И ТОВАРЫ ---

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
    db.add(Category(name=data.get("name"), cash_desk_id=desk_id))
    db.commit()
    return {"status": "ok"}


@router.get("/products")
def get_products(cash_desk_login: Optional[str] = None, db: Session = Depends(get_db)):
    if cash_desk_login:
        desk = db.query(CashDesk).filter(CashDesk.login == cash_desk_login).first()
        if not desk:
            return []
        mappings = db.query(CashDeskProduct).filter(CashDeskProduct.cash_desk_id == desk.id).all()
        result = []
        for m in mappings:
            prod = db.query(Product).filter(Product.id == m.product_id).first()
            if prod:
                result.append({
                    "id": prod.id, "name": prod.name,
                    "price": m.price, "category_id": prod.category_id,
                })
        return result
    return db.query(Product).all()


@router.post("/products")
def add_product(data: dict, db: Session = Depends(get_db)):
    new_p = Product(
        name=data.get("name"),
        price=data.get("price"),
        category_id=data.get("category_id"),
    )
    db.add(new_p)
    db.commit()
    db.refresh(new_p)
    if data.get("cash_desk_ids"):
        for d_id in data["cash_desk_ids"]:
            db.add(CashDeskProduct(cash_desk_id=d_id, product_id=new_p.id, price=data.get("price")))
        db.commit()
    return {"status": "ok"}


@router.put("/products/{p_id}")
def update_product(p_id: int, data: dict, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == p_id).first()
    if not product:
        raise HTTPException(404, "Товар не найден")
    if "name" in data:
        product.name = data["name"]
    if "price" in data:
        product.price = data["price"]
        for d_id in (data.get("cash_desk_ids") or []):
            mapping = db.query(CashDeskProduct).filter(
                CashDeskProduct.product_id == p_id,
                CashDeskProduct.cash_desk_id == d_id,
            ).first()
            if mapping:
                mapping.price = data["price"]
    db.commit()
    return {"status": "ok"}


@router.delete("/products/{p_id}")
def delete_product(p_id: int, db: Session = Depends(get_db)):
    db.query(CashDeskProduct).filter(CashDeskProduct.product_id == p_id).delete()
    db.query(Product).filter(Product.id == p_id).delete()
    db.commit()
    return {"status": "ok"}


@router.put("/categories/{cat_id}")
def update_category(cat_id: int, data: dict, db: Session = Depends(get_db)):
    cat = db.query(Category).filter(Category.id == cat_id).first()
    if not cat:
        raise HTTPException(404, "Категория не найдена")
    if "name" in data:
        cat.name = data["name"]
    db.commit()
    return {"status": "ok"}


@router.delete("/categories/{cat_id}")
def delete_category(cat_id: int, db: Session = Depends(get_db)):
    prods = db.query(Product).filter(Product.category_id == cat_id).all()
    for prod in prods:
        db.query(CashDeskProduct).filter(CashDeskProduct.product_id == prod.id).delete()
    db.query(Product).filter(Product.category_id == cat_id).delete()
    db.query(Category).filter(Category.id == cat_id).delete()
    db.commit()
    return {"status": "ok"}


@router.post("/verify_desk_password")
def verify_desk_password(data: dict, db: Session = Depends(get_db)):
    desk = db.query(CashDesk).filter(CashDesk.login == data.get("login")).first()
    if desk and desk.hashed_password and verify_password(data.get("password", ""), desk.hashed_password):
        return {"status": "ok"}
    raise HTTPException(403, "Неверный пароль")


# --- АВТОРИЗАЦИЯ ТЕРМИНАЛА ---

@router.post("/login")
async def admin_login(data: AdminLoginRequest):
    admin_password = os.getenv("ADMIN_PASSWORD", "")
    if admin_password and data.password == admin_password:
        return {"success": True}
    return {"success": False}


# --- СТАТИСТИКА И ЭКСПОРТ ---

@router.get("/statistics/chart")
def get_chart_data(
    start_date: date = Query(...),
    end_date: date = Query(...),
    cash_desks: Optional[List[str]] = Query(None),
    payment_methods: Optional[List[str]] = Query(None),
    db: Session = Depends(get_db),
):
    labels = []
    curr = start_date
    while curr <= end_date:
        labels.append(curr.strftime("%Y-%m-%d"))
        curr += timedelta(days=1)

    query = db.query(Transaction).filter(
        func.date(Transaction.created_at) >= start_date,
        func.date(Transaction.created_at) <= end_date,
        Transaction.status == "COMPLETED",
    )
    if cash_desks:
        query = query.filter(Transaction.cash_desk_id.in_(cash_desks))
    if payment_methods:
        query = query.filter(Transaction.payment_method.in_(payment_methods))

    transactions = query.all()
    active_desks = list(set(t.cash_desk_id for t in transactions)) if transactions else []
    datasets = []
    for desk_id in active_desks:
        daily_sums = {label: 0.0 for label in labels}
        for tx in [t for t in transactions if t.cash_desk_id == desk_id]:
            day_key = tx.created_at.strftime("%Y-%m-%d")
            if day_key in daily_sums:
                daily_sums[day_key] += (tx.amount_total_kopecks or 0) / 100.0
        datasets.append({
            "label": f"Касса {desk_id}",
            "data": [round(daily_sums[label], 2) for label in labels],
        })

    if not datasets:
        datasets.append({"label": "Нет данных", "data": [0] * len(labels)})

    return {"labels": labels, "datasets": datasets, "total_count": len(transactions)}


@router.get("/statistics/export")
def export_statistics_csv(
    start_date: date = Query(...), end_date: date = Query(...), db: Session = Depends(get_db)
):
    transactions = db.query(Transaction).filter(
        func.date(Transaction.created_at) >= start_date,
        func.date(Transaction.created_at) <= end_date,
    ).order_by(Transaction.created_at.desc()).all()

    stream = io.StringIO()
    writer = csv.writer(stream, delimiter=";", dialect="excel")
    writer.writerow(["ID", "Дата", "Сотрудник", "Касса", "Метод", "Сумма (РУБ)", "Состав заказа"])
    for t in transactions:
        rubles = (t.amount_total_kopecks or 0) / 100.0
        item_summary = {}
        if t.items and isinstance(t.items, list):
            for item in t.items:
                name = item.get("name", "Товар")
                item_summary[name] = item_summary.get(name, 0) + item.get("qty", 1)
        items_str = ", ".join([f"{name} x{qty}" for name, qty in item_summary.items()])
        emp_name = t.employee.full_name if t.employee else "Внешняя оплата"
        writer.writerow([
            t.id, t.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            emp_name, t.cash_desk_id, t.payment_method,
            f"{rubles:.2f}".replace(".", ","), items_str,
        ])
    content = "﻿" + stream.getvalue()
    return StreamingResponse(
        iter([content.encode("utf-8-sig")]),
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": "attachment; filename=report.csv"},
    )


# --- ПОЛЬЗОВАТЕЛЬСКИЙ ПОРТАЛ ---

@router.post("/user/login")
def user_login(data: UserLoginRequest, db: Session = Depends(get_db)):
    card = db.query(Card).filter(Card.uid == data.card_uid.strip()).first()
    if not card:
        raise HTTPException(404, "Карта не найдена")
    return {"status": "success", "emp_id": card.employee_id}


@router.get("/user/full_data/{emp_id}")
def get_user_full_data(emp_id: int, db: Session = Depends(get_db)):
    emp = db.query(Employee).filter(Employee.id == emp_id).first()
    if not emp:
        raise HTTPException(404)

    today = date.today()
    is_work = db.query(WorkDay).filter(
        WorkDay.employee_id == emp.id,
        func.date(WorkDay.date) == today,
    ).first()
    role = db.query(RoleSetting).filter(RoleSetting.role_name == emp.role).first()
    daily_limit = role.subsidy_rub if (role and is_work) else 0

    used_subsidy_kopecks = db.query(func.sum(Transaction.subsidy_part_kopecks)).filter(
        Transaction.employee_id == emp.id,
        func.date(Transaction.created_at) == today,
    ).scalar() or 0

    txs = (
        db.query(Transaction)
        .filter(Transaction.employee_id == emp_id)
        .order_by(Transaction.created_at.desc())
        .limit(30)
        .all()
    )

    return {
        "info": {
            "name": emp.full_name,
            "role": emp.role,
            "limit": emp.month_limit_kopecks / 100,
            "tg_linked": bool(emp.telegram_id),
            "notifications_enabled": emp.notifications_enabled,
        },
        "subsidy": {
            "max": daily_limit,
            "used": round(used_subsidy_kopecks / 100, 2),
            "is_work": bool(is_work),
        },
        "schedule": [
            d[0].isoformat()
            for d in db.query(WorkDay.date)
            .filter(WorkDay.employee_id == emp.id, WorkDay.date >= today.replace(day=1))
            .all()
        ],
        "history": [
            {
                "id": t.id,
                "date": t.created_at.strftime("%d.%m %H:%M"),
                "total": t.amount_total_kopecks / 100,
                "items": t.items,
            }
            for t in txs
        ],
    }


@router.get("/user/info/{emp_id}")
def get_user_info(emp_id: int, db: Session = Depends(get_db)):
    emp = db.query(Employee).filter(Employee.id == emp_id).first()
    if not emp:
        raise HTTPException(404)
    is_work = db.query(WorkDay).filter(
        WorkDay.employee_id == emp.id, WorkDay.date == date.today()
    ).first()
    role = db.query(RoleSetting).filter(RoleSetting.role_name == emp.role).first()
    daily_limit = role.subsidy_rub if (role and is_work) else 0
    used_subsidy = db.query(func.sum(Transaction.subsidy_part_kopecks)).filter(
        Transaction.employee_id == emp.id,
        func.date(Transaction.created_at) == date.today(),
    ).scalar() or 0
    return {
        "full_name": emp.full_name,
        "role": emp.role,
        "balance": emp.month_limit_kopecks / 100,
        "subsidy_today": daily_limit,
        "subsidy_used": used_subsidy / 100,
    }


@router.get("/user/history/{emp_id}")
def get_user_history(emp_id: int, db: Session = Depends(get_db)):
    txs = (
        db.query(Transaction)
        .filter(Transaction.employee_id == emp_id)
        .order_by(Transaction.created_at.desc())
        .limit(20)
        .all()
    )
    return txs
