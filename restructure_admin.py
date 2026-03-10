import re
import os

admin_path = 'admin.html' if os.path.exists('admin.html') else ('static/admin.html' if os.path.exists('static/admin.html') else None)

if admin_path:
    with open(admin_path, 'r', encoding='utf-8') as f:
        html = f.read()

    # Извлекаем все внутри <body>
    body_match = re.search(r'<body>(.*?)</body>', html, re.DOTALL | re.IGNORECASE)
    if body_match:
        body_content = body_match.group(1)
        
        # Разделяем скрипты и html
        scripts = re.findall(r'<script.*?</script>', body_content, re.DOTALL)
        body_no_scripts = re.sub(r'<script.*?</script>', '', body_content, flags=re.DOTALL)
        
        # Находим наш блок касс, который мы добавили в прошлый раз, и отделяем его от старого контента
        marker = ""
        if marker in body_no_scripts:
            parts = body_no_scripts.split(marker)
            employees_html = parts[0]
            cashdesks_html = marker + parts[1]
        else:
            employees_html = body_no_scripts
            cashdesks_html = ""

        # Собираем новый layout с боковой панелью
        new_layout = f"""
    <div class="d-flex vh-100 overflow-hidden">
        <div class="d-flex flex-column flex-shrink-0 p-3 text-white bg-dark" style="width: 250px;">
            <a href="/" class="d-flex align-items-center mb-4 text-white text-decoration-none border-bottom pb-3">
                <span class="fs-4">Админ-панель</span>
            </a>
            <ul class="nav nav-pills flex-column mb-auto" id="sidebarMenu">
                <li class="nav-item mb-2">
                    <a href="#" class="nav-link active" onclick="switchTab('employees', this)" style="cursor:pointer;">
                        👥 Сотрудники
                    </a>
                </li>
                <li class="nav-item">
                    <a href="#" class="nav-link text-white" onclick="switchTab('cashdesks', this)" style="cursor:pointer;">
                        🖥 Кассы
                    </a>
                </li>
            </ul>
        </div>
        
        <div class="p-4 w-100 overflow-auto bg-light">
            <div id="employeesTab">
                {employees_html}
            </div>
            <div id="cashdesksTab" style="display:none;">
                {cashdesks_html}
            </div>
        </div>
    </div>

    <script>
        function switchTab(tabId, element) {{
            // Скрываем все вкладки
            document.getElementById('employeesTab').style.display = 'none';
            document.getElementById('cashdesksTab').style.display = 'none';
            
            // Показываем нужную
            document.getElementById(tabId + 'Tab').style.display = 'block';
            
            // Меняем стили кнопок в меню
            const links = document.querySelectorAll('#sidebarMenu .nav-link');
            links.forEach(l => {{
                l.classList.remove('active');
                l.classList.add('text-white');
            }});
            element.classList.add('active');
            element.classList.remove('text-white');
        }}
    </script>
    {''.join(scripts)}
"""
        new_html = html.replace(body_match.group(0), f"<body>\n{new_layout}\n</body>")
        with open(admin_path, 'w', encoding='utf-8') as f:
            f.write(new_html)
        print("✅ admin.html успешно обновлен (интегрирована боковая панель)!")
else:
    print("❌ Файл admin.html не найден.")
