from sqlalchemy import Column, Integer, String, Float, LargeBinary, ForeignKey, Date, DateTime
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
    employee_id = Column(Integer, ForeignKey("employees.id"))
    amount_total_kopecks = Column(Integer)
    subsidy_part_kopecks = Column(Integer)
    limit_part_kopecks = Column(Integer)
    status = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

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
