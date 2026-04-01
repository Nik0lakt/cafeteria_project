import os
from dotenv import load_dotenv

# ЭТО ДОЛЖНО БЫТЬ САМЫМ ПЕРВЫМ
load_dotenv()

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.database import engine, Base
from app.routers import auth, payment, liveness, bot

from sqlalchemy import text

def update_db_schema():
    with engine.connect() as conn:
        # Проверяем наличие колонки notifications_enabled
        res = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='employees' AND column_name='notifications_enabled'"))
        if not res.fetchone():
            print("Обновление базы: Добавляю колонку notifications_enabled...")
            conn.execute(text("ALTER TABLE employees ADD COLUMN notifications_enabled BOOLEAN DEFAULT TRUE"))
            conn.commit()
            print("База успешно обновлена (уведомления)!")

update_db_schema()

Base.metadata.create_all(bind=engine)
app = FastAPI(title="Cafeteria")

@app.on_event("startup")
async def startup_event():
    bot.start_bot()

app.include_router(auth.router, prefix="/api")
app.include_router(liveness.router, prefix="/api")
app.include_router(payment.router, prefix="/api")

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/", StaticFiles(directory="static", html=True), name="root")
