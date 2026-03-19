from app.database import engine
from app.models import Category, Product, CashDesk
from sqlalchemy import text
Category.__table__.create(bind=engine, checkfirst=True)
Product.__table__.create(bind=engine, checkfirst=True)
with engine.connect() as conn:
    try: conn.execute(text("ALTER TABLE cash_desks ADD COLUMN password VARCHAR DEFAULT '1234'"))
    except: pass
    conn.commit()
    
    # Добавляем базовые категории, если их нет
    if conn.execute(text("SELECT count(*) FROM categories")).scalar() == 0:
        conn.execute(text("INSERT INTO categories (name) VALUES ('Напитки'), ('Выпечка'), ('Снеки')"))
        conn.execute(text("INSERT INTO products (name, price, category_id) VALUES ('Кофе', 80, 1), ('Чай', 40, 1), ('Пицца', 150, 2)"))
        conn.commit()
print("✅ БД обновлена!")
