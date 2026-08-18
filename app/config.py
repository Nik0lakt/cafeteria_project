import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
PRIVATE_PHOTOS_DIR = Path(
    os.getenv("PRIVATE_PHOTOS_DIR", str(BASE_DIR / "data" / "private_photos"))
).resolve()


def cors_origins() -> list[str]:
    raw_origins = os.getenv("CORS_ORIGINS", "http://localhost:8000,http://localhost:3000")
    return [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
