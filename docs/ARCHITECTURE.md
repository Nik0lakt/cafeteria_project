# Architecture

## System Overview

Cafeteria is a corporate cafeteria management system that automates meal payments using RFID cards and biometric face verification.

```mermaid
graph TB
    subgraph Client["Client Layer"]
        T[Cash Terminal<br/>canteen.html]
        A[Admin Panel<br/>admin.html]
        C[Employee Cabinet<br/>cabinet.html]
        TG[Telegram Bot]
    end

    subgraph Server["Application Server (FastAPI)"]
        AUTH[Auth Router]
        PAY[Payment Router]
        LIVE[Liveness Router]
        CASH[Cashiers Router]
        SVC[Payment Service]
        CV[CV Utils<br/>face_recognition]
    end

    subgraph Data["Data Layer"]
        PG[(PostgreSQL)]
        SQLITE[(SQLite<br/>Cashiers)]
        FS[Private Photos<br/>Filesystem]
    end

    T --> PAY
    T --> LIVE
    A --> AUTH
    A --> PAY
    C --> PAY
    TG --> AUTH

    PAY --> SVC
    LIVE --> CV
    AUTH --> PG
    PAY --> PG
    LIVE --> PG
    CASH --> SQLITE
    AUTH --> FS
```

## Components

### HTTP Layer (Routers)

| Router | Responsibility |
|--------|---------------|
| `auth.py` | Admin login (JWT), employee CRUD, roles, schedule, biometric enrollment |
| `payment.py` | Payment processing, cash desks, products/categories, statistics |
| `liveness.py` | Face verification sessions, anti-spoofing algorithm |
| `bot.py` | Telegram bot (balance queries, notifications) |
| `cashiers.py` | Cashier management (separate SQLite store) |

### Business Logic Layer

- `services/payment_service.py` — order total calculation, subsidy logic
- `cv_utils.py` — face embedding extraction, comparison with configurable tolerance
- `security.py` — JWT tokens, bcrypt password hashing

### Data Layer

- **PostgreSQL** — primary database (employees, transactions, cards, schedules)
- **SQLite** — lightweight cashier registry (no foreign-key coupling to main DB)
- **Filesystem** — private photo storage (`/app/private_photos/`)

## Payment Flow

```mermaid
sequenceDiagram
    participant T as Terminal
    participant S as Server
    participant DB as PostgreSQL
    participant TG as Telegram

    T->>S: POST /api/start_liveness (card_uid)
    S->>DB: Find employee by card
    S-->>T: session_id

    loop Every 500ms
        T->>S: POST /api/liveness_frame (image)
        S->>S: Extract embedding, compare, check variance
        S-->>T: {status: processing, match_count}
    end

    S-->>T: {status: finished} (liveness passed)
    T->>S: POST /api/pay (session_id, items)
    S->>DB: Verify session.passed, calculate subsidy
    S->>DB: Create transaction, deduct limit
    S-->>T: {status: success}
    S->>TG: Send receipt to employee
```

## Deployment

- **Docker Compose** with 3 services: PostgreSQL, FastAPI (Uvicorn), Caddy (HTTPS)
- Caddy provides automatic TLS certificate management
- Volumes for persistent data (PostgreSQL, Caddy certs)
