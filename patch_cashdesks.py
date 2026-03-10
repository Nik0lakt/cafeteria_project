import re

# --- Обновляем app/models.py ---
with open('app/models.py', 'r', encoding='utf-8') as f:
    models_code = f.read()

if 'class CashDesk' not in models_code:
    models_code += "\n\nclass CashDesk(Base):\n    __tablename__ = 'cash_desks'\n    id = Column(Integer, primary_key=True, index=True)\n    login = Column(String, unique=True, index=True)\n    description = Column(String, nullable=True)\n"
    with open('app/models.py', 'w', encoding='utf-8') as f:
        f.write(models_code)
    print("✅ app/models.py обновлен (добавлена таблица CashDesk)")

# --- Обновляем app/routers/payment.py ---
with open('app/routers/payment.py', 'r', encoding='utf-8') as f:
    router_code = f.read()

if 'verify_cash_desk' not in router_code:
    # Добавляем импорт CashDesk
    router_code = router_code.replace('from app.models import Employee', 'from app.models import CashDesk, Employee')
    
    new_endpoints = """
class CashDeskCreate(BaseModel):
    login: str
    description: str

class CashDeskLogin(BaseModel):
    login: str

@router.post("/verify_cash_desk")
def verify_cash_desk(data: CashDeskLogin, db: Session = Depends(get_db)):
    desk = db.query(CashDesk).filter(CashDesk.login == data.login).first()
    if not desk:
        raise HTTPException(status_code=401, detail="Касса не найдена")
    return {"status": "ok", "login": desk.login, "description": desk.description}

@router.get("/cash_desks")
def get_cash_desks(db: Session = Depends(get_db)):
    return db.query(CashDesk).all()

@router.post("/cash_desks")
def add_cash_desk(data: CashDeskCreate, db: Session = Depends(get_db)):
    if db.query(CashDesk).filter(CashDesk.login == data.login).first():
        raise HTTPException(status_code=400, detail="Логин занят")
    new_desk = CashDesk(login=data.login, description=data.description)
    db.add(new_desk)
    db.commit()
    return {"status": "success"}

@router.delete("/cash_desks/{desk_id}")
def delete_cash_desk(desk_id: int, db: Session = Depends(get_db)):
    desk = db.query(CashDesk).filter(CashDesk.id == desk_id).first()
    if desk:
        db.delete(desk)
        db.commit()
    return {"status": "success"}
"""
    router_code += new_endpoints
    with open('app/routers/payment.py', 'w', encoding='utf-8') as f:
        f.write(router_code)
    print("✅ app/routers/payment.py обновлен (добавлены API для касс)")

# --- Безопасно обновляем admin.html ---
# Ищем файл админки (может быть в корне или в static)
admin_path = 'admin.html' if os.path.exists('admin.html') else ('static/admin.html' if os.path.exists('static/admin.html') else None)
if admin_path:
    with open(admin_path, 'r', encoding='utf-8') as f:
        admin_html = f.read()
        
    if 'loadCashDesks' not in admin_html:
        cashdesk_ui = """
    <div class="container mt-5 mb-5">
        <hr>
        <h3 class="mb-4">Управление кассами (Логины терминалов)</h3>
        <div class="card mb-4 p-3 shadow-sm">
            <h5 class="mb-3">Создать новый логин кассы</h5>
            <div class="row g-2">
                <div class="col-md-5"><input type="text" id="newDeskLogin" class="form-control" placeholder="Логин (например, kassa1)"></div>
                <div class="col-md-5"><input type="text" id="newDeskDesc" class="form-control" placeholder="Описание (Касса в холле)"></div>
                <div class="col-md-2"><button class="btn btn-success w-100" onclick="addCashDesk()">Создать</button></div>
            </div>
        </div>
        <table class="table table-bordered bg-white shadow-sm">
            <thead class="table-light"><tr><th>ID</th><th>Логин</th><th>Описание</th><th>Действия</th></tr></thead>
            <tbody id="cashDesksTableBody"></tbody>
        </table>
    </div>
    
    <script>
        async function loadCashDesks() {
            const res = await fetch('/api/cash_desks');
            const desks = await res.json();
            document.getElementById('cashDesksTableBody').innerHTML = desks.map(d => `<tr><td>${d.id}</td><td><b>${d.login}</b></td><td>${d.description || ''}</td><td><button class="btn btn-sm btn-danger" onclick="deleteCashDesk(${d.id})">Удалить</button></td></tr>`).join('');
        }
        async function addCashDesk() {
            const login = document.getElementById('newDeskLogin').value.trim();
            const desc = document.getElementById('newDeskDesc').value.trim();
            if(!login) return alert("Введите логин");
            await fetch('/api/cash_desks', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({login: login, description: desc})});
            document.getElementById('newDeskLogin').value = ''; document.getElementById('newDeskDesc').value = ''; loadCashDesks();
        }
        async function deleteCashDesk(id) {
            if(confirm("Удалить эту кассу?")) { await fetch(`/api/cash_desks/${id}`, {method: 'DELETE'}); loadCashDesks(); }
        }
        document.addEventListener('DOMContentLoaded', loadCashDesks);
    </script>
"""
        admin_html = admin_html.replace('</body>', cashdesk_ui + '\n</body>')
        with open(admin_path, 'w', encoding='utf-8') as f:
            f.write(admin_html)
        print("✅ admin.html безопасно обновлен (секция касс добавлена вниз страницы)")
