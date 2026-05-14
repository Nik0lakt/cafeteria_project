from datetime import datetime
from sqlalchemy import Column, JSON, Integer, BigInteger, String, Float, Boolean, ForeignKey, Date, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Employee(Base):
    __tablename__ = "employees"
    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String)
    role = Column(String)
    month_limit_kopecks = Column(BigInteger, default=500000)
    face_embedding_json = Column(JSON, nullable=True)
    telegram_id = Column(String, nullable=True)
    notifications_enabled = Column(Boolean, default=True)
    limit_reset_day = Column(Integer, default=28)
    web_login = Column(String, unique=True, nullable=True)
    hashed_password = Column(String, nullable=True)
    is_first_login = Column(Boolean, default=True)
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
    amount_total_kopecks = Column(BigInteger)
    subsidy_part_kopecks = Column(BigInteger)
    limit_part_kopecks = Column(BigInteger)
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
    passed = Column(Boolean, default=False, nullable=False)
    embedding_json = Column(JSON, nullable=True)
    blink_count = Column(Integer, default=0, nullable=False)
    eye_closed = Column(Boolean, default=False, nullable=False)
    last_ear = Column(Float, nullable=True)
    min_ear_closed = Column(Float, nullable=True)  # минимум EAR за время текущего закрытия — отсеивает неглубокие ложные морганя


class CashDesk(Base):
    __tablename__ = "cash_desks"
    id = Column(Integer, primary_key=True, index=True)
    login = Column(String, unique=True, index=True)
    description = Column(String, nullable=True)
    hashed_password = Column(String, nullable=True)
    assigned_cashier_logins = Column(JSON, nullable=True)
    last_seen = Column(DateTime, nullable=True)
    products_association = relationship("CashDeskProduct", back_populates="cash_desk")


class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    cash_desk_id = Column(Integer, ForeignKey("cash_desks.id"))


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    price = Column(Integer)
    category_id = Column(Integer, ForeignKey("categories.id"))
    cash_desks_association = relationship("CashDeskProduct", back_populates="product")


class CashDeskProduct(Base):
    __tablename__ = "cash_desk_products"
    cash_desk_id = Column(Integer, ForeignKey("cash_desks.id"), primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), primary_key=True)
    price = Column(Integer, nullable=False, default=0)
    cash_desk = relationship("CashDesk", back_populates="products_association")
    product = relationship("Product", back_populates="cash_desks_association")


class AppSetting(Base):
    __tablename__ = "app_settings"
    key = Column(String, primary_key=True)
    value = Column(String, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    admin_username = Column(String)
    action = Column(String)
    entity = Column(String)
    entity_id = Column(Integer, nullable=True)
    details = Column(JSON, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
