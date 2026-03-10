import os

admin_path = 'admin.html' if os.path.exists('admin.html') else ('static/admin.html' if os.path.exists('static/admin.html') else None)

if not admin_path:
    print("❌ Файл admin.html не найден!")
else:
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
        print(f"✅ Файл {admin_path} успешно обновлен (секция касс добавлена)!")
    else:
        print(f"ℹ️ Файл {admin_path} уже содержит секцию касс.")
