import os
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

SECRET_KEY = os.getenv("JWT_SECRET")
if not SECRET_KEY:
    raise RuntimeError("JWT_SECRET environment variable is not set")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24
TERMINAL_TOKEN_EXPIRE_HOURS = 12
EMPLOYEE_TOKEN_EXPIRE_HOURS = 1

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (TypeError, ValueError):
        return False


def create_access_token(data: dict[str, Any], expires_hours: int = ACCESS_TOKEN_EXPIRE_HOURS) -> str:
    to_encode = data.copy()
    to_encode["exp"] = datetime.now(timezone.utc) + timedelta(hours=expires_hours)
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def _credentials_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_payload(token: str = Depends(oauth2_scheme)) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise _credentials_exception() from exc

    if not payload.get("sub") or not payload.get("role"):
        raise _credentials_exception()
    return payload


def _require_role(payload: dict[str, Any], role: str) -> dict[str, Any]:
    if payload.get("role") != role:
        raise _credentials_exception()
    return payload


def get_current_admin(payload: dict[str, Any] = Depends(get_current_payload)) -> dict[str, Any]:
    return _require_role(payload, "admin")


def get_current_terminal(payload: dict[str, Any] = Depends(get_current_payload)) -> dict[str, Any]:
    terminal = _require_role(payload, "terminal")
    if not terminal.get("desk_login"):
        raise _credentials_exception()
    return terminal


def get_current_employee(payload: dict[str, Any] = Depends(get_current_payload)) -> dict[str, Any]:
    employee = _require_role(payload, "employee")
    if not isinstance(employee.get("employee_id"), int):
        raise _credentials_exception()
    return employee


def assert_terminal_for_desk(payload: dict[str, Any], desk_login: str) -> None:
    if payload.get("role") != "terminal" or payload.get("desk_login") != desk_login:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Terminal is not authorized for this cash desk")


def assert_employee_identity(payload: dict[str, Any], employee_id: int) -> None:
    if payload.get("employee_id") != employee_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access to another employee is forbidden")
