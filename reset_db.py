import sys
import os
from sqlalchemy import text

# Добавляем путь, чтобы видеть папку app
sys.path.append(os.getcwd())

from app.database import engine, Base
# Импорт моделей, чтобы создать их заново
from app.models import Employee, CashDesk, Product, Category, Transaction, Card, RoleSetting, LivenessSession

print("♻️  Принудительная очистка всей базы (CASCADE)...")

with engine.connect() as conn:
    # Этот код полностью сносит схему public и создает её заново - это удалит ВСЕ таблицы
    conn.execute(text("DROP SCHEMA public CASCADE;"))
    conn.execute(text("CREATE SCHEMA public;"))
    conn.commit()

print("🏗️  Создание новой структуры по моделям...")
Base.metadata.create_all(bind=engine)

print("✅ База идеально чиста и пересоздана!")
