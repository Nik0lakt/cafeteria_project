import os
import sqlite3
from typing import List, Optional

from app.config import PRIVATE_PHOTOS_DIR

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cashiers.db")

PHOTOS_DIR = PRIVATE_PHOTOS_DIR


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cashiers (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT    NOT NULL,
                login      TEXT    NOT NULL UNIQUE,
                photo_path TEXT
            )
        """)
        # Migration: add photo_path if it doesn't exist yet
        try:
            conn.execute("ALTER TABLE cashiers ADD COLUMN photo_path TEXT")
        except sqlite3.OperationalError:
            pass
        conn.commit()


def create_cashier(name: str, login: str) -> dict:
    with _connect() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO cashiers (name, login) VALUES (?, ?)",
                (name.strip(), login.strip()),
            )
            conn.commit()
            return {"id": cur.lastrowid, "name": name.strip(), "login": login.strip(), "photo_path": None}
        except sqlite3.IntegrityError:
            raise ValueError(f"Логин «{login}» уже занят")


def get_all_cashiers() -> List[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT id, name, login, photo_path FROM cashiers ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def get_cashier_by_login(login: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, name, login, photo_path FROM cashiers WHERE login = ?",
            (login.strip(),),
        ).fetchone()
    return dict(row) if row else None


def get_cashier_by_id(cashier_id: int) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, name, login, photo_path FROM cashiers WHERE id = ?",
            (cashier_id,),
        ).fetchone()
    return dict(row) if row else None


def update_cashier_photo(cashier_id: int, photo_path: str):
    with _connect() as conn:
        conn.execute("UPDATE cashiers SET photo_path = ? WHERE id = ?", (photo_path, cashier_id))
        conn.commit()


def delete_cashier(cashier_id: int) -> bool:
    cashier = get_cashier_by_id(cashier_id)
    if cashier and cashier.get("photo_path"):
        try:
            os.remove(os.path.join(PHOTOS_DIR, cashier["photo_path"]))
        except OSError:
            pass
    with _connect() as conn:
        cur = conn.execute("DELETE FROM cashiers WHERE id = ?", (cashier_id,))
        conn.commit()
    return cur.rowcount > 0
