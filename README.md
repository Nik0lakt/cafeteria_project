# Cafeteria — Corporate Dining Management System

> [Читать на русском](README_RU.md)

A full-stack B2B platform for automating corporate cafeteria operations. Combines NFC card identification, real-time face liveness verification, and a role-based subsidy engine — all managed through a single-page admin panel and a Telegram bot.

---

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Security Standards](#security-standards)
- [Tech Stack](#tech-stack)
- [Architecture](#architecture)
- [Database Schema](#database-schema)
- [Installation & Setup](#installation--setup)
- [Environment Variables](#environment-variables)
- [Hardware Integration](#hardware-integration)
- [API Reference](#api-reference)

---

## Overview

Cafeteria eliminates cashier errors and subsidy misuse by automating the entire lunch payment flow:

1. Employee taps NFC card → system loads their profile
2. Liveness check runs via webcam (face_recognition + MediaPipe) → identity confirmed
3. Subsidy and personal limit calculated in real-time → payment approved
4. Telegram notification sent to employee; audit report sent to admin (for manual confirmations)

The platform supports multiple POS terminals, each with independent menus and product catalogs. All financial calculations are performed in integer kopecks (BigInt) to avoid floating-point drift.

---

## Key Features

### Biometric Payment (Face ID)

- Real-time face liveness check using webcam stream, preventing photo spoofing
- Face embeddings stored as JSON vectors — no pickle files, no binary blobs
- Manual fallback: cashier can visually compare a database photo against the live camera feed
- Session-based flow: each payment attempt creates a `LivenessSession` record tied to the card UID

### Multi-Terminal Support

- Unlimited POS terminals (cash desks), each with a unique login and password
- Per-desk product catalogs: different menus can be assigned to different terminals
- Individual product categories per desk
- Statistics filtered by terminal in the admin panel

### Role-Based Subsidy Engine

- Daily subsidy amount defined per role (e.g., Worker: 150 ₽/day, Manager: 200 ₽/day)
- Subsidy is only applied on scheduled work days (per-employee calendar)
- If the order total exceeds the daily subsidy, the remainder is charged to the employee's monthly limit
- Monthly limit reset day is configurable per employee (default: 28th of each month)
- All balances stored in kopecks (BigInt) for exact arithmetic

### Telegram Bot

- Employees can check their daily subsidy balance and monthly limit with `/my`
- Instant payment receipt sent after each successful transaction
- Admin receives a dual-photo audit report (database photo + live camera frame) for every manual confirmation
- Bot runs as a background polling thread alongside the FastAPI server

### Admin Panel

- Single-page application protected by JWT (HS256, 8-hour sessions, daily rotation)
- Employee management: create, edit, delete; upload or capture biometric photos
- Per-employee work schedule calendar with preset shift patterns (5/2, 2/2, custom)
- Role and subsidy configuration
- Revenue statistics chart with filters by period, terminal, and payment method
- CSV export of transaction history
- RFID scanner connection (Web Serial API) with live UID test field

### Employee Self-Service Portal

- Web login at `/cabinet.html` — employees log in with a personal password
- View current monthly limit, daily subsidy, and today's spending
- First-login password change flow

---

## Security Standards

| Control | Implementation |
|---|---|
| **Authentication** | JWT HS256 via `python-jose`; 8-hour expiry; daily session invalidation on re-login |
| **Password hashing** | bcrypt via `passlib`/`bcrypt`; per-employee and per-admin hashes |
| **Financial precision** | All monetary values stored as `BIGINT` kopecks; no floats in payment paths |
| **Face data** | 128-dimensional vectors stored as `JSON`; no pickle serialization |
| **Database isolation** | PostgreSQL runs inside Docker bridge network; not exposed on host |
| **Input validation** | Pydantic schemas on all write endpoints; empty-field checks on employee creation |
| **Audit trail** | Manual payments trigger dual-photo Telegram reports to admin chat |

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | Python 3.10, FastAPI 0.95, Uvicorn |
| **Database ORM** | SQLAlchemy 2.0, psycopg2 |
| **Database** | PostgreSQL 13 |
| **Validation** | Pydantic 1.10 |
| **Auth** | python-jose (JWT HS256), bcrypt |
| **Biometrics** | face_recognition 1.3, OpenCV (headless), MediaPipe |
| **Frontend** | Vanilla JS, Web Serial API, WebRTC (getUserMedia) |
| **UI Icons** | Phosphor Icons 2.1 |
| **Telegram Bot** | aiogram (long-polling, background thread) |
| **Reverse Proxy** | Caddy 2 (automatic HTTPS) |
| **Containerization** | Docker, Docker Compose |
| **Hardware** | Arduino Uno + PN532 NFC module (I2C) |

---

## Architecture

```
Browser (Chrome)
    │
    ├── Web Serial API ──► Arduino/PN532 (RFID reader)
    │
    └── HTTPS ──► Caddy (reverse proxy, TLS termination)
                      │
                      └── FastAPI (Uvicorn, port 8000)
                              │
                              ├── /api/auth      — employee & admin auth, JWT
                              ├── /api/liveness  — face session management
                              ├── /api/payment   — order processing, subsidy calculation
                              ├── /api/bot       — Telegram bot polling (background thread)
                              │
                              └── PostgreSQL (Docker bridge network)
```

**Live-sync development**: `app/` and `static/` are Docker volume-mounted, so code changes apply without rebuilding the image.

---

## Database Schema

| Table | Purpose |
|---|---|
| `employees` | Full name, role, Telegram ID, face embedding (JSON), monthly limit (kopecks), limit reset day, web login/password hash |
| `cards` | Maps NFC card UID → employee ID |
| `transactions` | Payment history: total amount, subsidy portion, limit portion, payment method, items (JSON), cash desk ID |
| `role_settings` | Daily subsidy amount per role name |
| `work_days` | Per-employee scheduled work days (subsidy eligibility) |
| `cash_desks` | Terminal login, description, hashed password |
| `categories` | Product categories, scoped to a cash desk |
| `products` | Product name and base price |
| `cash_desk_products` | Per-terminal price overrides for products |
| `liveness_sessions` | Short-lived face verification session records |

---

## Installation & Setup

### Prerequisites

- Docker Engine 24+
- Docker Compose v2
- Chrome/Edge browser (Web Serial API required for RFID)

### 1. Clone and configure

```bash
git clone <repository-url>
cd cafeteria_project
cp .env.example .env
```

### 2. Generate secrets

```bash
# JWT secret (minimum 32 characters)
python3 -c "import secrets; print(secrets.token_hex(32))"

# Admin password hash
python3 -c "from passlib.hash import bcrypt; print(bcrypt.hash('your_password'))"
```

Fill in `.env` with the generated values (see [Environment Variables](#environment-variables) below).

### 3. Build and start

```bash
docker compose up -d --build
```

The application will be available at:
- `http://localhost:8000` — direct (no TLS)
- Your configured Caddy domain — with automatic HTTPS

### 4. First run

On first startup, `main.py` automatically runs schema migrations via `update_db_schema()` — no manual migration step needed.

Open the admin panel at `/login.html`, enter your admin password, and:
1. Add roles and set subsidy amounts
2. Register employees and assign NFC cards
3. Create cash desk terminals
4. Enroll employee face photos via the admin panel camera or file upload

---

## Environment Variables

Copy `.env.example` to `.env` and fill in all values:

```env
# PostgreSQL connection (must match docker-compose.yml)
DATABASE_URL=postgresql://user:password@db:5432/cafeteria_db

# Telegram bot (get token from @BotFather)
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here

# Admin Telegram chat ID for audit reports
ADMIN_CHAT_ID=your_admin_chat_id_here

# JWT signing secret — minimum 32 random characters
JWT_SECRET=change_me_to_a_long_random_secret_key_min_32_chars

# Bcrypt hash of the admin panel password
ADMIN_PASSWORD_HASH=$2b$12$replacethiswitharealhashedpassword
```

---

## Hardware Integration

**RFID Reader setup:**

1. Connect an Arduino Uno with PN532 NFC module via I2C
2. Flash the Arduino with a sketch that reads card UIDs and outputs them to Serial at 9600 baud as `HEX_UID\n`
3. Connect the Arduino via USB to the machine running Chrome
4. In the admin panel → Settings tab, click **Connect Scanner** and select the COM port
5. The green indicator confirms connection; UIDs are routed automatically to the active input field

The system also works without hardware — employees can type or paste their UID manually.

---

## API Reference

All admin endpoints require `Authorization: Bearer <jwt_token>`.

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/login` | — | Admin login, returns JWT |
| `GET` | `/api/employees` | Admin | List all employees |
| `POST` | `/api/employees` | Admin | Create employee + card |
| `PUT` | `/api/employees/{id}` | Admin | Update employee |
| `DELETE` | `/api/employees/{id}` | Admin | Delete employee and all related data |
| `GET` | `/api/role_settings` | Admin | List roles and subsidy amounts |
| `POST` | `/api/role_settings` | Admin | Add role |
| `PUT` | `/api/role_settings` | Admin | Update role subsidy |
| `DELETE` | `/api/role_settings/{name}` | Admin | Delete role |
| `GET` | `/api/cash_desks` | — | List terminals |
| `POST` | `/api/cash_desks` | — | Add terminal |
| `DELETE` | `/api/cash_desks/{id}` | — | Delete terminal |
| `POST` | `/api/start_liveness` | — | Begin face verification session |
| `POST` | `/api/liveness_frame` | — | Submit webcam frame for analysis |
| `POST` | `/api/pay` | — | Process subsidy payment |
| `GET` | `/api/employee_info` | — | Look up employee by card UID |
| `GET` | `/api/statistics/chart` | — | Revenue chart data (filterable) |
| `GET` | `/api/statistics/export` | — | CSV export |
