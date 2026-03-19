import os, re

def patch_backend():
    path = 'app/routers/payment.py'
    with open(path, 'r', encoding='utf-8') as f:
        code = f.read()
    if '@router.put("/products/' not in code:
        edit_api = """
@router.put("/products/{p_id}")
def edit_product(p_id: int, data: ProductCreate, db: Session = Depends(get_db)):
    p = db.query(Product).filter(Product.id == p_id).first()
    if p:
        p.name = data.name
        p.price = data.price
        p.category_id = data.category_id
        db.commit()
        return {"status": "ok"}
    raise HTTPException(404, "Товар не найден")
"""
        code = code.replace('@router.post("/verify_desk_password")', edit_api + '\n@router.post("/verify_desk_password")')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(code)

def patch_index():
    for path in ['index.html', 'static/index.html']:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                html = f.read()
            html = html.replace("location.href = 'canteen.html'", "location.href = 'canteen.html?desk=' + currentCashDesk")
            with open(path, 'w', encoding='utf-8') as f:
                f.write(html)

def patch_admin():
    path = 'admin.html' if os.path.exists('admin.html') else ('static/admin.html' if os.path.exists('static/admin.html') else None)
    if path:
        with open(path, 'r', encoding='utf-8') as f:
            html = f.read()
        if 'async function forceChangePwd' not in html:
            script = """
            <script>
                async function forceChangePwd(id) {
                    const np = prompt("Введите новый пароль для этой кассы:");
                    if(np) {
                        try {
                            const res = await fetch(`/api/cash_desks/${id}/password`, {
                                method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({password: np})
                            });
                            if(res.ok) alert("Пароль успешно изменен!"); else alert("Ошибка смены пароля");
                        } catch(e) { alert("Ошибка соединения"); }
                    }
                }
            </script>
            """
            html = html.replace("</body>", script + "\n</body>")
            html = re.sub(r'onclick=[\'"]changeDeskPwd\([^)]+\)[\'"]', 'onclick="forceChangePwd(${d.id})"', html)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(html)

patch_backend()
patch_index()
patch_admin()
print("Бэкенд, индекс и админка успешно обновлены!")
