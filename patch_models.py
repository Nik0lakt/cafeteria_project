import re
with open('app/models.py', 'r', encoding='utf-8') as f:
    content = f.read()

if 'cash_desk_id' not in content:
    if ' JSON' not in content:
        content = content.replace('from sqlalchemy import Column', 'from sqlalchemy import Column, JSON')
    
    pattern = r'(class Transaction\(Base\):.*?)(?=class \w+\(Base\):|$)'
    def replacer(match):
        block = match.group(1)
        # Делаем employee_id необязательным
        block = re.sub(r'employee_id = Column\(Integer, ForeignKey\("employees\.id"\)(, nullable=\w+)?\)', 'employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)', block)
        if 'nullable=True' not in block:
            block = block.replace('employee_id = Column(Integer, ForeignKey("employees.id"))', 'employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)')
        
        # Добавляем новые колонки
        new_cols = "\n    cash_desk_id = Column(String, index=True, nullable=True)\n    payment_method = Column(String, default=\"internal\")\n    items = Column(JSON, nullable=True)\n"
        return block + new_cols
        
    new_content = re.sub(pattern, replacer, content, flags=re.DOTALL)
    with open('app/models.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("✅ Файл app/models.py обновлен!")
else:
    print("ℹ️ Файл app/models.py уже содержит нужные изменения.")
