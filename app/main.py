import os
import shutil
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.database import engine, Base
from app.routers import auth, payment, liveness, bot, cashiers
from app import cashiers_db


def _col_exists(conn, table: str, column: str) -> bool:
    res = conn.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = :t AND column_name = :c"
    ), {"t": table, "c": column})
    return bool(res.fetchone())


def update_db_schema():
    with engine.connect() as conn:
        # notifications_enabled
        if not _col_exists(conn, "employees", "notifications_enabled"):
            conn.execute(text(
                "ALTER TABLE employees ADD COLUMN notifications_enabled BOOLEAN DEFAULT TRUE"
            ))
            conn.commit()

        # month_limit_kopecks (перенос данных из month_limit_rub если колонка существует)
        if not _col_exists(conn, "employees", "month_limit_kopecks"):
            conn.execute(text(
                "ALTER TABLE employees ADD COLUMN month_limit_kopecks BIGINT DEFAULT 500000"
            ))
            if _col_exists(conn, "employees", "month_limit_rub"):
                conn.execute(text(
                    "UPDATE employees "
                    "SET month_limit_kopecks = ROUND(COALESCE(month_limit_rub, 5000) * 100)"
                ))
            conn.commit()

        # hashed_password для сотрудников (замена web_password)
        if not _col_exists(conn, "employees", "hashed_password"):
            conn.execute(text(
                "ALTER TABLE employees ADD COLUMN hashed_password VARCHAR"
            ))
            conn.commit()

        # face_embedding_json (замена face_embedding/pickle)
        if not _col_exists(conn, "employees", "face_embedding_json"):
            conn.execute(text(
                "ALTER TABLE employees ADD COLUMN face_embedding_json JSON"
            ))
            conn.commit()

        # hashed_password для касс (замена password)
        if not _col_exists(conn, "cash_desks", "hashed_password"):
            conn.execute(text(
                "ALTER TABLE cash_desks ADD COLUMN hashed_password VARCHAR"
            ))
            conn.commit()

        # passed — флаг успешного прохождения liveness (защита от обхода оплаты)
        if not _col_exists(conn, "liveness_sessions", "passed"):
            conn.execute(text(
                "ALTER TABLE liveness_sessions ADD COLUMN passed BOOLEAN NOT NULL DEFAULT FALSE"
            ))
            conn.commit()

        # embedding_json — кэш вектора в сессии (без повторных запросов на каждый кадр)
        if not _col_exists(conn, "liveness_sessions", "embedding_json"):
            conn.execute(text(
                "ALTER TABLE liveness_sessions ADD COLUMN embedding_json JSON"
            ))
            conn.commit()

        # last_seen — время последнего пинга с кассы (для online/offline статуса)
        if not _col_exists(conn, "cash_desks", "last_seen"):
            conn.execute(text(
                "ALTER TABLE cash_desks ADD COLUMN last_seen TIMESTAMP"
            ))
            conn.commit()

        # assigned_cashier_logins — список кассиров (JSON-массив логинов)
        if not _col_exists(conn, "cash_desks", "assigned_cashier_logins"):
            conn.execute(text(
                "ALTER TABLE cash_desks ADD COLUMN assigned_cashier_logins JSON"
            ))
            # Мигрируем старое одиночное поле в новый список, если оно есть
            if _col_exists(conn, "cash_desks", "assigned_cashier_login"):
                conn.execute(text(
                    "UPDATE cash_desks "
                    "SET assigned_cashier_logins = json_build_array(assigned_cashier_login) "
                    "WHERE assigned_cashier_login IS NOT NULL AND assigned_cashier_login != ''"
                ))
            conn.commit()


PRIVATE_PHOTOS_DIR = "/app/private_photos"
OLD_PHOTOS_DIR = "/app/static/photos"


def migrate_photos():
    """Переносим фото из static/photos в private_photos (однократно при первом запуске)."""
    os.makedirs(PRIVATE_PHOTOS_DIR, exist_ok=True)
    if not os.path.isdir(OLD_PHOTOS_DIR):
        return
    for fname in os.listdir(OLD_PHOTOS_DIR):
        if fname.startswith("."):
            continue
        src = os.path.join(OLD_PHOTOS_DIR, fname)
        dst = os.path.join(PRIVATE_PHOTOS_DIR, fname)
        if os.path.isfile(src) and not os.path.exists(dst):
            shutil.move(src, dst)


update_db_schema()
Base.metadata.create_all(bind=engine)
cashiers_db.init_db()
migrate_photos()

app = FastAPI(title="Cafeteria")


@app.on_event("startup")
async def startup_event():
    bot.start_bot()


app.include_router(auth.router, prefix="/api")
app.include_router(liveness.router, prefix="/api")
app.include_router(payment.router, prefix="/api")
app.include_router(cashiers.router, prefix="/api")

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/", StaticFiles(directory="static", html=True), name="root")
