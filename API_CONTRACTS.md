# SentinelPay — API Contracts

Base URL: `http://localhost:8000/api/v1`  
All requests and responses use `Content-Type: application/json`.  
All authenticated endpoints require: `Authorization: Bearer <access_token>`

---

## Common Schemas

### Error Response (all 4xx / 5xx)
```json
{
  "error": {
    "code": "string",
    "message": "string",
    "details": {}
  }
}
```

### Pagination (for list endpoints)
Query params: `?page=1&page_size=20` (defaults shown)  
Response wrapper:
```json
{
  "items": [...],
  "total": 0,
  "page": 1,
  "page_size": 20,
  "pages": 1
}
```

---

## Auth Endpoints

### POST /auth/register
Register a new merchant account.

**Auth:** None (public)

**Request Body:**
```json
{
  "email": "string (valid email, required)",
  "password": "string (min 8 chars, required)",
  "merchant_id": "string (3–50 alphanumeric+dash, required, unique)",
  "role": "merchant | admin (optional, default: merchant)"
}
```

**Response 201:**
```json
{
  "id": "uuid",
  "email": "string",
  "merchant_id": "string",
  "role": "merchant",
  "is_active": true,
  "created_at": "2024-01-01T00:00:00Z"
}
```

**Errors:**
- `400 EMAIL_ALREADY_REGISTERED` — email in use
- `400 MERCHANT_ID_ALREADY_TAKEN` — merchant_id in use
- `422` — validation failure

---

### POST /auth/login
Obtain access + refresh tokens.

**Auth:** None (public)

**Request Body:**
```json
{
  "email": "string (required)",
  "password": "string (required)"
}
```

**Response 200:**
```json
{
  "access_token": "string (JWT)",
  "refresh_token": "string (JWT)",
  "token_type": "bearer",
  "expires_in": 1800
}
```

**Errors:**
- `401 INVALID_CREDENTIALS` — wrong email or password
- `401 ACCOUNT_INACTIVE` — account disabled

---

### POST /auth/refresh
Exchange refresh token for new access token.

**Auth:** None (public)

**Request Body:**
```json
{
  "refresh_token": "string (required)"
}
```

**Response 200:**
```json
{
  "access_token": "string (JWT)",
  "token_type": "bearer",
  "expires_in": 1800
}
```

**Errors:**
- `401 INVALID_REFRESH_TOKEN`
- `401 REFRESH_TOKEN_EXPIRED`

---

### POST /auth/logout
Invalidate refresh token (client must discard access token).

**Auth:** Bearer token required

**Request Body:**
```json
{
  "refresh_token": "string (required)"
}
```

**Response 200:**
```json
{
  "message": "Successfully logged out"
}
```

**Errors:**
- `401 UNAUTHORIZED`

---

## Transaction Endpoints

### POST /transactions/analyze
Submit a payment transaction for fraud analysis. Returns a complete fraud decision synchronously.

**Auth:** Bearer token (merchant or admin)

**Request Body:**
```json
{
  "external_transaction_id": "string (max 255 chars, required — idempotency key)",
  "amount": "number (positive, max 2 decimal places, required)",
  "currency": "string (ISO-4217 3-letter code, required, e.g. USD)",
  "card_last4": "string (exactly 4 digits, required)",
  "card_bin": "string (6–8 digits, required)",
  "cardholder_name": "string (max 255 chars, required)",
  "merchant_category_code": "string (exactly 4 digits, required)",
  "merchant_name": "string (max 255 chars, required)",
  "ip_address": "string (valid IPv4 or IPv6, required)",
  "device_fingerprint": "string (max 255 chars, required)",
  "country_code": "string (ISO-3166-1 alpha-2, required, e.g. US)",
  "city": "string (max 100 chars, optional)",
  "latitude": "number (-90 to 90, optional)",
  "longitude": "number (-180 to 180, optional)"
}
```

**Response 200:**
```json
{
  "transaction_id": "uuid",
  "external_transaction_id": "string",
  "final_decision": "APPROVE | FLAG | REVIEW | BLOCK",
  "recommended_action": "string",
  "processing_ms": 0,
  "layers": {
    "rule_engine": {
      "result": "PASS | FLAG | BLOCK",
      "reasons": ["string"]
    },
    "behavioral_profiler": {
      "behavioral_score": 0.000,
      "anomalies": ["string"]
    },
    "ai_scorer": {
      "risk_score": 0,
      "risk_level": "LOW | MEDIUM | HIGH | CRITICAL",
      "explanation": "string",
      "skipped": false
    }
  },
  "created_at": "2024-01-01T00:00:00Z"
}
```

**Notes:**
- `ai_scorer.skipped = true` when Layer 1 = BLOCK; in that case `risk_score`, `risk_level`, `explanation` are `null`.
- Submitting the same `external_transaction_id` twice returns `409 DUPLICATE_TRANSACTION`.

**Errors:**
- `400 INVALID_CURRENCY` — currency not in ISO-4217
- `400 INVALID_COUNTRY_CODE` — country_code not in ISO-3166-1
- `409 DUPLICATE_TRANSACTION` — external_transaction_id already analyzed
- `422` — validation failure
- `503 AI_SCORER_UNAVAILABLE` — Anthropic API unreachable (fallback decision still returned)

---

### GET /transactions/{transaction_id}
Retrieve a single transaction by its internal UUID.

**Auth:** Bearer token (merchant: own only; admin: all)

**Path params:**
- `transaction_id` — UUID

**Response 200:**
```json
{
  "id": "uuid",
  "external_transaction_id": "string",
  "merchant_id": "string",
  "amount": "number",
  "currency": "string",
  "card_last4": "string",
  "card_bin": "string",
  "cardholder_name": "string",
  "merchant_category_code": "string",
  "merchant_name": "string",
  "ip_address": "string",
  "device_fingerprint": "string",
  "country_code": "string",
  "city": "string | null",
  "latitude": "number | null",
  "longitude": "number | null",
  "created_at": "2024-01-01T00:00:00Z"
}
```

**Errors:**
- `403 FORBIDDEN` — merchant accessing another merchant's transaction
- `404 TRANSACTION_NOT_FOUND`

---

### GET /transactions/
List transactions with pagination.

**Auth:** Bearer token (merchant: own only; admin: all)

**Query params:**
| Param | Type | Default | Description |
|---|---|---|---|
| page | int | 1 | Page number |
| page_size | int | 20 | Items per page (max 100) |
| final_decision | string | — | Filter: APPROVE, FLAG, REVIEW, BLOCK |
| from_date | datetime | — | ISO-8601, inclusive |
| to_date | datetime | — | ISO-8601, inclusive |
| merchant_id | string | — | Admin only: filter by merchant |

**Response 200:** Paginated list of transaction objects (same schema as GET /transactions/{id})

---

### GET /transactions/{transaction_id}/decision
Retrieve the fraud decision for a specific transaction.

**Auth:** Bearer token (merchant: own only; admin: all)

**Path params:**
- `transaction_id` — UUID

**Response 200:**
```json
{
  "id": "uuid",
  "transaction_id": "uuid",
  "final_decision": "APPROVE | FLAG | REVIEW | BLOCK",
  "recommended_action": "string",
  "processing_ms": 0,
  "layers": {
    "rule_engine": {
      "result": "PASS | FLAG | BLOCK",
      "reasons": ["string"]
    },
    "behavioral_profiler": {
      "behavioral_score": 0.000,
      "anomalies": ["string"]
    },
    "ai_scorer": {
      "risk_score": 0,
      "risk_level": "LOW | MEDIUM | HIGH | CRITICAL",
      "explanation": "string",
      "skipped": false
    }
  },
  "created_at": "2024-01-01T00:00:00Z"
}
```

**Errors:**
- `403 FORBIDDEN`
- `404 TRANSACTION_NOT_FOUND`
- `404 DECISION_NOT_FOUND` — transaction exists but has no decision (should not occur in normal flow)

---

## Rule Endpoints (Admin Only)

### GET /rules/
List all fraud rules.

**Auth:** Bearer token (admin only)

**Query params:**
| Param | Type | Default | Description |
|---|---|---|---|
| page | int | 1 | |
| page_size | int | 20 | |
| rule_type | string | — | velocity, amount, geo, blacklist |
| is_active | bool | — | filter by active status |

**Response 200:** Paginated list of rule objects
```json
{
  "items": [
    {
      "id": "uuid",
      "name": "string",
      "rule_type": "velocity | amount | geo | blacklist",
      "condition": {},
      "action": "FLAG | BLOCK",
      "is_active": true,
      "created_by": "uuid",
      "created_at": "2024-01-01T00:00:00Z",
      "updated_at": "2024-01-01T00:00:00Z"
    }
  ],
  "total": 0,
  "page": 1,
  "page_size": 20,
  "pages": 1
}
```

---

### POST /rules/
Create a new fraud rule.

**Auth:** Bearer token (admin only)

**Request Body:**
```json
{
  "name": "string (unique, max 100 chars, required)",
  "rule_type": "velocity | amount | geo | blacklist (required)",
  "condition": {
    "VELOCITY rule": {
      "window_seconds": 3600,
      "threshold": 5
    },
    "AMOUNT rule": {
      "threshold": 10000.00
    },
    "GEO rule": {
      "max_distance_km": 500,
      "min_hours": 2
    },
    "BLACKLIST rule": {
      "list_key": "sentinelpay:blacklist:cards | sentinelpay:blacklist:ips | sentinelpay:blacklist:devices"
    }
  },
  "action": "FLAG | BLOCK (required)",
  "is_active": "boolean (optional, default true)"
}
```

**Note:** `condition` object shape depends on `rule_type`. Exactly one of the above shapes must be provided.

**Response 201:** Rule object (same schema as GET /rules/ item)

**Errors:**
- `400 RULE_NAME_ALREADY_EXISTS`
- `403 FORBIDDEN`
- `422` — invalid condition for rule_type

---

### PUT /rules/{rule_id}
Update an existing rule.

**Auth:** Bearer token (admin only)

**Path params:**
- `rule_id` — UUID

**Request Body:** Same as POST /rules/ (all fields optional — only provided fields are updated)

**Response 200:** Updated rule object

**Errors:**
- `403 FORBIDDEN`
- `404 RULE_NOT_FOUND`
- `422`

---

### DELETE /rules/{rule_id}
Delete a rule permanently.

**Auth:** Bearer token (admin only)

**Path params:**
- `rule_id` — UUID

**Response 204:** No content

**Errors:**
- `403 FORBIDDEN`
- `404 RULE_NOT_FOUND`

---

### PUT /rules/{rule_id}/toggle
Enable or disable a rule without deleting it.

**Auth:** Bearer token (admin only)

**Path params:**
- `rule_id` — UUID

**Request Body:**
```json
{
  "is_active": "boolean (required)"
}
```

**Response 200:** Updated rule object

**Errors:**
- `403 FORBIDDEN`
- `404 RULE_NOT_FOUND`

---

## Admin Endpoints (Admin Only)

### GET /admin/metrics
System-wide fraud detection metrics.

**Auth:** Bearer token (admin only)

**Query params:**
| Param | Type | Default | Description |
|---|---|---|---|
| from_date | datetime | 24h ago | Start of window |
| to_date | datetime | now | End of window |

**Response 200:**
```json
{
  "period": {
    "from": "2024-01-01T00:00:00Z",
    "to": "2024-01-01T00:00:00Z"
  },
  "totals": {
    "transactions_analyzed": 0,
    "approved": 0,
    "flagged": 0,
    "reviewed": 0,
    "blocked": 0
  },
  "rates": {
    "approval_rate": 0.00,
    "flag_rate": 0.00,
    "review_rate": 0.00,
    "block_rate": 0.00
  },
  "layer_triggers": {
    "layer1_flags": 0,
    "layer1_blocks": 0,
    "layer2_avg_score": 0.000,
    "layer3_avg_risk_score": 0,
    "layer3_skipped": 0
  },
  "performance": {
    "avg_processing_ms": 0,
    "p95_processing_ms": 0,
    "p99_processing_ms": 0
  }
}
```

**Errors:**
- `403 FORBIDDEN`

---

### GET /admin/users
List all registered users.

**Auth:** Bearer token (admin only)

**Query params:**
| Param | Type | Default | Description |
|---|---|---|---|
| page | int | 1 | |
| page_size | int | 20 | |
| role | string | — | merchant, admin |
| is_active | bool | — | |

**Response 200:** Paginated list of user objects
```json
{
  "items": [
    {
      "id": "uuid",
      "email": "string",
      "merchant_id": "string",
      "role": "merchant | admin",
      "is_active": true,
      "created_at": "2024-01-01T00:00:00Z",
      "updated_at": "2024-01-01T00:00:00Z"
    }
  ],
  "total": 0,
  "page": 1,
  "page_size": 20,
  "pages": 1
}
```

**Errors:**
- `403 FORBIDDEN`

---

### PUT /admin/users/{user_id}/role
Update a user's role or active status.

**Auth:** Bearer token (admin only)

**Path params:**
- `user_id` — UUID

**Request Body:**
```json
{
  "role": "merchant | admin (optional)",
  "is_active": "boolean (optional)"
}
```

At least one field must be provided.

**Response 200:** Updated user object

**Errors:**
- `403 FORBIDDEN`
- `404 USER_NOT_FOUND`
- `400 CANNOT_DEMOTE_SELF` — admin cannot remove their own admin role

---

## Pydantic Schema Definitions (for Developer agent)

### TransactionCreate (app/schemas/transaction.py)
```python
class TransactionCreate(BaseModel):
    external_transaction_id: str  # max_length=255
    amount: Decimal               # gt=0, max_digits=18, decimal_places=2
    currency: str                 # length=3, uppercase
    card_last4: str               # pattern=r'^\d{4}$'
    card_bin: str                 # pattern=r'^\d{6,8}$'
    cardholder_name: str          # max_length=255
    merchant_category_code: str   # pattern=r'^\d{4}$'
    merchant_name: str            # max_length=255
    ip_address: str               # validated as IP
    device_fingerprint: str       # max_length=255
    country_code: str             # length=2, uppercase
    city: str | None = None       # max_length=100
    latitude: float | None = None # ge=-90, le=90
    longitude: float | None = None # ge=-180, le=180
```

### RuleResult (app/services/rule_engine.py — internal dataclass)
```python
@dataclass
class RuleResult:
    result: Literal['PASS', 'FLAG', 'BLOCK']
    reasons: list[str]
```

### BehavioralResult (app/services/behavioral_profiler.py — internal dataclass)
```python
@dataclass
class BehavioralResult:
    behavioral_score: float   # 0.0–1.0
    anomalies: list[str]
```

### AIResult (app/services/ai_scorer.py — internal dataclass)
```python
@dataclass
class AIResult:
    risk_score: int                                    # 0–100
    risk_level: Literal['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']
    explanation: str
    recommended_action: Literal['APPROVE', 'FLAG', 'REVIEW', 'BLOCK']
    skipped: bool = False
```

### FraudDecisionResult (app/services/fraud_engine.py — internal dataclass)
```python
@dataclass
class FraudDecisionResult:
    final_decision: Literal['APPROVE', 'FLAG', 'REVIEW', 'BLOCK']
    recommended_action: str
    processing_ms: int
    rule_result: RuleResult
    behavioral_result: BehavioralResult
    ai_result: AIResult | None
```

---

## Blacklist Management (Redis direct — no REST endpoint)

The Developer agent must implement these as service methods called from admin endpoints or CLI tooling, not exposed as REST routes in v1:

- `BlacklistService.add_card(card_last4: str)` — SADD sentinelpay:blacklist:cards
- `BlacklistService.remove_card(card_last4: str)` — SREM
- `BlacklistService.add_ip(ip: str)` — SADD sentinelpay:blacklist:ips
- `BlacklistService.remove_ip(ip: str)` — SREM
- `BlacklistService.add_device(fingerprint: str)` — SADD sentinelpay:blacklist:devices
- `BlacklistService.remove_device(fingerprint: str)` — SREM

These methods should live in `app/services/rule_engine.py`.

---

## Health Check

### GET /health
**Auth:** None (public)

**Response 200:**
```json
{
  "status": "ok",
  "version": "1.0.0",
  "database": "ok | error",
  "redis": "ok | error"
}
```

If either dependency is unhealthy, return `503` with `status: "degraded"`.
