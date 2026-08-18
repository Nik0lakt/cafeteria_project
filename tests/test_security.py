import pytest

from app.security import create_access_token


class TestSecurityEndpoints:
    """Verify that protected endpoints reject unauthorized access."""

    PROTECTED_ENDPOINTS = [
        ("GET", "/api/employees"),
        ("POST", "/api/employees"),
        ("GET", "/api/role_settings"),
        ("POST", "/api/role_settings"),
        ("POST", "/api/cash_desks"),
        ("GET", "/api/statistics/chart?start_date=2024-01-01&end_date=2024-01-31"),
    ]

    @pytest.mark.parametrize("method,path", PROTECTED_ENDPOINTS)
    def test_protected_endpoints_reject_no_auth(self, client, method, path):
        if method == "GET":
            resp = client.get(path)
        else:
            resp = client.post(path, json={})
        assert resp.status_code == 401

    @pytest.mark.parametrize("method,path", PROTECTED_ENDPOINTS)
    def test_protected_endpoints_reject_bad_token(self, client, method, path):
        headers = {"Authorization": "Bearer fake.invalid.token"}
        if method == "GET":
            resp = client.get(path, headers=headers)
        else:
            resp = client.post(path, json={}, headers=headers)
        assert resp.status_code == 401

    def test_photo_access_requires_auth(self, client):
        resp = client.get("/api/photos/test.jpg")
        assert resp.status_code == 403

    def test_photo_access_with_admin_token(self, client):
        token = create_access_token({"sub": "admin", "role": "admin"})
        resp = client.get(f"/api/photos/test.jpg?token={token}")
        assert resp.status_code == 404  # authorized but file doesn't exist


class TestPublicEndpoints:
    """Verify that intentionally public endpoints stay public."""

    def test_app_settings_is_public(self, client):
        resp = client.get("/api/app_settings", headers={"Authorization": ""})
        assert resp.status_code == 200

    def test_employee_info_requires_terminal_token(self, client):
        anonymous = client.get("/api/employee_info?card_uid=NONEXIST", headers={"Authorization": ""})
        assert anonymous.status_code == 401

        terminal_token = create_access_token(
            {"sub": "terminal:desk1", "role": "terminal", "desk_login": "desk1"}
        )
        authorized = client.get(
            "/api/employee_info?card_uid=NONEXIST",
            headers={"Authorization": f"Bearer {terminal_token}"},
        )
        assert authorized.status_code == 404
