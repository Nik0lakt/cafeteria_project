#!/usr/bin/env python3
"""
Demo data initialization for Cafeteria system.
Clears all operational tables and inserts realistic presentation data.
Usage: python init_demo_db.py
"""

import sys
import os
import random
import sqlite3
from datetime import datetime, timedelta, date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from app.database import engine, SessionLocal, Base
from app.models import (
    Employee, Card, Transaction, WorkDay, RoleSetting,
    CashDesk, Category, Product, CashDeskProduct,
    AppSetting, AuditLog, LivenessSession,
)
from app.security import hash_password
from app import cashiers_db

# Ensure all tables exist before we try to delete from them
Base.metadata.create_all(bind=engine)

db = SessionLocal()

# ── 1. CLEAR ALL DATA ────────────────────────────────────────────────────────

print("Clearing all tables...")

db.query(AuditLog).delete()
db.query(Transaction).delete()
db.query(LivenessSession).delete()
db.query(WorkDay).delete()
db.query(Card).delete()
db.query(CashDeskProduct).delete()
db.query(Product).delete()
db.query(Category).delete()
db.query(CashDesk).delete()
db.query(Employee).delete()
db.query(RoleSetting).delete()
db.commit()

# Reset SQLite autoincrement counters
with engine.connect() as conn:
    for tbl in [
        "employees", "cards", "transactions", "work_days", "role_settings",
        "cash_desks", "categories", "products", "audit_logs",
    ]:
        try:
            conn.execute(text(f"DELETE FROM sqlite_sequence WHERE name='{tbl}'"))
        except Exception:
            pass
    conn.commit()

print("  done.")

# ── 2. ROLE SETTINGS ─────────────────────────────────────────────────────────

# 150 rub/day subsidy for workers, 200 rub/day for managers
db.add(RoleSetting(role_name="Работник", subsidy_rub=150.0))
db.add(RoleSetting(role_name="Менеджер", subsidy_rub=200.0))
db.commit()

WORKER_DAILY_SUBSIDY_KOP = 15000  # 150 rub in kopecks

# ── 3. EMPLOYEES ──────────────────────────────────────────────────────────────

print("Creating employee Иван Иванов...")

# We'll set the final remaining balance after generating transactions.
# Starting allowance: 5000 rub = 500000 kopecks per month.
ivan = Employee(
    full_name="Иван Иванов",
    role="Работник",
    month_limit_kopecks=500000,
    face_embedding_json=None,
    telegram_id=None,
    notifications_enabled=True,
    limit_reset_day=1,
)
db.add(ivan)
db.commit()
db.refresh(ivan)

db.add(Card(uid="777888999", employee_id=ivan.id))
db.commit()

print(f"  id={ivan.id}, card=777888999")

# ── 4. CASHIERS (SQLite cashiers.db) ─────────────────────────────────────────

print("Creating cashiers...")

cashier_db_path = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "app", "cashiers.db"
)
if os.path.exists(cashier_db_path):
    c = sqlite3.connect(cashier_db_path)
    c.execute("DELETE FROM cashiers")
    try:
        c.execute("DELETE FROM sqlite_sequence WHERE name='cashiers'")
    except Exception:
        pass
    c.commit()
    c.close()

cashiers_db.init_db()
anna = cashiers_db.create_cashier("Анна Кассир", "anna_kassir")
petr = cashiers_db.create_cashier("Петр Кассир", "petr_kassir")
print(f"  {anna['name']} (login={anna['login']})")
print(f"  {petr['name']} (login={petr['login']})")

# ── 5. CASH DESKS ─────────────────────────────────────────────────────────────

print("Creating cash desks...")

desk1 = CashDesk(
    login="stolovaya",
    description="Основная столовая",
    hashed_password=hash_password("desk123"),
    assigned_cashier_logins=["anna_kassir", "petr_kassir"],
)
desk2 = CashDesk(
    login="bufet",
    description="Буфет",
    hashed_password=hash_password("desk456"),
    assigned_cashier_logins=["anna_kassir"],
)
db.add(desk1)
db.add(desk2)
db.commit()
db.refresh(desk1)
db.refresh(desk2)

print(f"  Касса 1: login='{desk1.login}', id={desk1.id}")
print(f"  Касса 2: login='{desk2.login}', id={desk2.id}")

# ── 6. CATEGORIES & PRODUCTS ──────────────────────────────────────────────────

print("Building menu for Основная столовая...")

# price is stored in INTEGER RUBLES in Product/CashDeskProduct
# amount_total_kopecks = price * qty * 100  (see calculate_secure_total)

stolovaya_menu = {
    "Первые блюда": [
        ("Борщ со сметаной",         120),
        ("Суп харчо",                 110),
        ("Щи из свежей капусты",      100),
        ("Солянка сборная",           140),
    ],
    "Вторые блюда": [
        ("Котлета по-домашнему",      180),
        ("Бефстроганов",              280),
        ("Стейк из свинины",          350),
        ("Куриная грудка гриль",      250),
    ],
    "Гарниры": [
        ("Картофельное пюре",          80),
        ("Рис отварной",               60),
        ("Гречка",                     70),
        ("Тушёная капуста",            75),
    ],
    "Напитки": [
        ("Кофе американо",             90),
        ("Чай зелёный",                50),
        ("Компот из сухофруктов",      60),
        ("Сок апельсиновый",           80),
    ],
    "Комплексные обеды": [
        ("Комплекс №1 (суп + горячее + напиток)", 380),
        ("Комплекс №2 (2 горячих + гарнир)",      420),
        ("Бизнес-ланч",                           350),
    ],
}

bufet_menu = {
    "Выпечка": [
        ("Круассан",                   70),
        ("Пирожок с капустой",         50),
        ("Булочка с корицей",          60),
    ],
    "Напитки": [
        ("Кофе капучино",             120),
        ("Чай чёрный",                 40),
        ("Вода минеральная",           30),
    ],
}

# {desk_id: [(name, price_rub), ...]}  — flat product list per desk for transaction gen
desk_products = {desk1.id: [], desk2.id: []}


def create_menu(desk, menu_dict):
    for cat_name, items in menu_dict.items():
        cat = Category(name=cat_name, cash_desk_id=desk.id)
        db.add(cat)
        db.commit()
        db.refresh(cat)
        for name, price_rub in items:
            prod = Product(name=name, price=price_rub, category_id=cat.id)
            db.add(prod)
            db.commit()
            db.refresh(prod)
            db.add(CashDeskProduct(cash_desk_id=desk.id, product_id=prod.id, price=price_rub))
            db.commit()
            desk_products[desk.id].append((prod.id, name, price_rub))


create_menu(desk1, stolovaya_menu)
create_menu(desk2, bufet_menu)
print(f"  {len(desk_products[desk1.id])} products in stolovaya, {len(desk_products[desk2.id])} in bufet")

# ── 7. TRANSACTION HISTORY ────────────────────────────────────────────────────

print("Generating 20 transactions (April–May 2026)...")

random.seed(42)  # reproducible demo

# Collect all workdays April 14 – May 14, 2026 (Mon–Fri)
start_date = date(2026, 4, 14)
end_date   = date(2026, 5, 14)
workdays = [
    start_date + timedelta(days=i)
    for i in range((end_date - start_date).days + 1)
    if (start_date + timedelta(days=i)).weekday() < 5
]

# Pick ~20 visit dates; some days have two visits (stolovaya + bufet)
visit_days = sorted(random.sample(workdays, 17))
double_days = set(random.sample(visit_days[3:], 3))  # 3 days with two receipts

# Build visit list: (date, desk, products_pool)
visits = []
for d in visit_days:
    visits.append((d, desk1, desk_products[desk1.id]))
    if d in double_days:
        visits.append((d, desk2, desk_products[desk2.id]))

# Payment method weights: mostly internal (subsidy), some card and cash
payment_pool = (
    ["internal"] * 10 +
    ["bank_card"] * 6 +
    ["cash"] * 4
)
random.shuffle(payment_pool)

limit_consumed = 0  # tracks kopecks deducted from month_limit

transactions_created = 0
for i, (visit_date, desk, pool) in enumerate(visits):
    n_items = random.randint(2, 3) if desk.id == desk1.id else random.randint(1, 2)
    chosen = random.sample(pool, min(n_items, len(pool)))

    items_json = [
        {"name": name, "price": price_rub, "qty": 1}
        for (_, name, price_rub) in chosen
    ]
    total_kop = sum(price_rub * 100 for (_, _, price_rub) in chosen)

    payment_method = payment_pool[i % len(payment_pool)]

    if payment_method == "internal":
        # Subsidy covers up to 150 rub; remainder comes from monthly limit
        subsidy_kop = min(WORKER_DAILY_SUBSIDY_KOP, total_kop)
        limit_kop   = total_kop - subsidy_kop
        limit_consumed += limit_kop
    else:
        # Card / cash — no subsidy, no limit deduction for this demo
        subsidy_kop = 0
        limit_kop   = 0

    hour   = random.randint(11, 14)
    minute = random.randint(0, 59)
    tx_dt  = datetime(visit_date.year, visit_date.month, visit_date.day, hour, minute, 0)

    tx = Transaction(
        employee_id=ivan.id,
        amount_total_kopecks=total_kop,
        subsidy_part_kopecks=subsidy_kop,
        limit_part_kopecks=limit_kop,
        status="COMPLETED",
        created_at=tx_dt,
        cash_desk_id=desk.login,
        payment_method=payment_method,
        items=items_json,
    )
    db.add(tx)
    transactions_created += 1

db.commit()

# Update Ivan's remaining monthly limit
ivan.month_limit_kopecks = max(0, 500000 - limit_consumed)
db.commit()

print(f"  {transactions_created} transactions created.")
print(f"  Limit consumed:  {limit_consumed / 100:.2f} rub")
print(f"  Remaining limit: {ivan.month_limit_kopecks / 100:.2f} rub")

# ── 8. APP SETTINGS ───────────────────────────────────────────────────────────

if not db.query(AppSetting).filter(AppSetting.key == "manual_payment_use_subsidy").first():
    db.add(AppSetting(key="manual_payment_use_subsidy", value="true"))
    db.commit()

remaining_rub = ivan.month_limit_kopecks / 100
db.close()

# ── SUMMARY ───────────────────────────────────────────────────────────────────

print()
print("=" * 52)
print("  Demo data ready!")
print("=" * 52)
print(f"  Employee : Иван Иванов  (card: 777888999)")
print(f"  Desk 1   : stolovaya    (password: desk123)")
print(f"  Desk 2   : bufet        (password: desk456)")
print(f"  Cashier 1: anna_kassir")
print(f"  Cashier 2: petr_kassir")
print(f"  Remaining limit: {remaining_rub:.0f} rub / 5000 rub")
print("=" * 52)
