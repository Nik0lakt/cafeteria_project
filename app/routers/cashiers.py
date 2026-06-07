import os

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from app import cashiers_db
from app.security import get_current_admin

router = APIRouter()

PHOTOS_DIR = "/app/private_photos"


class CashierCreate(BaseModel):
    name: str
    login: str


@router.get("/cashiers", dependencies=[Depends(get_current_admin)])
def list_cashiers():
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


@router.post("/cashiers/{cashier_id}/photo", dependencies=[Depends(get_current_admin)])
async def upload_cashier_photo(cashier_id: int, file: UploadFile = File(...)):
    cashier = cashiers_db.get_cashier_by_id(cashier_id)
    if not cashier:
        raise HTTPException(404, "Кассир не найден")
    filename = f"cashier_{cashier_id}.jpg"
    path = os.path.join(PHOTOS_DIR, filename)
    contents = await file.read()
    with open(path, "wb") as f:
        f.write(contents)
    cashiers_db.update_cashier_photo(cashier_id, filename)
    return {"status": "ok", "photo_path": filename}


@router.delete("/cashiers/{cashier_id}", dependencies=[Depends(get_current_admin)])
def delete_cashier(cashier_id: int):
    if not cashiers_db.delete_cashier(cashier_id):
        raise HTTPException(404, "Кассир не найден")
    return {"status": "deleted"}
