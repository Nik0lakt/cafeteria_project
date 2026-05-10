import os
import sqlite3
from typing import List, Optional

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cashiers.db")


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cashiers (
                id    INTEGER PRIMARY KEY AUTOINCREMENT,
                name  TEXT    NOT NULL,
                login TEXT    NOT NULL UNIQUE
            )
        """)
        conn.commit()


def create_cashier(name: str, login: str) -> dict:
    with _connect() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO cashiers (name, login) VALUES (?, ?)",
                (name.strip(), login.strip()),
            )
            conn.commit()
            return {"id": cur.lastrowid, "name": name.strip(), "login": login.strip()}
        except sqlite3.IntegrityError:
            raise ValueError(f"Логин «{login}» уже занят")


def get_all_cashiers() -> List[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT id, name, login FROM cashiers ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def get_cashier_by_login(login: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, name, login FROM cashiers WHERE login = ?",
            (login.strip(),),
        ).fetchone()
    return dict(row) if row else None


def delete_cashier(cashier_id: int) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM cashiers WHERE id = ?", (cashier_id,))
        conn.commit()
    return cur.rowcount > 0
