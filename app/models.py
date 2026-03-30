from datetime import datetime
from datetime import datetime
from sqlalchemy import Column, JSON, Integer, String, Float, LargeBinary, ForeignKey, Date, DateTime, Table
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class Employee(Base):
    __tablename__ = "employees"
    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String)
    role = Column(String)
    month_limit_rub = Column(Float)
    face_embedding = Column(LargeBinary, nullable=True)
    telegram_id = Column(String, nullable=True)
    work_days = relationship("WorkDay", back_populates="employee")

class Card(Base):
    __tablename__ = "cards"
    id = Column(Integer, primary_key=True, index=True)
    uid = Column(String, unique=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"))

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    employee = relationship("Employee")
    amount_total_kopecks = Column(Integer)
    subsidy_part_kopecks = Column(Integer)
    limit_part_kopecks = Column(Integer)
    status = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


    cash_desk_id = Column(String, index=True, nullable=True)
    payment_method = Column(String, default="internal")
    items = Column(JSON, nullable=True)
class WorkDay(Base):
    __tablename__ = "work_days"
    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"))
    date = Column(Date, index=True)
    employee = relationship("Employee", back_populates="work_days")

class RoleSetting(Base):
    __tablename__ = "role_settings"
    id = Column(Integer, primary_key=True, index=True)
    role_name = Column(String, unique=True)
    subsidy_rub = Column(Float, default=0.0)

class LivenessSession(Base):
    __tablename__ = "liveness_sessions"
    id = Column(String, primary_key=True, index=True)
    card_uid = Column(String)
    timestamp = Column(DateTime, default=datetime.now)

class CashDesk(Base):
    __tablename__ = 'cash_desks'
    id = Column(Integer, primary_key=True, index=True)
    login = Column(String, unique=True, index=True)
    description = Column(String, nullable=True)
    password = Column(String, default='1234')
    
    # Связь через промежуточный класс
    products_association = relationship("CashDeskProduct", back_populates="cash_desk")

class Category(Base):
    __tablename__ = 'categories'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    cash_desk_id = Column(Integer, ForeignKey('cash_desks.id'))

class Product(Base):
    __tablename__ = 'products'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    price = Column(Integer) # Базовая цена
    category_id = Column(Integer, ForeignKey('categories.id'))
    
    # Связь через промежуточный класс
    cash_desks_association = relationship("CashDeskProduct", back_populates="product")

class CashDeskProduct(Base):
    __tablename__ = "cash_desk_products"
    cash_desk_id = Column(Integer, ForeignKey('cash_desks.id'), primary_key=True)
    product_id = Column(Integer, ForeignKey('products.id'), primary_key=True)
    price = Column(Integer, nullable=False, default=0) # Цена именно для этой кассы

    # Добавляем связи, чтобы удобно было доставать данные
    cash_desk = relationship("CashDesk", back_populates="products_association")
    product = relationship("Product", back_populates="cash_desks_association")


