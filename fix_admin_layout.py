import os, re

path = 'admin.html' if os.path.exists('admin.html') else ('static/admin.html' if os.path.exists('static/admin.html') else None)

if not path:
    print("❌ Файл admin.html не найден!")
    exit(1)

with open(path, 'r', encoding='utf-8') as f:
    html = f.read()

body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL | re.IGNORECASE)
body_inner = body_match.group(1) if body_match else html

# Очищаем от старых скриптов касс, чтобы не дублировать
body_inner = re.sub(r'<script>\s*function switchTab.*?</script>', '', body_inner, flags=re.DOTALL)
body_inner = re.sub(r'<script>\s*async function loadCashDesks.*?</script>', '', body_inner, flags=re.DOTALL)

# Если макет уже применялся, вытаскиваем чистый контент
if 'id="tab-content-emp"' in body_inner:
    emp_match = re.search(r'<div id="tab-content-emp">(.*?)</div>\s*<div id="tab-content-cash"', body_inner, re.DOTALL)
    cash_match = re.search(r'<div id="tab-content-cash"[^>]*>(.*?)</div>\s*</div>\s*</div>', body_inner, re.DOTALL)
    if emp_match: body_inner = emp_match.group(1) + "\n" + (cash_match.group(1) if cash_match else "")

# Разделяем контент
cash_idx = body_inner.find('Управление кассами')
if cash_idx != -1:
    split_idx = body_inner.rfind('<div class="container', 0, cash_idx)
    if split_idx == -1: split_idx = body_inner.rfind('<hr>', 0, cash_idx)
    if split_idx == -1: split_idx = cash_idx
    emp_html = body_inner[:split_idx].strip()
    cash_html = body_inner[split_idx:].strip()
else:
    emp_html = body_inner
    cash_html = """
    <div style="max-width: 800px;">
        <h2 style="margin-bottom: 20px; font-family: sans-serif;">Управление кассами (Логины)</h2>
        <div style="border: 1px solid #eaeaea; padding: 20px; border-radius: 8px; margin-bottom: 30px;">
            <p style="margin-top:0; font-weight:bold;">Создать новый логин кассы</p>
            <div style="display: flex; gap: 10px; margin-bottom: 15px;">
                <input type="text" id="newDeskLogin" placeholder="Логин (например, kassa1)" style="flex: 1; padding: 12px; border: 1px solid #ccc; border-radius: 6px;">
                <input type="text" id="newDeskDesc" placeholder="Описание (Главная касса)" style="flex: 1; padding: 12px; border: 1px solid #ccc; border-radius: 6px;">
            </div>
            <button onclick="addCashDesk()" style="background: #000; color: #fff; border: none; padding: 12px; border-radius: 6px; cursor: pointer; width: 100%; font-weight: bold;">Создать кассу</button>
        </div>
        <table style="width: 100%; border-collapse: collapse; text-align: left; font-family: sans-serif;">
            <tr style="border-bottom: 2px solid #000;">
                <th style="padding: 12px 8px;">ID</th><th style="padding: 12px 8px;">Логин</th><th style="padding: 12px 8px;">Описание</th><th style="padding: 12px 8px;">Действия</th>
            </tr>
            <tbody id="cashDesksTableBody"></tbody>
        </table>
    </div>
    """

scripts = """
<script>
    function switchTab(tab) {
        document.getElementById('tab-content-emp').style.display = tab === 'emp' ? 'block' : 'none';
        document.getElementById('tab-content-cash').style.display = tab === 'cash' ? 'block' : 'none';
        document.getElementById('tab-btn-emp').style.background = tab === 'emp' ? '#000' : 'transparent';
        document.getElementById('tab-btn-emp').style.color = tab === 'emp' ? '#fff' : '#555';
        document.getElementById('tab-btn-cash').style.background = tab === 'cash' ? '#000' : 'transparent';
        document.getElementById('tab-btn-cash').style.color = tab === 'cash' ? '#fff' : '#555';
    }
    async function loadCashDesks() {
        try {
            const res = await fetch('/api/cash_desks');
            const desks = await res.json();
            document.getElementById('cashDesksTableBody').innerHTML = desks.map(d => `
                <tr style="border-bottom: 1px solid #eaeaea;">
                    <td style="padding: 12px 8px;">${d.id}</td>
                    <td style="padding: 12px 8px;"><b>${d.login}</b></td>
                    <td style="padding: 12px 8px;">${d.description || ''}</td>
                    <td style="padding: 12px 8px;"><button style="background:#dc3545; color:#fff; border:none; padding:6px 12px; border-radius:4px; cursor:pointer;" onclick="deleteCashDesk(${d.id})">Удалить</button></td>
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
</script>
"""

new_body = f"""
<div style="display: flex; height: 100vh; overflow: hidden; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
    <div style="width: 250px; background: #fcfcfc; border-right: 1px solid #eaeaea; display: flex; flex-direction: column; padding: 20px; flex-shrink: 0;">
        <div style="font-size: 20px; font-weight: bold; margin-bottom: 30px; padding-bottom: 15px; border-bottom: 1px solid #eaeaea; color: #000;">
            Админ-панель
        </div>
        <div id="tab-btn-emp" onclick="switchTab('emp')" style="padding: 12px 15px; background: #000; color: #fff; border-radius: 8px; cursor: pointer; margin-bottom: 10px; font-weight: 500; transition: 0.2s;">
            Сотрудники
        </div>
        <div id="tab-btn-cash" onclick="switchTab('cash')" style="padding: 12px 15px; background: transparent; color: #555; border-radius: 8px; cursor: pointer; font-weight: 500; transition: 0.2s;">
            Кассы терминалов
        </div>
    </div>
    
    <div style="flex: 1; overflow-y: auto; padding: 40px; background: #fff;">
        <div id="tab-content-emp">
            {emp_html}
        </div>
        <div id="tab-content-cash" style="display: none;">
            {cash_html}
        </div>
    </div>
</div>
{scripts}
"""

if body_match:
    new_html = html.replace(body_match.group(0), f"<body>\n{new_body}\n</body>")
else:
    new_html = html + new_body

with open(path, 'w', encoding='utf-8') as f:
    f.write(new_html)

print("✅ admin.html: Макет успешно обновлен (Боковое меню добавлено!)")
