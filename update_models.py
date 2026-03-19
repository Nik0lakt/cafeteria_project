with open('app/models.py', 'r', encoding='utf-8') as f:
    content = f.read()

if 'class Category(Base):' not in content:
    new_models = """
class Category(Base):
    __tablename__ = 'categories'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True)

class Product(Base):
    __tablename__ = 'products'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    price = Column(Integer)
    category_id = Column(Integer, ForeignKey('categories.id'))
"""
    content += new_models
    
    # Добавляем пароль в CashDesk
    content = content.replace("description = Column(String, nullable=True)", "description = Column(String, nullable=True)\n    password = Column(String, default='1234')")
    
    with open('app/models.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("✅ app/models.py обновлен!")
