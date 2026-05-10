from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.security import get_current_admin
from app import cashiers_db

router = APIRouter()


class CashierCreate(BaseModel):
    name: str
    login: str


@router.get("/cashiers")
def list_cashiers(_=Depends(get_current_admin)):
    return cashiers_db.get_all_cashiers()


@router.post("/cashiers", dependencies=[Depends(get_current_admin)])
def create_cashier(data: CashierCreate):
    if not data.name.strip():
        raise HTTPException(400, "Имя кассира не может быть пустым")
    if not data.login.strip():
        raise HTTPException(400, "Логин не может быть пустым")
    try:
        return cashiers_db.create_cashier(data.name, data.login)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/cashiers/{cashier_id}", dependencies=[Depends(get_current_admin)])
def delete_cashier(cashier_id: int):
    if not cashiers_db.delete_cashier(cashier_id):
        raise HTTPException(404, "Кассир не найден")
    return {"status": "deleted"}
