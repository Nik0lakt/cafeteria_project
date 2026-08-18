from app.security import create_access_token, hash_password, verify_password


class TestAuth:
    def test_login_success(self, client):
        import os
        password = "test_admin_pass"
        hashed = hash_password(password)
        os.environ["ADMIN_PASSWORD_HASH"] = hashed
        resp = client.post("/api/login", json={"password": password})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "token" in data

    def test_login_wrong_password(self, client):
        import os
        os.environ["ADMIN_PASSWORD_HASH"] = hash_password("correct")
        resp = client.post("/api/login", json={"password": "wrong"})
        data = resp.json()
        assert data["success"] is False

    def test_protected_endpoint_without_token(self, client):
        resp = client.get("/api/employees")
        assert resp.status_code == 401

    def test_protected_endpoint_with_valid_token(self, client):
        token = create_access_token({"sub": "admin", "role": "admin"})
        resp = client.get("/api/employees", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_protected_endpoint_with_invalid_token(self, client):
        resp = client.get("/api/employees", headers={"Authorization": "Bearer invalid.token.here"})
        assert resp.status_code == 401


class TestPasswordHashing:
    def test_hash_and_verify(self):
        password = "secure_password_123"
        hashed = hash_password(password)
        assert verify_password(password, hashed)
        assert not verify_password("wrong_password", hashed)

    def test_different_hashes_for_same_password(self):
        password = "same_password"
        h1 = hash_password(password)
        h2 = hash_password(password)
        assert h1 != h2
        assert verify_password(password, h1)
        assert verify_password(password, h2)
