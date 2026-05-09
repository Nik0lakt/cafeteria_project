import os
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.database import engine, Base
from app.routers import auth, payment, liveness, bot


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
