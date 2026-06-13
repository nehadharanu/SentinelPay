# SentinelPay

![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111+-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-7-DC382D?style=for-the-badge&logo=redis&logoColor=white)
![Claude AI](https://img.shields.io/badge/Claude-claude--sonnet--4--6-D4A017?style=for-the-badge&logo=anthropic&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![Tests](https://img.shields.io/badge/Tests-89%20passing-22C55E?style=for-the-badge&logo=pytest&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-6B7280?style=for-the-badge)

> **AI-powered payment fraud detection engine — real-time transaction scoring via a deterministic 3-layer pipeline backed by PostgreSQL, Redis, and Anthropic Claude.**

---

## Architecture

```
                         ┌─────────────────────────────────────────────────────────┐
                         │                  SentinelPay Pipeline                   │
                         └─────────────────────────────────────────────────────────┘

  Merchant API
  Request
      │
      ▼
 ┌─────────┐    JWT     ┌──────────────┐
 │  POST   │───Auth────▶│  FastAPI     │
 │/analyze │            │  Endpoint    │
 └─────────┘            └──────┬───────┘
                               │ save transaction
                               ▼
                        ┌──────────────┐
                        │  PostgreSQL  │  (transactions table)
                        └──────┬───────┘
                               │
                               ▼
                   ┌───────────────────────┐
                   │   LAYER 1             │
                   │   Rule Engine         │◀── PostgreSQL rules table (cached 60s)
                   │                       │◀── Redis blacklists (cards/IPs/devices)
                   │  • Blacklist checks   │
                   │  • Amount thresholds  │
                   │  • Velocity counters  │
                   │  • Impossible travel  │
                   └───────────┬───────────┘
                               │
                     ┌─────────┴──────────┐
                     │                    │
                   BLOCK?               PASS / FLAG
                     │                    │
                     ▼                    ▼
              ┌─────────────┐  ┌───────────────────────┐
              │  BLOCK      │  │   LAYER 2             │
              │  (skip L2   │  │   Behavioral Profiler │◀── Redis profile hash
              │   and L3)   │  │                       │       (per card, 30d TTL)
              └─────────────┘  │  • Amount spike       │
                               │  • Std dev deviation  │
                               │  • New device         │
                               │  • New country        │
                               │  • Frequency spike    │
                               │  • New MCC category   │
                               └───────────┬───────────┘
                                           │  score 0.0 – 1.0
                                           ▼
                               ┌───────────────────────┐
                               │   LAYER 3             │
                               │   Claude AI Scorer    │──▶ Anthropic API
                               │   claude-sonnet-4-6   │    (temperature=0)
                               │                       │
                               │  • Holistic reasoning │
                               │  • Pattern synthesis  │
                               │  • Risk score 0–100   │
                               └───────────┬───────────┘
                                           │
                                           ▼
                               ┌───────────────────────┐
                               │   Decision Matrix     │
                               │                       │
                               │  APPROVE / FLAG /     │
                               │  REVIEW  / BLOCK      │
                               └───────────┬───────────┘
                                           │ save decision
                                           ▼
                                    ┌──────────────┐
                                    │  PostgreSQL  │  (fraud_decisions table)
                                    └──────────────┘
                                           │
                                           ▼
                                  JSON Response to Merchant
```

---

## Features

- **3-Layer Fraud Pipeline** — deterministic rules → behavioral profiling → Claude AI, each layer informing the next
- **Real-Time Scoring** — sub-500ms end-to-end decisions including the AI call
- **Behavioral Profiling** — per-card rolling statistics in Redis using Welford's online algorithm; no unbounded history storage
- **Impossible Travel Detection** — Haversine great-circle distance check against last known location
- **Dynamic Rules Engine** — admins create/update/toggle fraud rules at runtime; active in under 60 seconds
- **Redis Blacklists** — instant hard-block for flagged cards, IPs, and device fingerprints
- **JWT Authentication** — short-lived access tokens (30 min) + long-lived refresh tokens (7 days)
- **Role-Based Access Control** — `merchant` and `admin` roles with strict endpoint-level enforcement
- **Idempotency** — `external_transaction_id` prevents duplicate analysis of the same transaction
- **Graceful AI Degradation** — Anthropic API outages fall back to MEDIUM risk without crashing
- **Full Audit Trail** — every decision stored with per-layer breakdown for dispute resolution
- **Interactive API Docs** — Swagger UI at `/docs`, ReDoc at `/redoc`
- **89 Tests** — unit, integration, and end-to-end coverage across all layers

---

## Tech Stack

| Component | Technology | Purpose |
|---|---|---|
| **Web Framework** | [FastAPI](https://fastapi.tiangolo.com/) 0.111+ | Async REST API, OpenAPI docs generation |
| **Database** | [PostgreSQL](https://www.postgresql.org/) 15 | Persistent storage for transactions, decisions, rules, users |
| **Cache / Profiles** | [Redis](https://redis.io/) 7 | Behavioral profiles, velocity counters, blacklists |
| **AI Scorer** | [Anthropic Claude](https://www.anthropic.com/) `claude-sonnet-4-6` | Holistic risk reasoning over transaction context |
| **ORM** | [SQLAlchemy](https://www.sqlalchemy.org/) 2.0 (async) | Database models and async query interface |
| **Migrations** | [Alembic](https://alembic.sqlalchemy.org/) | Schema version control |
| **Auth** | [python-jose](https://github.com/mpdavis/python-jose) + [passlib](https://passlib.readthedocs.io/) | JWT HS256 tokens, bcrypt password hashing |
| **Validation** | [Pydantic](https://docs.pydantic.dev/) v2 | Request/response validation and serialization |
| **ASGI Server** | [Uvicorn](https://www.uvicorn.org/) | Production async server |
| **HTTP Client** | [httpx](https://www.python-httpx.org/) | Async HTTP for the Anthropic SDK |
| **Containerization** | [Docker](https://www.docker.com/) + Compose | One-command local environment |
| **Testing** | [pytest](https://pytest.org/) + pytest-asyncio | 89-test suite across unit/integration/e2e |

---

## How It Works

### Layer 1 — Rule Engine (Deterministic)

The first and fastest check. Evaluates four rule types in strict order:

| Rule Type | What It Checks | Outcome |
|---|---|---|
| **Blacklist** | Card last4 / IP address / device fingerprint in Redis SET | Immediate **BLOCK** |
| **Amount** | Transaction amount vs configurable thresholds | **FLAG** (>$10k) or **BLOCK** (>$50k) |
| **Velocity** | Transaction count on card in last 1h / 24h via Redis counters | **FLAG** or **BLOCK** |
| **Geo** | Haversine distance from last known location vs time elapsed | **FLAG** (impossible travel) |

Rules are loaded from PostgreSQL on startup and **cached in memory for 60 seconds**. A hard BLOCK from Layer 1 short-circuits the pipeline — Layers 2 and 3 are skipped entirely.

### Layer 2 — Behavioral Profiler (Statistical)

Maintains a rolling behavioral profile per card in Redis (30-day TTL). Scores six anomaly signals:

| Signal | Score Delta | Trigger Condition |
|---|---|---|
| `AMOUNT_SPIKE` | +0.30 | Amount > 3× historical average |
| `NEW_COUNTRY` | +0.25 | Country code not in card's known countries |
| `NEW_DEVICE` | +0.20 | Device fingerprint not in card's known devices |
| `AMOUNT_DEVIATION` | +0.20 | Amount > mean + 2× standard deviation |
| `FREQUENCY_SPIKE` | +0.15 | Transaction count this week unusually high |
| `NEW_MERCHANT_CATEGORY` | +0.10 | First transaction in this MCC type |

The final `behavioral_score` is clamped to `[0.0, 1.0]`. After scoring, the profile is updated using **Welford's online algorithm** — accurate rolling mean and standard deviation using only three stored values, no unbounded history.

### Layer 3 — Claude AI Scorer (Holistic)

Sends the full transaction context — along with Layer 1 reasons and Layer 2 anomalies — to `claude-sonnet-4-6` at `temperature=0` (deterministic). Claude returns a structured JSON risk assessment:

```json
{
  "risk_score": 87,
  "risk_level": "CRITICAL",
  "explanation": "Impossible travel with new device and new country strongly indicates stolen card.",
  "recommended_action": "BLOCK"
}
```

If the Anthropic API is unreachable, the scorer returns a safe `MEDIUM` fallback — the system never crashes or drops a transaction.

### Final Decision Matrix

The `FraudEngine` combines all three layer outputs into a single decision:

| Layer 1 | Behavioral Score | AI Risk Level | Final Decision |
|---|---|---|---|
| BLOCK | any | skipped | **BLOCK** |
| any | any | CRITICAL | **BLOCK** |
| FLAG | any | HIGH or CRITICAL | **BLOCK** |
| any | > 0.55 | any | **REVIEW** |
| any | 0.25 – 0.55 | HIGH | **REVIEW** |
| any | 0.25 – 0.55 | LOW / MEDIUM | **FLAG** |
| any | < 0.25 | LOW | **APPROVE** |
| any | < 0.25 | MEDIUM | **FLAG** |

---

## Quick Start

### Prerequisites

- [Docker](https://www.docker.com/) and Docker Compose
- An [Anthropic API key](https://console.anthropic.com/)

### 1. Clone the repository

```bash
git clone https://github.com/your-username/sentinelpay.git
cd sentinelpay
```

### 2. Configure environment

```bash
cp .env.example .env
```

Open `.env` and fill in your values:

```env
DATABASE_URL=postgresql+asyncpg://sentinel:sentinel@db:5432/sentinelpay
REDIS_URL=redis://redis:6379/0
ANTHROPIC_API_KEY=sk-ant-your-key-here
SECRET_KEY=your-secret-key-minimum-32-characters-long

# Optional — these have sensible defaults
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
AMOUNT_SOFT_LIMIT=10000.0
AMOUNT_HARD_LIMIT=50000.0
VELOCITY_1H_THRESHOLD=5
VELOCITY_24H_THRESHOLD=20
IMPOSSIBLE_TRAVEL_HOURS=2
IMPOSSIBLE_TRAVEL_KM=500.0
```

### 3. Start all services

```bash
docker-compose up --build
```

This starts PostgreSQL, Redis, and the SentinelPay API. Tables are created automatically on first boot.

### 4. Verify the service is healthy

```bash
curl http://localhost:8000/health
```

```json
{
  "status": "ok",
  "version": "1.0.0",
  "database": "ok",
  "redis": "ok"
}
```

### 5. Explore the API

- **Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc:** [http://localhost:8000/redoc](http://localhost:8000/redoc)

### Local development (without Docker)

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Ensure PostgreSQL and Redis are running locally, then:
uvicorn app.main:app --reload
```

---

## API Reference

### Authentication

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/api/v1/auth/register` | Public | Register a new merchant or admin account |
| `POST` | `/api/v1/auth/login` | Public | Login and receive access + refresh tokens |
| `POST` | `/api/v1/auth/refresh` | Public | Exchange refresh token for a new access token |
| `POST` | `/api/v1/auth/logout` | Bearer | Invalidate session (client-side token discard) |

### Transactions

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/api/v1/transactions/analyze` | Bearer | Submit a transaction for real-time fraud analysis |
| `GET` | `/api/v1/transactions/` | Bearer | List transactions (merchants see own; admins see all) |
| `GET` | `/api/v1/transactions/{id}` | Bearer | Retrieve a single transaction by UUID |
| `GET` | `/api/v1/transactions/{id}/decision` | Bearer | Retrieve the full fraud decision for a transaction |

### Rules (Admin only)

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/api/v1/rules/` | Admin | List all fraud rules with optional filters |
| `POST` | `/api/v1/rules/` | Admin | Create a new fraud detection rule |
| `PUT` | `/api/v1/rules/{id}` | Admin | Update an existing rule |
| `DELETE` | `/api/v1/rules/{id}` | Admin | Permanently delete a rule |
| `PUT` | `/api/v1/rules/{id}/toggle` | Admin | Enable or disable a rule without deleting it |

### Admin

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/api/v1/admin/metrics` | Admin | System-wide fraud metrics and latency percentiles |
| `GET` | `/api/v1/admin/users` | Admin | List all registered users |
| `PUT` | `/api/v1/admin/users/{id}/role` | Admin | Update a user's role or active status |

---

## Example: Fraud Detection Response

**Request**

```bash
curl -X POST http://localhost:8000/api/v1/transactions/analyze \
  -H "Authorization: Bearer <your_access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "external_transaction_id": "txn-20260613-00142",
    "amount": "2850.00",
    "currency": "USD",
    "card_last4": "7734",
    "card_bin": "411111",
    "cardholder_name": "Jane Smith",
    "merchant_category_code": "5094",
    "merchant_name": "Diamond Palace Jewelers",
    "ip_address": "203.0.113.42",
    "device_fingerprint": "android-d9f3a1c8-new",
    "country_code": "RU",
    "city": "Moscow",
    "latitude": 55.755826,
    "longitude": 37.617300
  }'
```

**Response**

```json
{
  "transaction_id": "a3f8c2d1-4e7b-4a9c-8f1d-2b6e3a5c7d9f",
  "external_transaction_id": "txn-20260613-00142",
  "final_decision": "BLOCK",
  "recommended_action": "BLOCK",
  "processing_ms": 312,
  "layers": {
    "rule_engine": {
      "result": "FLAG",
      "reasons": [
        "IMPOSSIBLE_TRAVEL"
      ]
    },
    "behavioral_profiler": {
      "behavioral_score": 0.85,
      "anomalies": [
        "AMOUNT_SPIKE",
        "NEW_DEVICE",
        "NEW_COUNTRY",
        "NEW_MERCHANT_CATEGORY"
      ]
    },
    "ai_scorer": {
      "risk_score": 91,
      "risk_level": "CRITICAL",
      "explanation": "Transaction in Russia with impossible travel from the US combined with a new device, new country, new merchant category, and an amount 3x above the card's historical average strongly indicates a stolen card or account takeover. Immediate block recommended.",
      "skipped": false
    }
  },
  "created_at": "2026-06-13T09:14:22.418Z"
}
```

**Clean transaction — same card, expected behaviour**

```json
{
  "transaction_id": "b7d2e9f4-1c3a-4b8d-9e2f-6a4c5d8e1f3b",
  "external_transaction_id": "txn-20260613-00143",
  "final_decision": "APPROVE",
  "recommended_action": "APPROVE",
  "processing_ms": 287,
  "layers": {
    "rule_engine": {
      "result": "PASS",
      "reasons": []
    },
    "behavioral_profiler": {
      "behavioral_score": 0.0,
      "anomalies": []
    },
    "ai_scorer": {
      "risk_score": 8,
      "risk_level": "LOW",
      "explanation": "Transaction matches the cardholder's established spending patterns with no anomalous signals detected across any layer.",
      "skipped": false
    }
  },
  "created_at": "2026-06-13T09:15:03.721Z"
}
```

---

## Testing

SentinelPay ships with **89 tests** across three layers of coverage.

```bash
# Install test dependencies
pip install -r requirements.txt

# Run the full suite
pytest

# Run with coverage report
pytest --cov=app --cov-report=term-missing

# Run only unit tests (no external services needed)
pytest tests/unit/

# Run only integration tests
pytest tests/integration/

# Run end-to-end pipeline tests
pytest tests/e2e/
```

### Test breakdown

```
tests/
├── unit/                        # Pure logic, no I/O — fast
│   ├── test_rule_engine.py      # Rule evaluation, blacklist logic, velocity checks
│   ├── test_behavioral_profiler.py  # Anomaly scoring, Welford's algorithm
│   ├── test_ai_scorer.py        # Claude response parsing, fallback behaviour
│   ├── test_fraud_engine.py     # Decision matrix, pipeline orchestration
│   ├── test_geo.py              # Haversine formula, impossible travel
│   └── test_security.py         # JWT encode/decode, bcrypt hashing
│
├── integration/                 # Full HTTP stack against test database
│   ├── test_auth_endpoints.py   # Register, login, refresh, logout flows
│   ├── test_transaction_endpoints.py  # Analyze, list, get, pagination
│   ├── test_rules_endpoints.py  # CRUD, toggle, admin-only enforcement
│   └── test_admin_endpoints.py  # Metrics, user management
│
└── e2e/
    └── test_full_pipeline.py    # Full fraud detection flow, all decision outcomes
```

---

## Project Structure

```
SentinelPay/
│
├── app/
│   ├── main.py                  # FastAPI app factory, lifespan, global error handler
│   ├── config.py                # Pydantic BaseSettings — all config from env
│   ├── dependencies.py          # FastAPI Depends() callables: auth, Redis, FraudEngine
│   │
│   ├── api/v1/
│   │   ├── router.py            # Mounts all sub-routers under /api/v1
│   │   └── endpoints/
│   │       ├── auth.py          # POST /auth/* — register, login, refresh, logout
│   │       ├── transactions.py  # POST+GET /transactions/* — analyze and retrieve
│   │       ├── rules.py         # CRUD /rules/* — admin-only rule management
│   │       └── admin.py         # GET /admin/* — metrics and user management
│   │
│   ├── core/
│   │   ├── security.py          # JWT encode/decode, bcrypt hash/verify
│   │   └── exceptions.py        # Typed HTTP exception classes with consistent envelope
│   │
│   ├── db/
│   │   ├── base.py              # SQLAlchemy DeclarativeBase shared by all models
│   │   ├── session.py           # Async engine + session factory + get_db()
│   │   └── init_db.py           # create_all on startup
│   │
│   ├── models/                  # SQLAlchemy ORM models (PostgreSQL tables)
│   │   ├── user.py              # users — email, role, merchant_id, hashed_password
│   │   ├── transaction.py       # transactions — full payment context
│   │   ├── fraud_decision.py    # fraud_decisions — all 3 layer outputs + final decision
│   │   └── rule.py              # rules — type, condition JSONB, action, active flag
│   │
│   ├── schemas/                 # Pydantic v2 request/response models
│   │   ├── auth.py              # RegisterRequest, LoginRequest, TokenResponse, ...
│   │   ├── transaction.py       # TransactionCreate (with validators), TransactionResponse
│   │   ├── fraud.py             # FraudDecisionResponse, LayersResponse, ...
│   │   └── rule.py              # RuleCreate, RuleUpdate, RuleToggle, PaginatedRules
│   │
│   ├── services/                # Business logic — no HTTP concerns
│   │   ├── fraud_engine.py      # Orchestrator: runs all 3 layers, applies decision matrix
│   │   ├── rule_engine.py       # Layer 1: blacklists, amount, velocity, geo rules
│   │   ├── behavioral_profiler.py  # Layer 2: Redis profiles, anomaly scoring, Welford's
│   │   ├── ai_scorer.py         # Layer 3: Anthropic Claude API call, JSON parsing
│   │   └── transaction_service.py  # PostgreSQL CRUD for transactions and decisions
│   │
│   └── utils/
│       └── geo.py               # haversine_km(), is_impossible_travel()
│
├── alembic/                     # Database migration scripts
│   ├── env.py
│   └── versions/
│
├── tests/
│   ├── conftest.py
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── requirements.txt
├── pytest.ini
└── ARCHITECTURE.md              # Detailed system design document
```

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | Yes | — | Async PostgreSQL DSN (`postgresql+asyncpg://...`) |
| `REDIS_URL` | Yes | — | Redis DSN (`redis://...`) |
| `ANTHROPIC_API_KEY` | Yes | — | Anthropic secret key for Claude API |
| `SECRET_KEY` | Yes | — | JWT signing secret (minimum 32 characters) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | `30` | Access token TTL in minutes |
| `REFRESH_TOKEN_EXPIRE_DAYS` | No | `7` | Refresh token TTL in days |
| `RULES_CACHE_TTL_SECONDS` | No | `60` | How often the rule engine refreshes from PostgreSQL |
| `AMOUNT_SOFT_LIMIT` | No | `10000.0` | Amount above which Layer 1 issues a FLAG |
| `AMOUNT_HARD_LIMIT` | No | `50000.0` | Amount above which Layer 1 issues a BLOCK |
| `VELOCITY_1H_THRESHOLD` | No | `5` | Max transactions per card per hour before FLAG |
| `VELOCITY_24H_THRESHOLD` | No | `20` | Max transactions per card per 24h before BLOCK |
| `IMPOSSIBLE_TRAVEL_HOURS` | No | `2` | Time window for impossible travel check |
| `IMPOSSIBLE_TRAVEL_KM` | No | `500.0` | Distance threshold for impossible travel |
| `ENVIRONMENT` | No | `development` | `development` or `production` |
| `LOG_LEVEL` | No | `INFO` | Python logging level |

---

## Error Responses

All errors return a consistent JSON envelope:

```json
{
  "error": {
    "code": "DUPLICATE_TRANSACTION",
    "message": "A transaction with this ID has already been analyzed.",
    "details": {}
  }
}
```

| Status | Code | When |
|---|---|---|
| `400` | `EMAIL_ALREADY_REGISTERED` | Registration with an existing email |
| `400` | `DUPLICATE_TRANSACTION` | `external_transaction_id` already analyzed |
| `401` | `INVALID_CREDENTIALS` | Wrong email or password |
| `401` | `TOKEN_EXPIRED` | Access token past its TTL |
| `401` | `INVALID_TOKEN` | Malformed or missing Bearer token |
| `403` | `FORBIDDEN` | Merchant accessing another merchant's data or admin-only endpoint |
| `404` | `TRANSACTION_NOT_FOUND` | Unknown transaction UUID |
| `404` | `RULE_NOT_FOUND` | Unknown rule UUID |
| `422` | _(Pydantic)_ | Request body validation failure |
| `503` | `AI_SCORER_UNAVAILABLE` | Anthropic API unreachable (fallback applied) |

---

## License

```
MIT License

Copyright (c) 2026 SentinelPay

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
