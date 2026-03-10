from app.database import engine
from sqlalchemy import text
with engine.connect() as conn:
    try:
        conn.execute(text("ALTER TABLE transactions ALTER COLUMN employee_id DROP NOT NULL;"))
        conn.execute(text("ALTER TABLE transactions ADD COLUMN cash_desk_id VARCHAR;"))
        conn.execute(text("ALTER TABLE transactions ADD COLUMN payment_method VARCHAR DEFAULT 'internal';"))
        conn.execute(text("ALTER TABLE transactions ADD COLUMN items JSON;"))
        conn.commit()
        print("✅ База данных (PostgreSQL) успешно обновлена!")
    except Exception as e:
        print("ℹ️ Миграция уже применена.")
