from datetime import date

import pytest

from app.models import (
    AppSetting,
    Card,
    CashDesk,
    CashDeskProduct,
    Category,
    Employee,
    LivenessSession,
    Product,
    RoleSetting,
    WorkDay,
)


@pytest.fixture
def sample_employee(db):
    emp = Employee(full_name="Иванов Иван", role="developer", month_limit_kopecks=500000)
    db.add(emp)
    db.commit()
    db.refresh(emp)
    return emp


@pytest.fixture
def sample_card(db, sample_employee):
    card = Card(uid="ABC123", employee_id=sample_employee.id)
    db.add(card)
    db.commit()
    return card


@pytest.fixture
def sample_role(db):
    role = RoleSetting(role_name="developer", subsidy_rub=200.0)
    db.add(role)
    db.commit()
    return role


@pytest.fixture
def sample_work_day(db, sample_employee):
    wd = WorkDay(employee_id=sample_employee.id, date=date.today())
    db.add(wd)
    db.commit()
    return wd


@pytest.fixture
def sample_cash_desk(db):
    desk = CashDesk(login="desk1", description="Main desk")
    db.add(desk)
    db.commit()
    db.refresh(desk)
    return desk


@pytest.fixture
def sample_product_setup(db, sample_cash_desk):
    cat = Category(name="Обеды", cash_desk_id=sample_cash_desk.id)
    db.add(cat)
    db.commit()
    db.refresh(cat)
    prod = Product(name="Борщ", price=150, category_id=cat.id)
    db.add(prod)
    db.commit()
    db.refresh(prod)
    mapping = CashDeskProduct(cash_desk_id=sample_cash_desk.id, product_id=prod.id, price=150)
    db.add(mapping)
    db.commit()
    return {"category": cat, "product": prod, "desk": sample_cash_desk}


@pytest.fixture
def liveness_session(db, sample_card):
    sess = LivenessSession(id="test-session-1", card_uid=sample_card.uid, passed=True)
    db.add(sess)
    db.commit()
    return sess


@pytest.fixture
def full_payment_setup(db, sample_employee, sample_card, sample_role, sample_work_day, sample_product_setup, liveness_session):
    db.add(AppSetting(key="manual_payment_use_subsidy", value="true"))
    db.commit()
    return {
        "employee": sample_employee,
        "card": sample_card,
        "product": sample_product_setup["product"],
        "desk": sample_product_setup["desk"],
        "session": liveness_session,
    }


class TestPayment:
    def test_successful_payment_with_subsidy(self, client, full_payment_setup):
        setup = full_payment_setup
        resp = client.post("/api/pay", json={
            "session_id": setup["session"].id,
            "items": [{"product_id": setup["product"].id, "quantity": 1}],
            "cash_desk_id": setup["desk"].login,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"

    def test_payment_insufficient_funds(self, client, db, full_payment_setup):
        setup = full_payment_setup
        setup["employee"].month_limit_kopecks = 0
        # Remove work day so no subsidy is available
        from app.models import WorkDay
        db.query(WorkDay).filter(WorkDay.employee_id == setup["employee"].id).delete()
        db.commit()
        resp = client.post("/api/pay", json={
            "session_id": setup["session"].id,
            "items": [{"product_id": setup["product"].id, "quantity": 1}],
            "cash_desk_id": setup["desk"].login,
        })
        assert resp.status_code == 400
        assert "средств" in resp.json()["detail"]

    def test_payment_without_liveness_rejected(self, client, db, full_payment_setup):
        setup = full_payment_setup
        sess = db.query(LivenessSession).filter(LivenessSession.id == setup["session"].id).first()
        sess.passed = False
        db.commit()
        resp = client.post("/api/pay", json={
            "session_id": setup["session"].id,
            "items": [{"product_id": setup["product"].id, "quantity": 1}],
            "cash_desk_id": setup["desk"].login,
        })
        assert resp.status_code == 403

    def test_manual_payment_allowed_without_liveness(self, client, db, full_payment_setup):
        setup = full_payment_setup
        sess = db.query(LivenessSession).filter(LivenessSession.id == setup["session"].id).first()
        sess.passed = False
        db.commit()
        resp = client.post("/api/pay", json={
            "session_id": setup["session"].id,
            "items": [{"product_id": setup["product"].id, "quantity": 1}],
            "is_manual": True,
            "cash_desk_id": setup["desk"].login,
        })
        assert resp.status_code == 200
