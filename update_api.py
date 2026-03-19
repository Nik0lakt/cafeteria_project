with open('app/routers/payment.py', 'r', encoding='utf-8') as f:
    content = f.read()

if 'class CategoryCreate' not in content:
    content = content.replace('from app.models import CashDesk, Employee', 'from app.models import CashDesk, Employee, Category, Product')
    
    api_code = """
class CategoryCreate(BaseModel):
    name: str

class ProductCreate(BaseModel):
    name: str
    price: int
    category_id: int

class DeskPassword(BaseModel):
    password: str

class VerifyDeskPassword(BaseModel):
    login: str
    password: str

@router.get("/categories")
def get_categories(db: Session = Depends(get_db)):
    return db.query(Category).all()

@router.post("/categories")
def add_category(data: CategoryCreate, db: Session = Depends(get_db)):
    cat = Category(name=data.name)
    db.add(cat)
    db.commit()
    return {"status": "ok"}

@router.delete("/categories/{cat_id}")
def delete_category(cat_id: int, db: Session = Depends(get_db)):
    db.query(Product).filter(Product.category_id == cat_id).delete()
    db.query(Category).filter(Category.id == cat_id).delete()
    db.commit()
    return {"status": "ok"}

@router.get("/products")
def get_products(db: Session = Depends(get_db)):
    return db.query(Product).all()

@router.post("/products")
def add_product(data: ProductCreate, db: Session = Depends(get_db)):
    p = Product(name=data.name, price=data.price, category_id=data.category_id)
    db.add(p)
    db.commit()
    return {"status": "ok"}

@router.delete("/products/{p_id}")
def delete_product(p_id: int, db: Session = Depends(get_db)):
    db.query(Product).filter(Product.id == p_id).delete()
    db.commit()
    return {"status": "ok"}

@router.post("/verify_desk_password")
def verify_desk_password(data: VerifyDeskPassword, db: Session = Depends(get_db)):
    desk = db.query(CashDesk).filter(CashDesk.login == data.login).first()
    if desk and desk.password == data.password:
        return {"status": "ok"}
    raise HTTPException(403, "Неверный пароль")

@router.put("/cash_desks/{desk_id}/password")
def update_desk_password(desk_id: int, data: DeskPassword, db: Session = Depends(get_db)):
    desk = db.query(CashDesk).filter(CashDesk.id == desk_id).first()
    if desk:
        desk.password = data.password
        db.commit()
        return {"status": "ok"}
    raise HTTPException(404, "Касса не найдена")
"""
    # Заменяем старую схему создания кассы
    content = content.replace(
        "class CashDeskCreate(BaseModel):\n    login: str\n    description: str",
        "class CashDeskCreate(BaseModel):\n    login: str\n    description: str\n    password: str"
    )
    content = content.replace(
        "new_desk = CashDesk(login=data.login, description=data.description)",
        "new_desk = CashDesk(login=data.login, description=data.description, password=data.password)"
    )
    
    with open('app/routers/payment.py', 'w', encoding='utf-8') as f:
        f.write(content + api_code)
    print("✅ Бэкенд API обновлен!")
