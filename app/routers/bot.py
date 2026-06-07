import json
import os
import sys
import threading
import time as time_module
import urllib.request
from datetime import date, datetime, time

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Employee, RoleSetting, Transaction, WorkDay

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


def send_reply(chat_id, text):
    if not TELEGRAM_BOT_TOKEN:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass


def process_message(db: Session, chat_id, text):
    text = text.lower()
    if text == "/start":
        send_reply(chat_id, "Привет! Напиши 'баланс' или /my для проверки лимитов.")
    elif text == "/my" or "баланс" in text:
        emp = db.query(Employee).filter(Employee.telegram_id == str(chat_id)).first()
        if not emp:
            send_reply(chat_id, f"❌ Вы не зарегистрированы. Ваш ID: {chat_id}")
            return

        is_work_day = (
            db.query(WorkDay)
            .filter(WorkDay.employee_id == emp.id, WorkDay.date == date.today())
            .first()
        ) is not None
        role_set = db.query(RoleSetting).filter(RoleSetting.role_name == emp.role).first()
        daily_limit = role_set.subsidy_rub if (role_set and is_work_day) else 0

        start_of_today = datetime.combine(date.today(), time.min)
        used_today_kop = db.query(func.sum(Transaction.subsidy_part_kopecks)).filter(
            Transaction.employee_id == emp.id,
            Transaction.created_at >= start_of_today,
        ).scalar() or 0

        used_today_rub = used_today_kop / 100
        subsidy_status = (
            f"✅ Доступно: {daily_limit} ₽ (Потрачено: {used_today_rub} ₽)"
            if daily_limit > 0
            else "❌ Сегодня нет дотации"
        )

        msg = (
            f"👤 <b>{emp.full_name}</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"🥗 <b>Дотация:</b>\n{subsidy_status}\n\n"
            f"💳 <b>Лимит:</b> {emp.month_limit_kopecks / 100:.2f} ₽"
        )
        send_reply(chat_id, msg)


def bot_polling():
    offset = 0
    time_module.sleep(2)
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("--- BOT ERROR: TELEGRAM_BOT_TOKEN NOT FOUND IN ENV ---", file=sys.stderr)
        return
    print(f"--- BOT POLLING STARTED WITH TOKEN: {token[:10]}... ---", file=sys.stderr)
    while True:
        try:
            url = f"https://api.telegram.org/bot{token}/getUpdates?offset={offset}&timeout=30"
            with urllib.request.urlopen(url, timeout=35) as response:
                data = json.loads(response.read().decode())
                for update in data.get("result", []):
                    offset = update["update_id"] + 1
                    if "message" in update:
                        chat_id = update["message"]["chat"]["id"]
                        text = update["message"].get("text", "")
                        db = SessionLocal()
                        try:
                            process_message(db, chat_id, text)
                        finally:
                            db.close()
        except Exception as e:
            print(f"--- POLLING ERROR: {e}", file=sys.stderr)
            time_module.sleep(10)


def start_bot():
    thread = threading.Thread(target=bot_polling, daemon=True)
    thread.start()
