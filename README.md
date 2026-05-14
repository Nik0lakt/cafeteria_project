# Cafeteria — Corporate Canteen Management System

**Navigation:** [English](#english) | [Русский](#russian) | [Investor FAQ (EN)](#investor--technical-faq) | [FAQ для инвесторов (RU)](#faq-для-инвесторов-и-корпоративных-клиентов)

---

<a name="english"></a>

# English

## Table of Contents

1. [Introduction](#1-introduction)
2. [Key Modules](#2-key-modules)
3. [Feature Overview](#3-feature-overview)
4. [Security and Data Integrity](#4-security-and-data-integrity)
5. [Technical Stack](#5-technical-stack)
6. [Installation and Deployment](#6-installation-and-deployment)
7. [Environment Variables](#7-environment-variables)
8. [Database Schema](#8-database-schema)
9. [Investor & Technical FAQ](#9-investor--technical-faq)

---

## 1. Introduction

**Cafeteria** is a full-stack, self-hosted ecosystem for managing corporate canteen operations. It replaces paper-based meal tracking, manual cashier workflows, and siloed accounting with a unified platform built around biometric identity, real-time analytics, and automated subsidy distribution.

The system serves three distinct roles simultaneously:

| Role | Interface | Authentication |
|------|-----------|----------------|
| Administrator | `admin.html` | JWT (bcrypt password hash) |
| Cashier / POS Terminal | `index.html`, `canteen.html` | Desk login + password |
| Employee | `cabinet.html` | RFID card UID |

**Problems it solves:**

- Employees are identified at the point of sale via RFID card + passive Face ID — no manual queue confirmation required.
- Daily meal subsidies are applied automatically based on work-schedule rules and role configuration.
- Financial data is stored in integer kopecks (1/100 of a ruble), eliminating floating-point rounding errors across all payment calculations.
- Administrators gain live analytics: multi-desk revenue charts with date-range and payment-method filters, exportable CSV reports, and real-time terminal online/offline status.
- The Telegram bot sends each employee a payment receipt immediately after a transaction and alerts administrators on every manual override.

---

## 2. Key Modules

### 2.1 Backend — FastAPI + PostgreSQL

The API server is built with **FastAPI** and **SQLAlchemy 2** (async-compatible ORM), backed by **PostgreSQL 13**. All routes are split into focused routers:

| Router file | Prefix | Responsibility |
|---|---|---|
| `routers/auth.py` | `/api` | Admin login (JWT), employee CRUD, schedule management, face enrollment |
| `routers/payment.py` | `/api` | POS payment flow, cash desk management, category/product CRUD, statistics |
| `routers/liveness.py` | `/api` | Liveness session lifecycle and frame analysis |
| `routers/cashiers.py` | `/api` | Cashier account management |
| `routers/bot.py` | — | Telegram bot polling thread |

On every startup, `app/main.py` runs an incremental schema migration (`update_db_schema`) using SQLAlchemy's dialect-agnostic `inspect()` — compatible with both SQLite (development) and PostgreSQL (production). It then calls `Base.metadata.create_all()` so new models are always applied.

### 2.2 Face ID and Liveness Detection

Biometric identification is powered by the **face_recognition** library (dlib underneath), with a fully JSON-based embedding pipeline — no `pickle` is used anywhere in the codebase.

**Enrollment flow:**
1. Admin uploads or captures a photo via the admin panel.
2. `cv_utils.get_face_embedding()` extracts a 128-dimensional face vector using `face_recognition.face_encodings()`.
3. The vector is stored as a JSON array in `employees.face_embedding_json`.

**Identification flow (per payment session):**

```
RFID card scan → /api/start_liveness → session created with cached embedding
     |
     v
Video frame → /api/liveness_frame → compare_faces() → track distance variance
     |
     v
match_count >= 4 AND max_dist - min_dist >= 0.02 → session.passed = True
     |
     v
/api/pay → liveness check → subsidy calculation → transaction
```

**Passive liveness (anti-spoofing):** Instead of requiring a deliberate blink, the system tracks the natural variance of `face_distance` values across consecutive frames. A live face produces micro-movements that cause the distance metric to vary by at least `0.02` over four frames (~1.6 seconds). A static photograph produces near-zero variance and fails the check.

The recognition tolerance is configurable via the `FACE_RECOGNITION_TOLERANCE` environment variable (default `0.55`; lower values are stricter).

### 2.3 POS Terminal

The terminal runs entirely in the browser via two HTML pages served as static files:

- **`index.html`** — RFID scan + Face ID verification screen. Starts a camera feed on page load, initiates a liveness session on card scan, streams JPEG frames (quality 0.92, 640x480) to the backend at 400 ms intervals.
- **`canteen.html`** — Order composition screen. Cashier selects products from per-desk categories, adjusts quantities, and confirms payment. Supports both biometric (automatic) and manual (cashier-confirms) payment modes.

RFID input arrives via **Web Serial API** (Arduino / USB RFID reader) using a streaming line-buffer parser, or alternatively via keyboard-emulation mode captured at the document level.

The terminal pings `/api/terminals/ping` every 60 seconds so the admin dashboard can display real-time online/offline status per desk.

### 2.4 Admin Dashboard

`admin.html` is a single-page application with four tabs:

**Employees tab:**
- Full CRUD with inline avatar preview, face enrollment (webcam capture or file upload), and per-employee monthly limit and reset day.
- Work schedule calendar: per-employee day toggle, bulk 5/2 and 2/2 presets, global date action by role.
- Background polling every 45 seconds refreshes the employee table without closing open modals or interrupting active search.
- Page Visibility API integration skips polling requests when the tab is hidden.

**Terminals tab:**
- Cash desk management: create, edit password, assign cashiers, view real-time online dot.
- Cashier management: create accounts with photo upload.

**Statistics tab:**
- Line chart (Chart.js) grouped by cash desk with multi-filter support: date range (7d / 30d / custom), cash desks (multi-select), payment methods (multi-select: card / cash / subsidy).
- Selecting all items in a filter group is the default; deselecting the last item auto-resets the group to all-selected.
- Revenue total and transaction count displayed above the chart.
- CSV export streamed directly from the server with UTF-8 BOM for Excel compatibility.

**Settings tab:**
- Web Serial RFID scanner connect / test.
- Toggle: whether manual cashier confirmation uses the employee subsidy balance.

### 2.5 Telegram Bot

A lightweight long-polling bot runs in a daemon thread alongside the FastAPI server. It handles two channels:

- **Inbound:** Employees can send `/my` or "баланс" to retrieve their current monthly balance and today's subsidy status.
- **Outbound — payment receipt:** After every successful biometric payment the system sends the employee a formatted HTML message with itemized order, subsidy applied, amount from limit, and remaining balance.
- **Outbound — manual override alert:** When a cashier manually confirms a payment (bypassing Face ID), the admin group receives a `sendMediaGroup` with the employee's enrolled photo and the live camera frame side by side.

---

## 3. Feature Overview

### 3.1 Two-factor Identity at Point of Sale

Every employee transaction requires two independent signals:

1. **Physical RFID card** — creates a liveness session tied to the card UID.
2. **Face match + liveness** — the session is only marked `passed = True` when both identity and anti-spoofing checks succeed on the server.

The `passed` flag is stored in `liveness_sessions` in the database. The `/api/pay` endpoint rejects any payment request where `session.passed` is `False`, even if the client sends `is_manual = False`. Manual override is logged and triggers an immediate Telegram alert to administrators.

### 3.2 Subsidy and Limit Management

Each employee role carries a daily meal subsidy (`RoleSetting.subsidy_rub`). On each payment:

```
available_today = role.subsidy_rub * 100  (kopecks)
                - SUM(subsidy_part_kopecks today)

applied_subsidy = min(total_bill, available_today)
withdraw        = total_bill - applied_subsidy
emp.month_limit_kopecks -= withdraw
```

Subsidy is only granted on days where a `WorkDay` record exists for the employee, ensuring non-working days receive no benefit. The daily subsidy cap resets at midnight (server local time).

Monthly limits reset on a configurable day of the month (`limit_reset_day`, default 28). Limits that exceed `month_limit_kopecks` are rejected with a `400 Insufficient funds` error before any database write.

### 3.3 Multi-filter Statistics

The statistics chart supports simultaneous selection of multiple cash desks and multiple payment methods. Each combination of active filters is translated into `IN()` SQL predicates on the server:

```python
if cash_desks:
    query = query.filter(Transaction.cash_desk_id.in_(cash_desks))
if payment_methods:
    query = query.filter(Transaction.payment_method.in_(payment_methods))
```

Datasets are grouped by `cash_desk_id` and aggregated per calendar day. The chart legend is shown automatically when more than one dataset is active.

### 3.4 Monthly Transaction History

Employees can view their full transaction history in `cabinet.html`, paginated by month. The `/api/user/history/{emp_id}` endpoint accepts `month` and `year` query parameters and returns an itemized list of purchases with a running monthly total. Month navigation is handled entirely on the client.

---

## 4. Security and Data Integrity

### 4.1 Authentication

| Layer | Mechanism |
|-------|-----------|
| Admin panel | JWT HS256, 24-hour expiry, `python-jose` |
| Password storage | bcrypt via the `bcrypt` library |
| Secret loading | `JWT_SECRET` from environment variable; raises `RuntimeError` on absence |
| Token validation | `get_current_admin()` dependency on every protected route; catches `JWTError` and expired tokens |
| Photo access | Private photos served via `/api/photos/{filename}` — requires admin JWT query param **or** a valid liveness session matching the card UID |

All admin-only mutations (cash desk CRUD, statistics endpoints) carry `dependencies=[Depends(get_current_admin)]`. Public read routes (product/category listing, terminal ping) are intentionally unauthenticated to support terminal operation without JWT.

### 4.2 Financial Precision

All monetary values are stored in **integer kopecks** (1/100 RUB) using `BigInteger` columns. Conversion to rubles (`/ 100`) occurs only at the API response boundary. This eliminates floating-point accumulation errors across all payment, subsidy, and reporting calculations.

```
DB column type   |  Application unit  |  Display
-----------------|--------------------|----------
BigInteger        |  kopecks (int)     |  / 100 -> rubles
```

The only exception is `RoleSetting.subsidy_rub` (a configuration value stored as `Float`), which is always rounded to the nearest kopeck with `int(round(value * 100))` before any arithmetic.

### 4.3 Infrastructure Isolation

```
Internet -> Caddy (TLS termination, HTTPS redirect)
               |
               v
           FastAPI / Uvicorn (port 8000, internal)
               |
               v
           PostgreSQL (internal network, not exposed)
```

- The database port is never mapped to the host.
- Private employee photos are stored in `/app/private_photos` (a Docker-internal path), not under the static file server root.
- The `.env` file is excluded from version control via `.gitignore`.

---

## 5. Technical Stack

### Backend

| Component | Library / Version |
|-----------|-------------------|
| Web framework | FastAPI 0.95 |
| ASGI server | Uvicorn 0.21 |
| ORM | SQLAlchemy 2.0 |
| Database | PostgreSQL 13 |
| DB driver | psycopg2-binary 2.9 |
| Data validation | Pydantic 1.10 |
| Authentication | python-jose (JWT HS256) |
| Password hashing | bcrypt |
| Environment | python-dotenv |

### Computer Vision

| Component | Library |
|-----------|---------|
| Face detection and encoding | face_recognition 1.3 (dlib) |
| Image decoding | OpenCV headless |
| Numerical operations | NumPy < 2.0 |

### Frontend

| Component | Technology |
|-----------|------------|
| UI | Vanilla JS + HTML5 |
| Styling | Custom CSS (CSS variables, no framework) |
| Icons | Phosphor Icons 2.1 (CDN) |
| Charts | Chart.js (CDN) |
| Camera API | MediaDevices (getUserMedia) |
| RFID input | Web Serial API (Arduino) |

### Infrastructure

| Component | Tool |
|-----------|------|
| Containerization | Docker + Docker Compose |
| Reverse proxy / TLS | Caddy 2 (automatic HTTPS) |
| Notifications | Telegram Bot API (long-polling) |

---

## 6. Installation and Deployment

### Prerequisites

- Docker Engine 20.10+
- Docker Compose 2.0+
- A domain name pointing to your server (required for Caddy automatic TLS)
- A Telegram bot token (from @BotFather)

### Step 1 — Clone the repository

```bash
git clone https://github.com/Nik0lakt/cafeteria_project.git
cd cafeteria_project
```

### Step 2 — Create the environment file

```bash
cp .env.example .env
```

### Step 3 — Generate a bcrypt hash for the admin password

```bash
python3 -c "import bcrypt; print(bcrypt.hashpw(b'your_password', bcrypt.gensalt()).decode())"
```

Paste the output into `ADMIN_PASSWORD_HASH` in `.env`.

### Step 4 — Generate a random JWT secret

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Paste the output into `JWT_SECRET` in `.env`.

### Step 5 — Configure the reverse proxy

Edit `Caddyfile` and replace the placeholder domain:

```
your.domain.com {
    reverse_proxy web:8000
}
```

### Step 6 — Start the stack

```bash
docker compose up -d --build
```

The first build downloads and compiles `dlib` / `face_recognition` models — this may take 5–15 minutes depending on hardware.

### Step 7 — Verify

```bash
docker compose logs -f web
```

The admin panel is available at `https://your.domain.com/admin.html`.

---

## 7. Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL connection string, e.g. `postgresql://user:pass@db:5432/cafeteria_db` |
| `JWT_SECRET` | Yes | Minimum 32-character random hex string used to sign admin tokens |
| `ADMIN_PASSWORD_HASH` | Yes | bcrypt hash of the admin password |
| `TELEGRAM_BOT_TOKEN` | Yes | Bot token from @BotFather |
| `ADMIN_CHAT_ID` | Yes | Telegram chat or group ID for manual payment alerts |
| `FACE_RECOGNITION_TOLERANCE` | No | Float 0.0–1.0, default `0.55`. Lower = stricter matching |

**Security note:** Never commit `.env` to version control. The file is listed in `.gitignore`.

---

## 8. Database Schema

### Core tables

| Table | Primary key | Key columns | Purpose |
|-------|-------------|-------------|---------|
| `employees` | `id` | `full_name`, `role`, `month_limit_kopecks`, `face_embedding_json`, `limit_reset_day` | Employee identity and financial state |
| `cards` | `id` | `uid`, `employee_id` | Maps physical RFID UID to an employee |
| `transactions` | `id` | `employee_id`, `amount_total_kopecks`, `subsidy_part_kopecks`, `limit_part_kopecks`, `items` (JSON), `payment_method`, `cash_desk_id` | Immutable payment records |
| `work_days` | `id` | `employee_id`, `date` | Work schedule — presence of a row means working day |
| `role_settings` | `id` | `role_name`, `subsidy_rub` | Daily subsidy per role |
| `liveness_sessions` | `id` (UUID) | `card_uid`, `passed`, `embedding_json`, `blink_count`, `last_ear`, `min_ear_closed` | Transient biometric sessions, auto-expired after 10 minutes |
| `cash_desks` | `id` | `login`, `hashed_password`, `assigned_cashier_logins` (JSON), `last_seen` | POS terminal registry |
| `categories` | `id` | `name`, `cash_desk_id` | Per-desk product categories |
| `products` | `id` | `name`, `price` (integer rubles), `category_id` | Menu items |
| `cash_desk_products` | composite | `cash_desk_id`, `product_id`, `price` | Per-desk price override for products |
| `app_settings` | `key` (string PK) | `value` | Runtime configuration flags |
| `audit_logs` | `id` | `action`, `entity`, `details` (JSON), `timestamp` | Admin action trail |

### Financial data flow

```
Employee pays at POS terminal
        |
        v
Transaction row created (all amounts in kopecks)
        |
        |-- amount_total_kopecks  = sum of (price x qty x 100) for all items
        |-- subsidy_part_kopecks  = min(daily_available, total_bill)
        +-- limit_part_kopecks   = total_bill - subsidy_part
                |
                v
        emp.month_limit_kopecks -= limit_part_kopecks
```

---

<a name="investor--technical-faq"></a>

## 9. Investor & Technical FAQ

### Q1: How does the system handle personal biometric data (GDPR / Russian Federal Law No. 152-FZ)?

**A:** The system is built on Privacy-by-Design principles:

| Layer | Implementation |
|-------|---------------|
| Storage | Only a 128-dimensional floating-point **vector** is stored — the original photograph is never persisted to disk. |
| Encoding | The photo → vector transformation (dlib ResNet) is one-directional; reconstructing a face from a vector is computationally infeasible. |
| Infrastructure | Fully **self-hosted** (Docker Compose, on-premise). No biometric data ever leaves the corporate network. |
| Session retention | `liveness_sessions` rows auto-delete after 10 minutes via a background cleanup task. |
| Right to erasure | On employee termination, a single `DELETE FROM employees WHERE id=X` removes the person's vector, name, card bindings, and financial history from the operational system. |

The architecture eliminates the primary compliance risk: storing the source biometric image is prohibited under 152-FZ — we never store it.

---

### Q2: What happens when the internet connection is lost?

**A:** The system is **local-first**. All business-critical paths function without an internet connection:

| Component | Offline behaviour |
|-----------|------------------|
| Face recognition | Runs locally (dlib on CPU) — no cloud API call |
| Payment processing | Writes directly to local PostgreSQL |
| RFID reader | USB Serial — no network dependency |
| Admin panel | Served from local static files via Caddy |
| Telegram notifications | Queued in memory; bot retries on reconnection |

The only features that degrade gracefully during a network outage are outbound Telegram messages and (if configured) remote monitoring dashboards. All financial transactions are recorded locally and are never lost.

---

### Q3: How is financial integrity guaranteed? (No floating-point rounding errors)

**A:** Every monetary value is stored and computed in **integer kopecks** (1/100th of a ruble).

The IEEE 754 problem this avoids:
```python
# WRONG — classic float rounding error
0.1 + 0.2 == 0.30000000000000004

# RIGHT — Cafeteria approach
10 + 20 == 30  # kopecks, always exact integer arithmetic
```

Database-level invariants enforced on every transaction:
- `amount_total_kopecks` (BIGINT) = Σ(price_kopecks × qty) — exact
- `subsidy_part_kopecks` (BIGINT) = min(daily_subsidy_kopecks, total) — exact
- `limit_part_kopecks` (BIGINT) = total − subsidy_part — exact

The **only** float in the system is `RoleSetting.subsidy_rub` (a human-readable configuration field), which is immediately converted via `int(round(value * 100))` before any arithmetic. Month-end reconciliation is auditable to the kopeck.

---

### Q4: How does the system scale to hundreds of terminals and thousands of employees?

**A:** The architecture is horizontally scalable at every layer:

**Step 1 — Single Node (current default):** One Docker Compose host handles up to ~20 POS terminals and ~2,000 employees. SQLAlchemy connection pooling; Caddy handles TLS termination and HTTP/2.

**Step 2 — Read Replica:** Add a PostgreSQL streaming replica for statistics queries. Route `GET /api/statistics/*` to the replica, all writes to primary. Zero application code change required.

**Step 3 — Multi-Node:** Place a load balancer (Nginx, HAProxy) in front of multiple FastAPI instances. Sessions are stateless (JWT) — any node can serve any request.

| Scale | Terminals | Employees | Architecture |
|-------|-----------|-----------|-------------|
| S | 1–5 | up to 500 | Single Docker Compose host |
| M | 5–50 | 500–5,000 | Primary + Read Replica |
| L | 50–500 | 5,000–50,000 | Multi-node FastAPI + PgBouncer + Read Replicas |

Each scale step is additive — no data migrations or application rewrites are needed between tiers.

---

### Q5: What prevents fraud and payment bypass attacks?

**A:** Multiple independent defence layers enforce a strict two-factor chain (card + face):

```
RFID Card tap
    │
    ├─► Card registered in system? ──No──► Transaction rejected immediately
    │
    ├─► Liveness session created (UUID, 10-min TTL)
    │       │
    │       ├─► Face distance variance ≥ 0.02 across 4 frames? ──No──► Session stays open
    │       │
    │       └─► session.passed = TRUE (written to DB atomically)
    │
    └─► /api/pay called with session UUID
            │
            ├─► session.passed == TRUE? ──No──► HTTP 403
            │
            ├─► session age < 10 min? ──No──► HTTP 403
            │
            └─► Transaction committed; session deleted immediately
```

**Attack surface analysis:**

| Attack vector | Mitigation |
|---------------|-----------|
| Photo / printed image spoofing | Passive liveness: variance of face distance across 4 captured frames must exceed threshold — flat images produce near-zero variance |
| Video replay attack | Same variance check; a looped video has zero variance over its duration |
| Session UUID replay | Session is deleted from DB immediately after successful payment — reuse returns 403 |
| Direct API call to `/pay` | `session.passed` flag must be `TRUE` in DB — it cannot be set without completing liveness |
| RFID card cloning | Card UID alone is insufficient — liveness session must pass independently |
| Admin privilege escalation | JWT HS256 signed with `SECRET_KEY`; admin password stored as bcrypt hash |

All cashier manual-override transactions are written to `audit_logs` with the cashier's identity and a timestamp.

---

### Q6: Can this integrate with 1C, SAP, or other ERP systems?

**A:** Yes. The system exposes a versioned RESTful JSON API; FastAPI auto-generates OpenAPI 3.0 documentation at `/docs` (interactive) and `/openapi.json` (machine-readable).

**Integration options:**

| Method | Use case | Effort |
|--------|----------|--------|
| REST API — polling | Nightly batch export of transactions to 1C / SBIS | Low — single authenticated GET |
| REST API — push | Real-time sync: HR system pushes employee create/update events | Low — standard PUT `/api/employees/{id}` |
| CSV Export | Finance team imports monthly report into Excel or 1C | Zero — built-in button in admin panel |
| Database direct read | BI tools (Metabase, Tableau, Power BI) connect to PostgreSQL read replica | Low — standard PostgreSQL connector |

**Example: sync a new employee from an HR system**
```http
PUT /api/employees/{id}
Authorization: Bearer <admin-jwt>
Content-Type: application/json

{
  "full_name": "Иванов Иван Иванович",
  "role": "engineer",
  "month_limit_rub": 5000
}
```

The OpenAPI schema can be imported directly into Postman or Insomnia, and used to auto-generate typed client SDKs for Python, TypeScript, Java, or any language supported by `openapi-generator`.

---

---

<a name="russian"></a>

# Русский

## Содержание

1. [Введение](#1-введение)
2. [Ключевые модули](#2-ключевые-модули)
3. [Возможности системы](#3-возможности-системы)
4. [Безопасность и целостность данных](#4-безопасность-и-целостность-данных)
5. [Технологический стек](#5-технологический-стек)
6. [Установка и развёртывание](#6-установка-и-развёртывание)
7. [Переменные окружения](#7-переменные-окружения)
8. [Схема базы данных](#8-схема-базы-данных)
9. [FAQ для инвесторов и корпоративных клиентов](#9-faq-для-инвесторов-и-корпоративных-клиентов)

---

## 1. Введение

**Cafeteria** — это полнофункциональная, самохостируемая экосистема для управления корпоративной столовой. Она заменяет бумажный учёт питания, ручное подтверждение кассиром и разрозненную бухгалтерию единой платформой, построенной на биометрической идентификации, аналитике в реальном времени и автоматическом распределении дотаций.

Система обслуживает три роли одновременно:

| Роль | Интерфейс | Аутентификация |
|------|-----------|----------------|
| Администратор | `admin.html` | JWT (bcrypt-хэш пароля) |
| Кассир / POS-терминал | `index.html`, `canteen.html` | Логин и пароль кассы |
| Сотрудник | `cabinet.html` | UID RFID-карты |

**Какие проблемы решает:**

- Сотрудники идентифицируются на кассе по RFID-карте и пассивному Face ID — без ручного подтверждения очереди.
- Ежедневные дотации начисляются автоматически на основании рабочего расписания и настроек роли.
- Финансовые данные хранятся в целочисленных копейках (1/100 рубля), исключая ошибки округления с плавающей точкой.
- Администраторы получают живую аналитику: многокассовые графики выручки с фильтрами по дате и способу оплаты, экспорт в CSV.
- Telegram-бот мгновенно отправляет сотруднику чек после каждой транзакции и уведомляет администратора при любом ручном обходе Face ID.

---

## 2. Ключевые модули

### 2.1 Бэкенд — FastAPI + PostgreSQL

API-сервер построен на **FastAPI** и **SQLAlchemy 2** (ORM), в качестве базы данных используется **PostgreSQL 13**. Маршруты разделены по тематическим роутерам:

| Файл роутера | Префикс | Ответственность |
|---|---|---|
| `routers/auth.py` | `/api` | Авторизация администратора (JWT), CRUD сотрудников, расписание, Face ID |
| `routers/payment.py` | `/api` | Платёжный процесс, управление кассами, категории/товары, статистика |
| `routers/liveness.py` | `/api` | Жизненный цикл сессии liveness и анализ кадров |
| `routers/cashiers.py` | `/api` | Управление аккаунтами кассиров |
| `routers/bot.py` | — | Поток polling Telegram-бота |

При каждом старте `app/main.py` запускает инкрементальную миграцию схемы (`update_db_schema`) через диалект-агностическую функцию `inspect()` SQLAlchemy — совместима как с SQLite (разработка), так и с PostgreSQL (продакшн). Затем вызывается `Base.metadata.create_all()` для применения новых моделей.

### 2.2 Face ID и определение живости (Liveness Detection)

Биометрическая идентификация работает на библиотеке **face_recognition** (dlib под капотом). Вся работа с эмбеддингами ведётся через JSON — `pickle` не используется нигде в кодовой базе.

**Процесс энролла (регистрации лица):**
1. Администратор загружает или снимает фото через административную панель.
2. `cv_utils.get_face_embedding()` извлекает 128-мерный вектор лица через `face_recognition.face_encodings()`.
3. Вектор сохраняется как JSON-массив в `employees.face_embedding_json`.

**Процесс идентификации (по сессии оплаты):**

```
Сканирование RFID -> /api/start_liveness -> создание сессии с кэшированным эмбеддингом
      |
      v
Видеокадр -> /api/liveness_frame -> compare_faces() -> отслеживание дисперсии расстояния
      |
      v
match_count >= 4 И max_dist - min_dist >= 0.02 -> session.passed = True
      |
      v
/api/pay -> проверка liveness -> расчёт дотации -> транзакция
```

**Пассивное определение живости (анти-спуфинг):** Вместо требования намеренного моргания система отслеживает естественную дисперсию значений `face_distance` на нескольких последовательных кадрах. Живое лицо создаёт микродвижения, из-за которых метрика расстояния варьируется не менее чем на `0.02` за четыре кадра (~1,6 секунды). Статичная фотография даёт почти нулевую дисперсию и не проходит проверку.

Порог распознавания настраивается через переменную окружения `FACE_RECOGNITION_TOLERANCE` (по умолчанию `0.55`; меньше — строже).

### 2.3 POS-терминал

Терминал полностью работает в браузере через две HTML-страницы, отдаваемые как статические файлы:

- **`index.html`** — экран сканирования RFID и проверки Face ID. Запускает видеопоток при загрузке страницы, инициирует сессию liveness при сканировании карты, передаёт JPEG-кадры (качество 0,92, разрешение 640x480) на сервер с интервалом 400 мс.
- **`canteen.html`** — экран формирования заказа. Кассир выбирает товары из категорий своей кассы, регулирует количество и подтверждает оплату. Поддерживает биометрический (автоматический) и ручной (подтверждение кассиром) режимы.

RFID-ввод поступает через **Web Serial API** (Arduino/USB-считыватель) с потоковым парсером строк, либо в режиме эмуляции клавиатуры, перехватываемой на уровне документа.

Терминал каждые 60 секунд пингует `/api/terminals/ping`, чтобы административная панель могла отображать актуальный статус онлайн/оффлайн для каждой кассы.

### 2.4 Административная панель

`admin.html` — одностраничное приложение с четырьмя вкладками:

**Сотрудники:**
- Полный CRUD с предпросмотром аватара, энроллом лица (съёмка с веб-камеры или загрузка файла) и настройками месячного лимита и дня сброса.
- Календарь рабочего расписания: переключение дней, групповые пресеты 5/2 и 2/2, массовое действие на дату по роли.
- Фоновый polling каждые 45 секунд обновляет таблицу без закрытия открытых модалок и без прерывания активного поиска.
- Интеграция с Page Visibility API — запросы не отправляются при скрытой вкладке.

**Терминалы:**
- Управление кассами: создание, смена пароля, назначение кассиров, индикатор онлайн в реальном времени.
- Управление кассирами: создание аккаунтов с загрузкой фото.

**Статистика:**
- Линейный график (Chart.js) с группировкой по кассе и мультифильтрами: диапазон дат (7д / 30д / произвольный), кассы (множественный выбор), способы оплаты (множественный выбор: карта / наличные / дотация).
- При выборе всех элементов фильтра используется значение по умолчанию; снятие последнего чекбокса автоматически выбирает всю группу снова.
- Сумма выручки и количество транзакций отображаются над графиком.
- Экспорт CSV стримится прямо с сервера с BOM-меткой UTF-8 для корректного открытия в Excel.

**Настройки:**
- Подключение и тест Web Serial RFID-сканера.
- Тумблер: использовать ли дотацию при ручном подтверждении кассиром.

### 2.5 Telegram-бот

Лёгкий long-polling бот запускается в daemon-потоке рядом с FastAPI-сервером и работает по двум каналам:

- **Входящие:** Сотрудники могут отправить `/my` или «баланс», чтобы получить текущий месячный остаток и статус дотации на сегодня.
- **Исходящие — чек сотрудника:** После каждой успешной биометрической оплаты система отправляет HTML-сообщение с детализацией заказа, суммой дотации, списанием с лимита и остатком.
- **Исходящие — уведомление об ручном обходе:** При ручном подтверждении кассиром (без Face ID) в группу администраторов отправляется `sendMediaGroup` с двумя фотографиями: зарегистрированное фото сотрудника и кадр с живой камеры.

---

## 3. Возможности системы

### 3.1 Двухфакторная идентификация на кассе

Каждая транзакция сотрудника требует двух независимых сигналов:

1. **Физическая RFID-карта** — создаёт сессию liveness, привязанную к UID карты.
2. **Совпадение лица + liveness** — сессия помечается `passed = True` только при успешном прохождении обеих проверок на сервере.

Флаг `passed` хранится в `liveness_sessions` в базе данных. Эндпоинт `/api/pay` отклоняет любой запрос на оплату, если `session.passed` равен `False`, даже если клиент передаёт `is_manual = False`. Ручной обход логируется и немедленно инициирует Telegram-уведомление администраторам.

### 3.2 Управление лимитами и дотациями

Каждая роль сотрудника имеет дневной лимит дотации (`RoleSetting.subsidy_rub`). При каждой оплате:

```
available_today = role.subsidy_rub * 100  (копейки)
               - SUM(subsidy_part_kopecks за сегодня)

applied_subsidy = min(сумма счёта, available_today)
withdraw        = сумма счёта - applied_subsidy
emp.month_limit_kopecks -= withdraw
```

Дотация начисляется только в дни, для которых существует запись в `WorkDay`, — нерабочие дни автоматически исключаются. Дневной лимит дотации сбрасывается в полночь по серверному времени.

Месячные лимиты сбрасываются в настраиваемый день месяца (`limit_reset_day`, по умолчанию 28). Если сумма к списанию превышает `month_limit_kopecks`, возвращается ошибка `400 Недостаточно средств` ещё до записи в базу данных.

### 3.3 Мультифильтровая статистика

График статистики поддерживает одновременный выбор нескольких касс и нескольких способов оплаты. Каждая комбинация активных фильтров транслируется в SQL-предикаты через `IN()` на сервере:

```python
if cash_desks:
    query = query.filter(Transaction.cash_desk_id.in_(cash_desks))
if payment_methods:
    query = query.filter(Transaction.payment_method.in_(payment_methods))
```

Датасеты группируются по `cash_desk_id` и агрегируются по календарным дням. Легенда графика отображается автоматически при наличии более одного активного датасета.

### 3.4 История транзакций по месяцам

Сотрудники могут просматривать полную историю покупок в `cabinet.html`, с постраничной навигацией по месяцам. Эндпоинт `/api/user/history/{emp_id}` принимает параметры `month` и `year` и возвращает постатейный список покупок с итоговой суммой за месяц. Навигация по месяцам обрабатывается полностью на клиенте.

---

## 4. Безопасность и целостность данных

### 4.1 Аутентификация

| Уровень | Механизм |
|---------|----------|
| Административная панель | JWT HS256, срок действия 24 часа, библиотека `python-jose` |
| Хранение паролей | bcrypt через библиотеку `bcrypt` |
| Загрузка секретов | `JWT_SECRET` из переменной окружения; при отсутствии — `RuntimeError` |
| Валидация токена | Зависимость `get_current_admin()` на каждом защищённом маршруте; перехватывает `JWTError` и истёкшие токены |
| Доступ к фото | Приватные фото отдаются через `/api/photos/{filename}` — требуют JWT-параметр администратора **либо** валидную сессию liveness с совпадающим UID карты |

Все административные мутации (CRUD касс, эндпоинты статистики) содержат `dependencies=[Depends(get_current_admin)]`. Публичные GET-маршруты (список товаров/категорий, пинг терминала) намеренно не требуют аутентификации для поддержки работы терминала без JWT.

### 4.2 Финансовая точность

Все денежные значения хранятся в **целочисленных копейках** (1/100 руб.) с использованием колонок типа `BigInteger`. Преобразование в рубли (`/ 100`) происходит только на границе API-ответа. Это исключает накопление ошибок плавающей точки во всех расчётах оплаты, дотаций и отчётности.

```
Тип колонки в БД |  Единица в приложении  |  Отображение
-----------------|------------------------|---------------
BigInteger        |  копейки (int)         |  / 100 -> рубли
```

Единственное исключение — `RoleSetting.subsidy_rub` (конфигурационное значение, хранящееся как `Float`), которое всегда округляется до ближайшей копейки через `int(round(value * 100))` перед любой арифметикой.

### 4.3 Изоляция инфраструктуры

```
Интернет -> Caddy (терминация TLS, редирект на HTTPS)
               |
               v
           FastAPI / Uvicorn (порт 8000, внутренняя сеть)
               |
               v
           PostgreSQL (внутренняя сеть, порт не проброшен)
```

- Порт базы данных никогда не пробрасывается на хост.
- Приватные фото сотрудников хранятся в `/app/private_photos` (путь внутри Docker), а не в корне статического файлового сервера.
- Файл `.env` исключён из системы контроля версий через `.gitignore`.

---

## 5. Технологический стек

### Бэкенд

| Компонент | Библиотека / Версия |
|-----------|---------------------|
| Веб-фреймворк | FastAPI 0.95 |
| ASGI-сервер | Uvicorn 0.21 |
| ORM | SQLAlchemy 2.0 |
| База данных | PostgreSQL 13 |
| Драйвер БД | psycopg2-binary 2.9 |
| Валидация данных | Pydantic 1.10 |
| Аутентификация | python-jose (JWT HS256) |
| Хэширование паролей | bcrypt |
| Работа с окружением | python-dotenv |

### Компьютерное зрение

| Компонент | Библиотека |
|-----------|------------|
| Детекция и кодирование лица | face_recognition 1.3 (dlib) |
| Декодирование изображений | OpenCV headless |
| Численные операции | NumPy < 2.0 |

### Фронтенд

| Компонент | Технология |
|-----------|------------|
| UI | Vanilla JS + HTML5 |
| Стилизация | Кастомный CSS (CSS-переменные, без фреймворка) |
| Иконки | Phosphor Icons 2.1 (CDN) |
| Графики | Chart.js (CDN) |
| Доступ к камере | MediaDevices (getUserMedia) |
| RFID-ввод | Web Serial API (Arduino) |

### Инфраструктура

| Компонент | Инструмент |
|-----------|-----------|
| Контейнеризация | Docker + Docker Compose |
| Обратный прокси / TLS | Caddy 2 (автоматический HTTPS) |
| Уведомления | Telegram Bot API (long-polling) |

---

## 6. Установка и развёртывание

### Требования

- Docker Engine 20.10+
- Docker Compose 2.0+
- Доменное имя, указывающее на ваш сервер (необходимо для автоматического TLS через Caddy)
- Токен Telegram-бота (от @BotFather)

### Шаг 1 — Клонировать репозиторий

```bash
git clone https://github.com/Nik0lakt/cafeteria_project.git
cd cafeteria_project
```

### Шаг 2 — Создать файл окружения

```bash
cp .env.example .env
```

### Шаг 3 — Сгенерировать bcrypt-хэш пароля администратора

```bash
python3 -c "import bcrypt; print(bcrypt.hashpw(b'ваш_пароль', bcrypt.gensalt()).decode())"
```

Вставить вывод в `ADMIN_PASSWORD_HASH` в `.env`.

### Шаг 4 — Сгенерировать случайный JWT-секрет

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Вставить вывод в `JWT_SECRET` в `.env`.

### Шаг 5 — Настроить обратный прокси

Отредактировать `Caddyfile`, заменив домен:

```
ваш.домен.ru {
    reverse_proxy web:8000
}
```

### Шаг 6 — Запустить стек

```bash
docker compose up -d --build
```

Первая сборка скачивает и компилирует `dlib` / `face_recognition` — это может занять 5–15 минут в зависимости от железа.

### Шаг 7 — Проверить

```bash
docker compose logs -f web
```

Административная панель доступна по адресу `https://ваш.домен.ru/admin.html`.

---

## 7. Переменные окружения

| Переменная | Обязательна | Описание |
|------------|-------------|----------|
| `DATABASE_URL` | Да | Строка подключения к PostgreSQL, например `postgresql://user:pass@db:5432/cafeteria_db` |
| `JWT_SECRET` | Да | Случайная строка длиной не менее 32 символов для подписи токенов |
| `ADMIN_PASSWORD_HASH` | Да | bcrypt-хэш пароля администратора |
| `TELEGRAM_BOT_TOKEN` | Да | Токен бота от @BotFather |
| `ADMIN_CHAT_ID` | Да | ID чата/группы Telegram для уведомлений о ручных оплатах |
| `FACE_RECOGNITION_TOLERANCE` | Нет | Float 0.0–1.0, по умолчанию `0.55`. Меньше — строже |

**Важно по безопасности:** Никогда не коммитьте `.env` в систему контроля версий. Файл перечислен в `.gitignore`.

---

## 8. Схема базы данных

### Основные таблицы

| Таблица | Первичный ключ | Ключевые колонки | Назначение |
|---------|----------------|------------------|------------|
| `employees` | `id` | `full_name`, `role`, `month_limit_kopecks`, `face_embedding_json`, `limit_reset_day` | Идентификация сотрудника и финансовое состояние |
| `cards` | `id` | `uid`, `employee_id` | Связь физического UID RFID с сотрудником |
| `transactions` | `id` | `employee_id`, `amount_total_kopecks`, `subsidy_part_kopecks`, `limit_part_kopecks`, `items` (JSON), `payment_method`, `cash_desk_id` | Неизменяемые записи оплаты |
| `work_days` | `id` | `employee_id`, `date` | Рабочий график — наличие записи означает рабочий день |
| `role_settings` | `id` | `role_name`, `subsidy_rub` | Дневная дотация по роли |
| `liveness_sessions` | `id` (UUID) | `card_uid`, `passed`, `embedding_json`, `blink_count`, `last_ear`, `min_ear_closed` | Временные биометрические сессии, авто-удаление через 10 мин |
| `cash_desks` | `id` | `login`, `hashed_password`, `assigned_cashier_logins` (JSON), `last_seen` | Реестр POS-терминалов |
| `categories` | `id` | `name`, `cash_desk_id` | Категории товаров по кассе |
| `products` | `id` | `name`, `price` (целые рубли), `category_id` | Позиции меню |
| `cash_desk_products` | составной | `cash_desk_id`, `product_id`, `price` | Индивидуальные цены товара для конкретной кассы |
| `app_settings` | `key` (строка PK) | `value` | Флаги конфигурации в реальном времени |
| `audit_logs` | `id` | `action`, `entity`, `details` (JSON), `timestamp` | Журнал действий администратора |

### Финансовый поток данных

```
Сотрудник платит на кассе
        |
        v
Создаётся запись Transaction (все суммы в копейках)
        |
        |-- amount_total_kopecks  = сумма (цена x кол-во x 100) по всем позициям
        |-- subsidy_part_kopecks  = min(доступная дотация, сумма счёта)
        +-- limit_part_kopecks   = сумма счёта - subsidy_part
                |
                v
        emp.month_limit_kopecks -= limit_part_kopecks
```

---

<a name="9-faq-для-инвесторов-и-корпоративных-клиентов"></a>

## 9. FAQ для инвесторов и корпоративных клиентов

### В1: Как система обрабатывает персональные биометрические данные (GDPR / 152-ФЗ)?

**О:** Система построена на принципах Privacy by Design:

| Уровень | Реализация |
|---------|-----------|
| Хранение | Хранится только 128-мерный вектор вещественных чисел — исходная фотография **никогда** не записывается на диск. |
| Кодирование | Преобразование фото → вектор (dlib ResNet) — односторонняя операция; восстановить лицо из вектора вычислительно невозможно. |
| Инфраструктура | Полностью **on-premise** (Docker Compose). Биометрические данные не покидают корпоративную сеть. |
| Хранение сессий | Строки `liveness_sessions` автоматически удаляются через 10 минут фоновым заданием очистки. |
| Право на удаление | При увольнении сотрудника один запрос `DELETE FROM employees WHERE id=X` удаляет вектор, ФИО, привязку карты и финансовую историю из операционной системы. |

Архитектура устраняет главный риск 152-ФЗ: хранение исходного биометрического изображения запрещено — мы его никогда не сохраняем.

---

### В2: Что происходит при потере интернет-соединения?

**О:** Система работает по принципу **local-first**. Все бизнес-критические операции выполняются без интернета:

| Компонент | Поведение при отключении |
|-----------|-------------------------|
| Распознавание лиц | Работает локально (dlib на CPU) — нет обращений к облаку |
| Проведение оплаты | Пишет напрямую в локальный PostgreSQL |
| RFID-считыватель | USB Serial — не зависит от сети |
| Панель администратора | Раздаётся из локальных статических файлов через Caddy |
| Telegram-уведомления | Ставятся в очередь; бот повторяет отправку при восстановлении соединения |

При отсутствии сети деградируют только исходящие сообщения Telegram и внешние дашборды мониторинга (если настроены). Все финансовые транзакции записываются локально и не теряются.

---

### В3: Как гарантируется финансовая точность? (Без ошибок округления с плавающей точкой)

**О:** Все денежные значения хранятся и обрабатываются в **целых копейках** (1/100 рубля).

Проблема IEEE 754, которую это решает:
```python
# НЕВЕРНО — классическая ошибка округления
0.1 + 0.2 == 0.30000000000000004

# ВЕРНО — подход Cafeteria
10 + 20 == 30  # копейки, точная целочисленная арифметика
```

Инварианты, соблюдаемые на уровне базы данных при каждой транзакции:
- `amount_total_kopecks` (BIGINT) = Σ(цена_копейки × кол-во) — точно
- `subsidy_part_kopecks` (BIGINT) = min(дневная_дотация_копейки, итого) — точно
- `limit_part_kopecks` (BIGINT) = итого − дотация — точно

**Единственный** float в системе — `RoleSetting.subsidy_rub` (поле конфигурации для удобства ввода), которое немедленно преобразуется через `int(round(value * 100))` перед любыми вычислениями. Сверка данных на конец месяца аудируема с точностью до копейки.

---

### В4: Как система масштабируется на сотни терминалов и тысячи сотрудников?

**О:** Архитектура горизонтально масштабируема на каждом уровне:

**Шаг 1 — Один узел (текущий вариант по умолчанию):** Один Docker Compose хост обрабатывает до ~20 POS-терминалов и ~2 000 сотрудников. Пул соединений SQLAlchemy; Caddy выполняет TLS-терминацию и HTTP/2.

**Шаг 2 — Read Replica:** Добавляется стриминговая реплика PostgreSQL для запросов статистики. Маршрутизация `GET /api/statistics/*` на реплику, все записи — на мастер. Изменений кода приложения не требуется.

**Шаг 3 — Несколько узлов:** Балансировщик нагрузки (Nginx, HAProxy) перед несколькими экземплярами FastAPI. Сессии — stateless (JWT), любой узел обрабатывает любой запрос.

| Масштаб | Терминалы | Сотрудники | Архитектура |
|---------|-----------|------------|-------------|
| S | 1–5 | до 500 | Один Docker Compose хост |
| M | 5–50 | 500–5 000 | Мастер + Read Replica |
| L | 50–500 | 5 000–50 000 | Мультиузловой FastAPI + PgBouncer + Read Replicas |

Каждый шаг масштабирования аддитивен — между уровнями не требуются миграции данных или переписывание приложения.

---

### В5: Что предотвращает мошенничество и обход системы оплаты?

**О:** Несколько независимых уровней защиты обеспечивают строгую двухфакторную цепочку (карта + лицо):

```
Прикладывание RFID-карты
    │
    ├─► Карта зарегистрирована в системе? ──Нет──► Транзакция немедленно отклонена
    │
    ├─► Создаётся Liveness-сессия (UUID, TTL 10 мин)
    │       │
    │       ├─► Дисперсия расстояния до лица ≥ 0.02 на 4 кадрах? ──Нет──► Сессия открыта
    │       │
    │       └─► session.passed = TRUE (атомарная запись в БД)
    │
    └─► /api/pay вызывается с UUID сессии
            │
            ├─► session.passed == TRUE? ──Нет──► HTTP 403
            │
            ├─► Возраст сессии < 10 мин? ──Нет──► HTTP 403
            │
            └─► Транзакция зафиксирована; сессия немедленно удалена
```

**Анализ вектора угроз:**

| Вектор атаки | Защита |
|--------------|--------|
| Подмена фото / распечатки | Пассивный liveness: дисперсия расстояния до лица на 4 кадрах должна превышать порог — у плоских изображений дисперсия близка к нулю |
| Атака воспроизведением видео | Тот же тест дисперсии; зациклённое видео даёт нулевую дисперсию за время просмотра |
| Повторное использование UUID сессии | Сессия удаляется из БД сразу после успешной оплаты — повторное использование возвращает 403 |
| Прямой вызов API `/pay` | Флаг `session.passed` должен быть `TRUE` в БД — нельзя установить без прохождения liveness |
| Клонирование RFID-карты | UID карты одного недостаточно — liveness-сессия должна быть пройдена независимо |
| Эскалация привилегий администратора | JWT HS256 подписан `SECRET_KEY`; пароль администратора хранится в виде bcrypt-хэша |

Все ручные транзакции, проводимые кассирами через режим обхода, записываются в `audit_logs` с идентификатором кассира и временной меткой.

---

### В6: Возможна ли интеграция с 1С, SAP или другими ERP-системами?

**О:** Да. Система предоставляет версионированный RESTful JSON API; FastAPI автоматически генерирует документацию OpenAPI 3.0 по адресу `/docs` (интерактивная) и `/openapi.json` (машиночитаемая).

**Варианты интеграции:**

| Метод | Сценарий | Трудозатраты |
|-------|----------|-------------|
| REST API — опрос | Ночной пакетный экспорт транзакций в 1С / СБИС | Низкие — один аутентифицированный GET |
| REST API — push | Синхронизация в реальном времени: HR-система отправляет события создания/обновления сотрудников | Низкие — стандартный PUT `/api/employees/{id}` |
| Экспорт CSV | Финансовый отдел импортирует ежемесячный отчёт в Excel или 1С | Нулевые — встроенная кнопка в панели администратора |
| Прямое чтение из БД | BI-инструменты (Metabase, Tableau, Power BI) подключаются к реплике PostgreSQL | Низкие — стандартный коннектор PostgreSQL |

**Пример: синхронизация нового сотрудника из HR-системы**
```http
PUT /api/employees/{id}
Authorization: Bearer <admin-jwt>
Content-Type: application/json

{
  "full_name": "Иванов Иван Иванович",
  "role": "engineer",
  "month_limit_rub": 5000
}
```

Схема OpenAPI читается машинами и может быть импортирована напрямую в Postman или Insomnia, а также использована для автоматической генерации типизированных клиентских SDK на Python, TypeScript, Java или любом языке, поддерживаемом `openapi-generator`.
