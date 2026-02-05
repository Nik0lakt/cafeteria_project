import time, json, urllib.request, threading, sys
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import SessionLocal
from app.models import Employee, Transaction, WorkDay, RoleSetting
from datetime import date

TELEGRAM_BOT_TOKEN = "8535946989:AAGgrIxaCBad8DS0yRac-lTehOi-8KNvAOE"

def send_reply(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    try: urllib.request.urlopen(req, timeout=5)
    except: pass

def process_message(db, chat_id, text):
    text = text.lower()
    if text == "/start":
        send_reply(chat_id, "Привет! Напиши 'баланс' или /my для проверки лимитов.")
    elif text == "/my" or "баланс" in text:
        emp = db.query(Employee).filter(Employee.telegram_id == str(chat_id)).first()
        if not emp:
            send_reply(chat_id, f"❌ Вы не зарегистрированы.\nВаш ID: <code>{chat_id}</code>")
            return

        is_work_day = db.query(WorkDay).filter(WorkDay.employee_id == emp.id, WorkDay.date == date.today()).first() is not None
        role_set = db.query(RoleSetting).filter(RoleSetting.role_name == emp.role).first()
        daily_subsidy = role_set.subsidy_rub if (role_set and is_work_day) else 0

        used_today_kop = db.query(func.sum(Transaction.subsidy_part_kopecks)).filter(
            Transaction.employee_id == emp.id, func.date(Transaction.created_at) == date.today()
        ).scalar() or 0
        
        subsidy_status = f"✅ Доступно: {daily_subsidy} ₽ (Потрачено: {used_today_kop/100} ₽)" if daily_subsidy > 0 else "❌ Сегодня нет дотации"
        
        msg = (f"👤 <b>{emp.full_name}</b>\n━━━━━━━━━━━━━━━\n"
               f"🥗 <b>Дотация:</b>\n{subsidy_status}\n\n"
               f"💳 <b>Лимит:</b> {round(emp.month_limit_rub, 2)} ₽")
        send_reply(chat_id, msg)

def bot_polling():
    offset = 0
    print("--- BOT POLLING STARTED ---", file=sys.stderr)
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates?offset={offset}&timeout=30"
            with urllib.request.urlopen(url, timeout=35) as response:
                data = json.loads(response.read().decode())
                for update in data.get("result", []):
                    offset = update["update_id"] + 1
                    if "message" in update:
                        chat_id = update["message"]["chat"]["id"]
                        text = update["message"].get("text", "")
                        db = SessionLocal()
                        try: process_message(db, chat_id, text)
                        finally: db.close()
        except Exception as e:
            print(f"--- POLLING ERROR: {e}", file=sys.stderr)
            time.sleep(5)

# Запуск в отдельном потоке
def start_bot():
    thread = threading.Thread(target=bot_polling, daemon=True)
    thread.start()
