import pytest

from app.models import Card, CashDesk, CashDeskProduct, Category, Employee, Product
from app.security import create_access_token


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def security_setup(db):
    desk = CashDesk(login="desk1", description="Main desk")
    employee = Employee(full_name="Employee One", role="developer", month_limit_kopecks=10_000)
    other_employee = Employee(full_name="Employee Two", role="developer", month_limit_kopecks=10_000)
    db.add_all([desk, employee, other_employee])
    db.flush()

    db.add_all([
        Card(uid="CARD-ONE", employee_id=employee.id),
        Card(uid="CARD-TWO", employee_id=other_employee.id),
    ])
    category = Category(name="Meals", cash_desk_id=desk.id)
    db.add(category)
    db.flush()
    product = Product(name="Soup", price=100, category_id=category.id)
    db.add(product)
    db.flush()
    db.add(CashDeskProduct(cash_desk_id=desk.id, product_id=product.id, price=100))
    db.commit()

    return {"desk": desk, "employee": employee, "other_employee": other_employee, "category": category, "product": product}


class TestAuthorizationRegression:
    def test_menu_mutation_requires_admin(self, client, security_setup):
        payload = {"name": "Unauthorized", "cash_desk_id": security_setup["desk"].id}

        anonymous = client.post("/api/categories", json=payload, headers={"Authorization": ""})
        assert anonymous.status_code == 401

        terminal = client.post("/api/categories", json=payload)
        assert terminal.status_code == 401

        admin = create_access_token({"sub": "admin", "role": "admin"})
        allowed = client.post("/api/categories", json=payload, headers=bearer(admin))
        assert allowed.status_code == 200

    def test_employee_cannot_read_or_modify_another_employee(self, client, security_setup):
        employee = security_setup["employee"]
        other_employee = security_setup["other_employee"]
        own_token = create_access_token(
            {"sub": f"employee:{employee.id}", "role": "employee", "employee_id": employee.id}
        )

        own_data = client.get(f"/api/user/full_data/{employee.id}", headers=bearer(own_token))
        assert own_data.status_code == 200

        other_data = client.get(f"/api/user/full_data/{other_employee.id}", headers=bearer(own_token))
        assert other_data.status_code == 403

        anonymous = client.post(
            f"/api/user/toggle_notifications/{employee.id}", headers={"Authorization": ""}
        )
        assert anonymous.status_code == 401

    def test_external_payment_requires_matching_terminal(self, client, security_setup):
        desk = security_setup["desk"]
        product = security_setup["product"]
        payload = {
            "cash_desk_id": desk.login,
            "items": [{"product_id": product.id, "quantity": 1}],
            "payment_method": "cash",
        }

        anonymous = client.post("/api/pay_external", json=payload, headers={"Authorization": ""})
        assert anonymous.status_code == 401

        wrong_terminal = create_access_token(
            {"sub": "terminal:other", "role": "terminal", "desk_login": "other"}
        )
        forbidden = client.post("/api/pay_external", json=payload, headers=bearer(wrong_terminal))
        assert forbidden.status_code == 403

        own_terminal = create_access_token(
            {"sub": f"terminal:{desk.login}", "role": "terminal", "desk_login": desk.login}
        )
        allowed = client.post("/api/pay_external", json=payload, headers=bearer(own_terminal))
        assert allowed.status_code == 200

    def test_order_quantity_must_be_positive(self, client, security_setup):
        desk = security_setup["desk"]
        product = security_setup["product"]
        payload = {
            "cash_desk_id": desk.login,
            "items": [{"product_id": product.id, "quantity": 0}],
            "payment_method": "cash",
        }
        response = client.post("/api/pay_external", json=payload)
        assert response.status_code == 422
