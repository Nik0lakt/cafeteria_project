import os
import shutil

from dotenv import load_dotenv

load_dotenv()

import time as time_module

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import text

from app import cashiers_db
from app.database import Base, SessionLocal, engine
from app.routers import auth, bot, cashiers, liveness, payment


def _col_exists(conn, table: str, column: str) -> bool:
    try:
        insp = sa_inspect(conn)
        return column in [c["name"] for c in insp.get_columns(table)]
    except Exception:
        return False


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

        # blink_count, eye_closed, last_ear — EAR-based liveness (anti-spoofing)
        if not _col_exists(conn, "liveness_sessions", "blink_count"):
            conn.execute(text(
                "ALTER TABLE liveness_sessions ADD COLUMN blink_count INTEGER NOT NULL DEFAULT 0"
            ))
            conn.commit()
        if not _col_exists(conn, "liveness_sessions", "eye_closed"):
            conn.execute(text(
                "ALTER TABLE liveness_sessions ADD COLUMN eye_closed BOOLEAN NOT NULL DEFAULT FALSE"
            ))
            conn.commit()
        if not _col_exists(conn, "liveness_sessions", "last_ear"):
            conn.execute(text(
                "ALTER TABLE liveness_sessions ADD COLUMN last_ear FLOAT"
            ))
            conn.commit()
        if not _col_exists(conn, "liveness_sessions", "min_ear_closed"):
            conn.execute(text(
                "ALTER TABLE liveness_sessions ADD COLUMN min_ear_closed FLOAT"
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


def seed_defaults():
    from app.models import AppSetting
    db = SessionLocal()
    try:
        defaults = {"manual_payment_use_subsidy": "true"}
        for key, val in defaults.items():
            if not db.query(AppSetting).filter(AppSetting.key == key).first():
                db.add(AppSetting(key=key, value=val))
        db.commit()
    finally:
        db.close()


seed_defaults()

app = FastAPI(title="Cafeteria")

cors_origins = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    bot.start_bot()


# --- Metrics & Health ---

METRICS = {"requests_total": 0, "requests_by_status": {}, "latency_sum_ms": 0.0}


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time_module.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time_module.perf_counter() - start) * 1000
    METRICS["requests_total"] += 1
    METRICS["latency_sum_ms"] += elapsed_ms
    status_key = str(response.status_code)
    METRICS["requests_by_status"][status_key] = METRICS["requests_by_status"].get(status_key, 0) + 1
    return response


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/metrics")
def prometheus_metrics():
    lines = [
        '# TYPE http_requests_total counter',
        f'http_requests_total {METRICS["requests_total"]}',
        '# TYPE http_request_latency_ms_sum counter',
        f'http_request_latency_ms_sum {METRICS["latency_sum_ms"]:.2f}',
    ]
    for code, count in METRICS["requests_by_status"].items():
        lines.append(f'http_requests_by_status{{code="{code}"}} {count}')
    return Response(content="\n".join(lines) + "\n", media_type="text/plain")


app.include_router(auth.router, prefix="/api")
app.include_router(liveness.router, prefix="/api")
app.include_router(payment.router, prefix="/api")
app.include_router(cashiers.router, prefix="/api")

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/", StaticFiles(directory="static", html=True), name="root")
