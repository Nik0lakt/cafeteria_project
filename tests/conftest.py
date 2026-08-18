import os
import sys
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("JWT_SECRET", "test-secret-key-for-testing")
os.environ.setdefault("ADMIN_PASSWORD_HASH", "$2b$12$LJ3m4sMKfXzSGqXFqXKYXe8XxYXzGqXFqXKYXe8XxYXzGqXFqXKYXe")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")

# Mock heavy CV dependencies before any app import
mock_face_recognition = MagicMock()
mock_cv2 = MagicMock()
sys.modules["face_recognition"] = mock_face_recognition
sys.modules["cv2"] = mock_cv2

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.security import create_access_token

SQLALCHEMY_TEST_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_TEST_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db):
    from app.main import app

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        terminal_token = create_access_token(
            {"sub": "terminal:desk1", "role": "terminal", "desk_login": "desk1"}
        )
        c.headers.update({"Authorization": f"Bearer {terminal_token}"})
        yield c
    app.dependency_overrides.clear()
