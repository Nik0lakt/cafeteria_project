import os, re

# Ищем файл там, где он реально лежит
path = 'admin.html' if os.path.exists('admin.html') else ('static/admin.html' if os.path.exists('static/admin.html') else None)

if not path:
    print("❌ Файл admin.html не найден!")
    exit(1)

with open(path, 'r', encoding='utf-8') as f:
    html = f.read()

# Добавляем инпут пароля в форму
if 'id="newDeskPass"' not in html:
    html = re.sub(
        r'(<div style="display: flex; gap: 10px; margin-bottom: 15px;">.*?)(</div>\s*<button onclick="addCashDesk)', 
        r'\1<input type="text" id="newDeskPass" placeholder="Пароль (по умолч. 1234)" style="flex: 1; padding: 12px; border: 1px solid #ccc; border-radius: 4px; font-size: 16px;">\2', 
        html, flags=re.DOTALL
    )
    
    html = html.replace(
        "body: JSON.stringify({login: login, description: desc})", 
        "body: JSON.stringify({login: login, description: desc, password: document.getElementById('newDeskPass').value.trim() || '1234'})"
    )
    html = html.replace(
        "document.getElementById('newDeskDesc').value = '';", 
        "document.getElementById('newDeskDesc').value = ''; document.getElementById('newDeskPass').value = '';"
    )
    
    # Добавляем кнопку "Сменить пароль"
    html = html.replace(
        "Удалить</button></td>", 
        "Удалить</button> <button style='background:#6c757d; color:#fff; border:none; padding:8px 16px; border-radius:4px; cursor:pointer; margin-left:5px;' onclick='changeDeskPwd(${d.id})' title='Сменить пароль'>🔑</button></td>"
    )

# Добавляем JS-функцию для смены пароля
if 'changeDeskPwd' not in html:
    new_script = """
    async function changeDeskPwd(id) {
        const np = prompt("Введите новый пароль для этой кассы:");
        if(np) {
            await fetch(`/api/cash_desks/${id}/password`, {
                method: 'PUT', 
                headers: {'Content-Type': 'application/json'}, 
                body: JSON.stringify({password: np})
            });
            alert("Пароль успешно изменен!");
        }
    }
    """
    html = html.replace("async function deleteCashDesk", new_script + "\n    async function deleteCashDesk")

with open(path, 'w', encoding='utf-8') as f:
    f.write(html)
print(f"✅ Файл {path} успешно обновлен (добавлены пароли)!")
