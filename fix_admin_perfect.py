import os, re

path = 'admin.html' if os.path.exists('admin.html') else ('static/admin.html' if os.path.exists('static/admin.html') else None)

with open(path, 'r', encoding='utf-8') as f:
    html = f.read()

# Если меню уже есть, ничего не делаем
if 'app-sidebar' in html:
    print("✅ Меню уже установлено!")
    exit(0)

# Берем абсолютно весь твой рабочий контент внутри body
body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL | re.IGNORECASE)
original_body = body_match.group(1) if body_match else html

# Вкладка "Кассы" (Строгий дизайн)
cash_html = """
<div style="background: #fff; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); max-width: 1000px; margin: 0 auto;">
    <h2 style="margin-top: 0; margin-bottom: 20px; font-family: sans-serif;">Управление терминалами</h2>
    <div style="border: 1px solid #eaeaea; padding: 20px; border-radius: 8px; margin-bottom: 30px;">
        <p style="margin-top:0; font-weight:bold; font-family: sans-serif;">Создать новый логин кассы</p>
        <div style="display: flex; gap: 10px; margin-bottom: 15px;">
            <input type="text" id="newDeskLogin" placeholder="Логин (например, kassa1)" style="flex: 1; padding: 12px; border: 1px solid #ccc; border-radius: 4px; font-size: 16px;">
            <input type="text" id="newDeskDesc" placeholder="Описание (Главная касса)" style="flex: 1; padding: 12px; border: 1px solid #ccc; border-radius: 4px; font-size: 16px;">
        </div>
        <button onclick="addCashDesk()" style="background: #000; color: #fff; border: none; padding: 12px; border-radius: 6px; cursor: pointer; width: 100%; font-weight: bold; font-size: 16px;">Создать</button>
    </div>
    <table style="width: 100%; border-collapse: collapse; text-align: left; font-family: sans-serif;">
        <tr style="border-bottom: 2px solid #000;">
            <th style="padding: 15px 10px;">ID</th><th style="padding: 15px 10px;">Логин</th><th style="padding: 15px 10px;">Описание</th><th style="padding: 15px 10px;">Действия</th>
        </tr>
        <tbody id="cashDesksTableBody"></tbody>
    </table>
</div>
"""

cash_scripts = """
<script>
    async function loadCashDesks() {
        try {
            const res = await fetch('/api/cash_desks');
            const desks = await res.json();
            document.getElementById('cashDesksTableBody').innerHTML = desks.map(d => `
                <tr style="border-bottom: 1px solid #eaeaea;">
                    <td style="padding: 15px 10px;">${d.id}</td>
                    <td style="padding: 15px 10px;"><b>${d.login}</b></td>
                    <td style="padding: 15px 10px;">${d.description || ''}</td>
                    <td style="padding: 15px 10px;"><button style="background:#000; color:#fff; border:none; padding:8px 16px; border-radius:4px; cursor:pointer;" onclick="deleteCashDesk(${d.id})">Удалить</button></td>
                </tr>
            `).join('');
        } catch(e) {}
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

    function switchTab(tabId, element) {
        document.getElementById('tab-emp').style.display = tabId === 'emp' ? 'block' : 'none';
        document.getElementById('tab-cash').style.display = tabId === 'cash' ? 'block' : 'none';
        document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
        element.classList.add('active');
    }
</script>
"""

new_layout = f"""
<style>
    body {{ margin: 0; padding: 0; background: #f4f6f9; overflow-x: hidden; font-family: -apple-system, sans-serif; }}
    
    /* Темная панель (Скрывается / Выезжает при наведении) */
    .app-sidebar {{
        position: fixed; top: 0; left: 0; height: 100vh; width: 60px;
        background: #111; color: #fff; transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        overflow: hidden; white-space: nowrap; z-index: 9999;
        box-shadow: 2px 0 15px rgba(0,0,0,0.2);
    }}
    .app-sidebar:hover {{ width: 250px; }}
    
    .nav-header {{ padding: 20px; font-size: 18px; font-weight: bold; border-bottom: 1px solid #333; margin-bottom: 10px; display: flex; align-items: center; color: #fff; }}
    .nav-item {{ padding: 15px 20px; cursor: pointer; display: flex; align-items: center; color: #aaa; transition: 0.2s; font-size: 16px; }}
    .nav-item:hover, .nav-item.active {{ background: #222; color: #fff; border-left: 4px solid #fff; padding-left: 16px; }}
    
    .nav-icon {{ font-size: 20px; min-width: 30px; text-align: left; }}
    .nav-text {{ margin-left: 10px; opacity: 0; transition: opacity 0.3s; }}
    .app-sidebar:hover .nav-text {{ opacity: 1; }}
    
    .main-content {{ margin-left: 60px; padding: 20px; min-height: 100vh; transition: margin-left 0.3s; }}
</style>

<div class="app-sidebar">
    <div class="nav-header">
        <span class="nav-icon">⚙️</span><span class="nav-text">Админ-панель</span>
    </div>
    <div class="nav-item active" onclick="switchTab('emp', this)">
        <span class="nav-icon">👥</span><span class="nav-text">Сотрудники</span>
    </div>
    <div class="nav-item" onclick="switchTab('cash', this)">
        <span class="nav-icon">🖥</span><span class="nav-text">Кассы терминалов</span>
    </div>
</div>

<div class="main-content">
    <div id="tab-emp">
        {original_body}
    </div>
    <div id="tab-cash" style="display: none;">
        {cash_html}
    </div>
</div>
{cash_scripts}
"""

new_html = html.replace(body_match.group(0), f"<body>\n{new_layout}\n</body>")
with open(path, 'w', encoding='utf-8') as f:
    f.write(new_html)
print("✅ Успех! Оригинальный контент обернут в новую боковую панель.")
