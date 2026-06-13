# SentinelPay — System Architecture

## 1. System Overview

SentinelPay is an async, AI-powered fraud detection engine exposed as a REST API. Merchants submit payment transactions; SentinelPay returns a fraud decision in real time using a deterministic 3-layer pipeline. Every decision is persisted to PostgreSQL for audit and analytics.

---

## 2. Technology Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| Web framework | FastAPI | 0.111+ |
| ASGI server | Uvicorn | 0.29+ |
| ORM | SQLAlchemy (async) | 2.0+ |
| Database | PostgreSQL | 15 |
| Cache / behavioral store | Redis | 7 |
| AI scorer | Anthropic Claude API | claude-sonnet-4-6 |
| Auth | JWT (python-jose) | HS256 |
| Password hashing | passlib[bcrypt] | — |
| Migrations | Alembic | — |
| HTTP client | httpx | async |
| Containerisation | Docker + docker-compose | — |

---

## 3. Full Folder Structure

```
SentinelPay/
├── app/
│   ├── __init__.py
│   ├── main.py                        # FastAPI app factory, lifespan, middleware
│   ├── config.py                      # Pydantic BaseSettings; reads .env
│   ├── dependencies.py                # Shared FastAPI Depends() callables
│   │
│   ├── api/
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── router.py              # Mounts all v1 sub-routers
│   │       └── endpoints/
│   │           ├── __init__.py
│   │           ├── auth.py            # /auth/* routes
│   │           ├── transactions.py    # /transactions/* routes
│   │           ├── rules.py           # /rules/* routes (admin)
│   │           └── admin.py           # /admin/* routes (admin)
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── security.py                # JWT encode/decode, password hash/verify
│   │   └── exceptions.py             # Custom HTTP exception classes
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── base.py                    # DeclarativeBase, metadata
│   │   ├── session.py                 # Async engine + AsyncSessionLocal factory
│   │   └── init_db.py                 # Creates tables on startup
│   │
│   ├── models/                        # SQLAlchemy ORM models (PostgreSQL tables)
│   │   ├── __init__.py
│   │   ├── user.py                    # users table
│   │   ├── transaction.py             # transactions table
│   │   ├── fraud_decision.py          # fraud_decisions table
│   │   └── rule.py                    # rules table
│   │
│   ├── schemas/                       # Pydantic v2 request/response models
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── transaction.py
│   │   ├── fraud.py
│   │   └── rule.py
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── fraud_engine.py            # Orchestrator: calls all 3 layers in order
│   │   ├── rule_engine.py             # Layer 1: deterministic rule evaluation
│   │   ├── behavioral_profiler.py     # Layer 2: Redis read/write, anomaly scoring
│   │   ├── ai_scorer.py               # Layer 3: Claude API call, response parsing
│   │   └── transaction_service.py     # Transaction CRUD against PostgreSQL
│   │
│   └── utils/
│       ├── __init__.py
│       └── geo.py                     # Haversine distance, impossible-travel calc
│
├── alembic/
│   ├── alembic.ini
│   ├── env.py
│   └── versions/                      # Migration scripts
│
├── tests/                             # Populated by tester agent
│
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── requirements.txt
└── ARCHITECTURE.md                    # This file
```

---

## 4. Database Schema

### 4.1 `users`
| Column | Type | Constraints |
|--------|------|------------|
| id | UUID | PK, default gen_random_uuid() |
| email | VARCHAR(255) | UNIQUE, NOT NULL |
| hashed_password | VARCHAR(255) | NOT NULL |
| role | ENUM('merchant','admin') | NOT NULL, default 'merchant' |
| merchant_id | VARCHAR(100) | UNIQUE, NOT NULL — caller's business identifier |
| is_active | BOOLEAN | NOT NULL, default TRUE |
| created_at | TIMESTAMPTZ | NOT NULL, default now() |
| updated_at | TIMESTAMPTZ | NOT NULL, default now() |

### 4.2 `transactions`
| Column | Type | Constraints |
|--------|------|------------|
| id | UUID | PK |
| merchant_id | VARCHAR(100) | NOT NULL, FK → users.merchant_id |
| external_transaction_id | VARCHAR(255) | UNIQUE, NOT NULL — idempotency key |
| amount | NUMERIC(18,2) | NOT NULL |
| currency | CHAR(3) | NOT NULL |
| card_last4 | CHAR(4) | NOT NULL |
| card_bin | VARCHAR(8) | NOT NULL |
| cardholder_name | VARCHAR(255) | NOT NULL |
| merchant_category_code | VARCHAR(4) | NOT NULL |
| merchant_name | VARCHAR(255) | NOT NULL |
| ip_address | INET | NOT NULL |
| device_fingerprint | VARCHAR(255) | NOT NULL |
| country_code | CHAR(2) | NOT NULL |
| city | VARCHAR(100) | |
| latitude | NUMERIC(9,6) | |
| longitude | NUMERIC(9,6) | |
| created_at | TIMESTAMPTZ | NOT NULL, default now() |

### 4.3 `fraud_decisions`
| Column | Type | Constraints |
|--------|------|------------|
| id | UUID | PK |
| transaction_id | UUID | FK → transactions.id, UNIQUE |
| layer1_result | ENUM('PASS','FLAG','BLOCK') | NOT NULL |
| layer1_reasons | JSONB | NOT NULL — array of reason code strings |
| layer2_behavioral_score | NUMERIC(4,3) | NOT NULL — 0.000–1.000 |
| layer2_anomalies | JSONB | NOT NULL — array of anomaly strings |
| layer3_risk_score | INTEGER | — null if skipped (0–100) |
| layer3_risk_level | ENUM('LOW','MEDIUM','HIGH','CRITICAL') | — null if skipped |
| layer3_explanation | TEXT | — null if skipped |
| final_decision | ENUM('APPROVE','FLAG','REVIEW','BLOCK') | NOT NULL |
| recommended_action | VARCHAR(255) | NOT NULL |
| processing_ms | INTEGER | NOT NULL — end-to-end latency |
| created_at | TIMESTAMPTZ | NOT NULL, default now() |

### 4.4 `rules`
| Column | Type | Constraints |
|--------|------|------------|
| id | UUID | PK |
| name | VARCHAR(100) | UNIQUE, NOT NULL |
| rule_type | ENUM('velocity','amount','geo','blacklist') | NOT NULL |
| condition | JSONB | NOT NULL — rule parameters (see Layer 1 spec) |
| action | ENUM('FLAG','BLOCK') | NOT NULL |
| is_active | BOOLEAN | NOT NULL, default TRUE |
| created_by | UUID | FK → users.id |
| created_at | TIMESTAMPTZ | NOT NULL, default now() |
| updated_at | TIMESTAMPTZ | NOT NULL, default now() |

---

## 5. Redis Data Structures

All keys are namespaced as `sentinelpay:{type}:{identifier}`.

### 5.1 Velocity counters
```
Key:    sentinelpay:velocity:{card_last4}:{window}
Type:   STRING (integer)
TTL:    window duration (3600s for 1h, 86400s for 24h)
Value:  transaction count in window
```

### 5.2 Behavioral profile
```
Key:    sentinelpay:profile:{card_last4}
Type:   HASH
TTL:    30 days (2592000s)
Fields:
  avg_amount_<mcc>        — rolling average spend for merchant category
  tx_count_total          — lifetime transaction count
  tx_count_7d             — 7-day rolling count
  known_devices           — JSON array of known device fingerprints (max 10)
  known_countries         — JSON array of known country codes (max 20)
  last_tx_country         — last transaction country
  last_tx_lat             — last transaction latitude
  last_tx_lon             — last transaction longitude
  last_tx_timestamp       — ISO-8601 timestamp of last transaction
  avg_amount_overall      — rolling average of all transaction amounts
  stddev_amount           — rolling std deviation of amounts
```

### 5.3 Blacklists
```
Key:    sentinelpay:blacklist:cards      — Redis SET of blocked card_last4 values
Key:    sentinelpay:blacklist:ips        — Redis SET of blocked IP addresses
Key:    sentinelpay:blacklist:devices    — Redis SET of blocked device fingerprints
TTL:    none (permanent until removed)
```

---

## 6. The 3-Layer Fraud Detection Pipeline

### Entry Point
`FraudEngine.analyze(transaction: TransactionCreate) -> FraudDecisionResult`

All three layers are called sequentially. The engine short-circuits after Layer 1 only if the result is BLOCK. Otherwise all three layers always run (Layers 2 and 3 may be skipped if the result is obvious—see decision matrix).

---

### Layer 1 — Rule Engine (`rule_engine.py`)

**Input:** `TransactionCreate` schema  
**Output:** `RuleResult(result: Literal['PASS','FLAG','BLOCK'], reasons: list[str])`

Rules are loaded from the `rules` table at startup and cached in memory (refreshed every 60 seconds).

**Built-in rule evaluations (in order):**

1. **Blacklist check**
   - If `card_last4` in `sentinelpay:blacklist:cards` → BLOCK, reason: `BLACKLISTED_CARD`
   - If `ip_address` in `sentinelpay:blacklist:ips` → BLOCK, reason: `BLACKLISTED_IP`
   - If `device_fingerprint` in `sentinelpay:blacklist:devices` → BLOCK, reason: `BLACKLISTED_DEVICE`

2. **Amount threshold** (from `rules` table, type=`amount`)
   - Default: amount > 50,000 → BLOCK, reason: `AMOUNT_EXCEEDS_HARD_LIMIT`
   - Default: amount > 10,000 → FLAG, reason: `AMOUNT_EXCEEDS_SOFT_LIMIT`

3. **Velocity check** (from `rules` table, type=`velocity`)
   - Default: >5 transactions on same card in 1 hour → FLAG, reason: `VELOCITY_1H_EXCEEDED`
   - Default: >20 transactions on same card in 24 hours → BLOCK, reason: `VELOCITY_24H_EXCEEDED`

4. **Geo / impossible travel** (from `rules` table, type=`geo`)
   - If last transaction was in a different country AND time delta < 2 hours AND haversine distance > 500 km → FLAG, reason: `IMPOSSIBLE_TRAVEL`

**Result aggregation:**
- If any rule returns BLOCK → final result is BLOCK
- If any rule returns FLAG → final result is FLAG
- Otherwise → PASS

---

### Layer 2 — Redis Behavioral Profiler (`behavioral_profiler.py`)

**Input:** `TransactionCreate`, `RuleResult`  
**Output:** `BehavioralResult(behavioral_score: float, anomalies: list[str])`

behavioral_score is 0.0 (normal) to 1.0 (highly anomalous).

**Scoring logic:**

Each anomaly adds to a raw score; the final score is clamped to [0.0, 1.0].

| Anomaly check | Score delta | Anomaly code |
|---|---|---|
| Amount > 3× avg_amount_overall | +0.30 | `AMOUNT_SPIKE` |
| Amount > avg + 2×stddev | +0.20 | `AMOUNT_DEVIATION` |
| Unknown device_fingerprint | +0.20 | `NEW_DEVICE` |
| Unknown country_code | +0.25 | `NEW_COUNTRY` |
| tx_count_7d > 2× historical weekly avg | +0.15 | `FREQUENCY_SPIKE` |
| New MCC (no prior spend in category) | +0.10 | `NEW_MERCHANT_CATEGORY` |

After scoring, the profile is updated:
- Increment velocity counters
- Update rolling averages (Welford's online algorithm for avg + stddev)
- Append device/country to known sets (capped at 10 / 20)
- Update last_tx fields

---

### Layer 3 — Claude AI Risk Scorer (`ai_scorer.py`)

**Input:** `TransactionCreate`, `RuleResult`, `BehavioralResult`  
**Output:** `AIResult(risk_score: int, risk_level: str, explanation: str, recommended_action: str)` or `None` if skipped

**When Layer 3 is invoked:**
- Always invoked unless Layer 1 = BLOCK (hard stop, no AI needed)

**Claude API call spec:**
- Model: `claude-sonnet-4-6`
- Max tokens: 512
- Temperature: 0 (deterministic)
- System prompt: instructs Claude to act as a payment fraud analyst and return a strict JSON object
- User prompt: serialised JSON of transaction data + Layer 1 reasons + Layer 2 anomalies + behavioral score

**Required Claude response format (JSON, no prose):**
```json
{
  "risk_score": 0-100,
  "risk_level": "LOW" | "MEDIUM" | "HIGH" | "CRITICAL",
  "explanation": "one or two sentences",
  "recommended_action": "APPROVE" | "FLAG" | "REVIEW" | "BLOCK"
}
```

The response is parsed with `json.loads`. If parsing fails, the scorer logs the error and returns `risk_score=50, risk_level=MEDIUM, recommended_action=REVIEW`.

---

### Final Decision Matrix

| Layer 1 | Behavioral Score | Layer 3 Risk Level | Final Decision |
|---------|-----------------|-------------------|----------------|
| BLOCK | any | skipped | BLOCK |
| PASS or FLAG | < 0.25 | LOW | APPROVE |
| PASS or FLAG | < 0.25 | MEDIUM | FLAG |
| PASS or FLAG | 0.25–0.55 | LOW or MEDIUM | FLAG |
| PASS or FLAG | 0.25–0.55 | HIGH | REVIEW |
| PASS or FLAG | > 0.55 | any | REVIEW |
| PASS or FLAG | any | CRITICAL | BLOCK |
| FLAG | any | HIGH or CRITICAL | BLOCK |

`recommended_action` in the response equals the Final Decision value.

---

## 7. Authentication & Authorization

**Mechanism:** JWT Bearer tokens (HS256)  
**Access token TTL:** 30 minutes  
**Refresh token TTL:** 7 days  
**Roles:** `merchant`, `admin`

**Endpoint access matrix:**

| Endpoint group | merchant | admin |
|---|---|---|
| POST /auth/* | public | public |
| POST /transactions/analyze | ✓ | ✓ |
| GET /transactions/{id} | own only | all |
| GET /transactions/ | own only | all |
| GET /transactions/{id}/decision | own only | all |
| GET/POST/PUT/DELETE /rules/* | ✗ | ✓ |
| GET /admin/* | ✗ | ✓ |

Merchants can only read transactions where `transaction.merchant_id == current_user.merchant_id`.

---

## 8. Request/Response Flow (sequence)

```
Client
  │
  ▼
POST /api/v1/transactions/analyze
  │
  ▼
JWT validation (dependencies.py: get_current_user)
  │
  ▼
TransactionService.create_pending(tx_data) → saves to transactions table
  │
  ▼
FraudEngine.analyze(tx_data)
  │
  ├─▶ RuleEngine.evaluate(tx_data)          → RuleResult
  │
  ├─▶ BehavioralProfiler.score(tx_data)     → BehavioralResult
  │   └─▶ Redis HGET profile
  │   └─▶ Redis INCR velocity counters
  │   └─▶ Redis HSET updated profile
  │
  ├─▶ AIScorer.score(tx_data, r1, r2)       → AIResult (if not BLOCK)
  │   └─▶ Anthropic API (claude-sonnet-4-6)
  │
  └─▶ FraudEngine._decide(r1, r2, r3)       → FraudDecisionResult
        │
        ▼
TransactionService.save_decision(decision)  → saves to fraud_decisions table
  │
  ▼
HTTP 200 JSON response → FraudDecisionResponse schema
```

---

## 9. Configuration (`config.py` — Pydantic BaseSettings)

All values read from environment / `.env` file:

| Setting | Type | Description |
|---------|------|-------------|
| DATABASE_URL | str | asyncpg DSN |
| REDIS_URL | str | Redis DSN |
| ANTHROPIC_API_KEY | str | Anthropic secret key |
| SECRET_KEY | str | JWT signing secret (≥32 chars) |
| ACCESS_TOKEN_EXPIRE_MINUTES | int | default 30 |
| REFRESH_TOKEN_EXPIRE_DAYS | int | default 7 |
| ENVIRONMENT | str | development / production |
| LOG_LEVEL | str | INFO |
| RULES_CACHE_TTL_SECONDS | int | default 60 |
| AMOUNT_SOFT_LIMIT | float | default 10000.0 |
| AMOUNT_HARD_LIMIT | float | default 50000.0 |
| VELOCITY_1H_THRESHOLD | int | default 5 |
| VELOCITY_24H_THRESHOLD | int | default 20 |
| IMPOSSIBLE_TRAVEL_HOURS | int | default 2 |
| IMPOSSIBLE_TRAVEL_KM | float | default 500.0 |

---

## 10. Error Handling

All errors return a consistent envelope:
```json
{
  "error": {
    "code": "ERROR_CODE_CONSTANT",
    "message": "Human-readable description",
    "details": {}
  }
}
```

| HTTP status | When |
|---|---|
| 400 | Validation error, duplicate external_transaction_id |
| 401 | Missing / expired / invalid JWT |
| 403 | Insufficient role |
| 404 | Resource not found |
| 409 | Idempotency conflict (transaction already analyzed) |
| 422 | Pydantic validation failure |
| 500 | Unhandled exception (logged, generic message returned) |
| 503 | Anthropic API unreachable (fallback to MEDIUM score applies) |

---

## 11. Developer Agent — Build Checklist

The Developer agent must produce exactly these files:

```
app/__init__.py
app/main.py
app/config.py
app/dependencies.py
app/api/v1/__init__.py
app/api/v1/router.py
app/api/v1/endpoints/__init__.py
app/api/v1/endpoints/auth.py
app/api/v1/endpoints/transactions.py
app/api/v1/endpoints/rules.py
app/api/v1/endpoints/admin.py
app/core/__init__.py
app/core/security.py
app/core/exceptions.py
app/db/__init__.py
app/db/base.py
app/db/session.py
app/db/init_db.py
app/models/__init__.py
app/models/user.py
app/models/transaction.py
app/models/fraud_decision.py
app/models/rule.py
app/schemas/__init__.py
app/schemas/auth.py
app/schemas/transaction.py
app/schemas/fraud.py
app/schemas/rule.py
app/services/__init__.py
app/services/fraud_engine.py
app/services/rule_engine.py
app/services/behavioral_profiler.py
app/services/ai_scorer.py
app/services/transaction_service.py
app/utils/__init__.py
app/utils/geo.py
alembic/alembic.ini
alembic/env.py
docker-compose.yml
.env.example
requirements.txt
Dockerfile
BUILD_REPORT.md
```

Every function and class must have a docstring. All I/O must use async/await. Follow this ARCHITECTURE.md exactly — no deviations without documenting the reason in BUILD_REPORT.md.
