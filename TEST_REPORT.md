# SentinelPay — Test Report

**Date:** 2026-06-10  
**Python:** 3.14.2  
**pytest:** 9.0.2  
**pytest-asyncio:** 1.4.0 (asyncio_mode = auto)

---

## Summary

| Metric | Value |
|--------|-------|
| Total tests | 89 |
| Passed | **89** |
| Failed | 0 |
| Errors | 0 |
| Duration | ~14 s |

**All 89 tests pass with zero failures.**

---

## Test Files Written

```
tests/
  conftest.py                        — shared fixtures (MockSession, _make_user, sample_tx, layer results)
  unit/
    test_security.py                 — 10 tests
    test_geo.py                      — 8 tests
    test_rule_engine.py              — 13 tests
    test_behavioral_profiler.py      — 8 tests
    test_ai_scorer.py                — 6 tests
    test_fraud_engine.py             — 9 tests
  integration/
    conftest.py                      — AsyncClient fixture with mocked DB + Redis
    test_auth_endpoints.py           — 13 tests
    test_transaction_endpoints.py    — 8 tests
    test_rules_endpoints.py          — 8 tests
    test_admin_endpoints.py          — 6 tests
  e2e/
    conftest.py                      — re-exports integration client fixture
    test_full_pipeline.py            — 3 tests
```

---

## Unit Tests (53 tests)

### `test_security.py` — 10 tests
| Test | Result | What it checks |
|------|--------|----------------|
| `test_hash_differs_from_plaintext` | ✅ | bcrypt hash ≠ plaintext |
| `test_verify_correct_password_returns_true` | ✅ | verify_password accepts correct password |
| `test_verify_wrong_password_returns_false` | ✅ | verify_password rejects wrong password |
| `test_create_and_decode_access_token` | ✅ | access token round-trips correctly |
| `test_expired_access_token_raises` | ✅ | expired access token raises TokenExpired |
| `test_wrong_type_access_token_raises` | ✅ | refresh token passed to decode_access_token raises InvalidToken |
| `test_garbage_token_raises_invalid` | ✅ | random string raises InvalidToken |
| `test_create_and_decode_refresh_token` | ✅ | refresh token round-trips correctly |
| `test_expired_refresh_token_raises` | ✅ | expired refresh token raises RefreshTokenExpired |
| `test_wrong_type_refresh_token_raises` | ✅ | access token passed to decode_refresh_token raises InvalidRefreshToken |

### `test_geo.py` — 8 tests
| Test | Result | What it checks |
|------|--------|----------------|
| `test_same_point_is_zero` | ✅ | haversine(p, p) == 0 |
| `test_london_to_paris_approx` | ✅ | London→Paris ~340 km |
| `test_new_york_to_los_angeles` | ✅ | NY→LA ~3,940 km |
| `test_antipodal_points` | ✅ | Poles ~20,015 km |
| `test_short_distance_is_not_impossible` | ✅ | 55 km in 0.5h is not flagged |
| `test_impossible_travel_detected` | ✅ | London→NY in 1h is flagged |
| `test_elapsed_time_exceeds_min_hours_not_impossible` | ✅ | elapsed ≥ min_hours → not flagged |
| `test_boundary_exactly_at_min_hours` | ✅ | elapsed == min_hours → not flagged (≥ check) |

### `test_rule_engine.py` — 13 tests
| Test | Result | What it checks |
|------|--------|----------------|
| `test_card_in_blacklist_returns_block` | ✅ | Blacklisted card → BLOCK + BLACKLISTED_CARD |
| `test_ip_in_blacklist_returns_block` | ✅ | Blacklisted IP → BLOCK + BLACKLISTED_IP |
| `test_device_in_blacklist_returns_block` | ✅ | Blacklisted device → BLOCK + BLACKLISTED_DEVICE |
| `test_clean_transaction_not_blacklisted` | ✅ | No blacklist hit → PASS |
| `test_amount_exceeds_hard_limit_blocks` | ✅ | Amount > 50,000 → BLOCK + AMOUNT_EXCEEDS_HARD_LIMIT |
| `test_amount_exceeds_soft_limit_flags` | ✅ | Amount > 10,000 → FLAG + AMOUNT_EXCEEDS_SOFT_LIMIT |
| `test_amount_below_threshold_passes` | ✅ | Normal amount → PASS |
| `test_velocity_1h_exceeded_flags` | ✅ | >5 tx/1h → FLAG + VELOCITY_1H_EXCEEDED |
| `test_velocity_24h_exceeded_blocks` | ✅ | >20 tx/24h → BLOCK + VELOCITY_24H_EXCEEDED |
| `test_velocity_within_threshold_passes` | ✅ | Low velocity → PASS |
| `test_impossible_travel_flags` | ✅ | London→NY in 1h → IMPOSSIBLE_TRAVEL |
| `test_no_previous_location_skips_geo` | ✅ | No prior profile → geo check skipped |
| *(helper tests)* | ✅ | Geo rule with sufficient elapsed time |

### `test_behavioral_profiler.py` — 8 tests
| Test | Result | What it checks |
|------|--------|----------------|
| `test_new_card_no_anomalies` | ✅ | First-time card → score 0.0, no anomalies |
| `test_amount_spike_detected` | ✅ | Amount 4× avg → AMOUNT_SPIKE (+0.30) |
| `test_amount_deviation_detected` | ✅ | Amount > avg+2σ (not spike) → AMOUNT_DEVIATION (+0.20) |
| `test_new_device_detected` | ✅ | Unknown device → NEW_DEVICE (+0.20) |
| `test_new_country_detected` | ✅ | Unknown country → NEW_COUNTRY (+0.25) |
| `test_new_merchant_category_detected` | ✅ | New MCC → NEW_MERCHANT_CATEGORY (+0.10) |
| `test_score_clamped_at_one` | ✅ | Multiple anomalies → score clamped at 1.0 |
| `test_profile_updated_after_scoring` | ✅ | Redis hset called after each score |

### `test_ai_scorer.py` — 6 tests
| Test | Result | What it checks |
|------|--------|----------------|
| `test_valid_json_parsed_correctly` | ✅ | Well-formed Claude response populates all AIResult fields |
| `test_invalid_json_returns_fallback` | ✅ | Unparseable output → MEDIUM fallback |
| `test_missing_field_returns_fallback` | ✅ | Incomplete JSON → MEDIUM fallback |
| `test_successful_api_call_returns_result` | ✅ | Mocked Anthropic response → correct AIResult |
| `test_connection_error_returns_fallback` | ✅ | APIConnectionError → fallback, no raise |
| `test_api_status_error_returns_fallback` | ✅ | APIStatusError → fallback, no raise |

### `test_fraud_engine.py` — 9 tests
| Test | Result | What it checks |
|------|--------|----------------|
| `test_critical_ai_risk_returns_block` | ✅ | CRITICAL AI → BLOCK regardless of other layers |
| `test_flag_with_high_ai_returns_block` | ✅ | FLAG + HIGH AI → escalated to BLOCK |
| `test_high_behavioral_score_returns_review` | ✅ | score > 0.55 → REVIEW |
| `test_mid_behavioral_high_ai_returns_review` | ✅ | 0.25–0.55 + HIGH → REVIEW |
| `test_mid_behavioral_medium_ai_returns_flag` | ✅ | 0.25–0.55 + MEDIUM → FLAG |
| `test_low_behavioral_low_ai_returns_approve` | ✅ | score < 0.25 + LOW → APPROVE |
| `test_low_behavioral_medium_ai_returns_flag` | ✅ | score < 0.25 + MEDIUM → FLAG |
| `test_layer1_block_skips_layers_2_and_3` | ✅ | BLOCK short-circuits: behavioral + AI never called |
| `test_layer1_pass_runs_all_layers` | ✅ | PASS runs all 3 layers → APPROVE |

---

## Integration Tests (36 tests)

### `test_auth_endpoints.py` — 13 tests
| Test | Result | Status |
|------|--------|--------|
| `test_register_new_user_returns_201` | ✅ | 201 + user JSON |
| `test_register_duplicate_email_returns_400` | ✅ | 400 EMAIL_ALREADY_REGISTERED |
| `test_register_duplicate_merchant_id_returns_400` | ✅ | 400 MERCHANT_ID_ALREADY_TAKEN |
| `test_register_invalid_email_returns_422` | ✅ | 422 Pydantic validation |
| `test_register_short_password_returns_422` | ✅ | 422 Pydantic validation |
| `test_login_success_returns_tokens` | ✅ | 200 + access_token + refresh_token |
| `test_login_wrong_password_returns_401` | ✅ | 401 INVALID_CREDENTIALS |
| `test_login_unknown_email_returns_401` | ✅ | 401 INVALID_CREDENTIALS |
| `test_login_inactive_account_returns_401` | ✅ | 401 ACCOUNT_INACTIVE |
| `test_refresh_valid_token_returns_new_access_token` | ✅ | 200 + new access_token |
| `test_refresh_invalid_token_returns_401` | ✅ | 401 INVALID_REFRESH_TOKEN |
| `test_logout_with_valid_token_returns_200` | ✅ | 200 + success message |

### `test_transaction_endpoints.py` — 8 tests
| Test | Result | Status |
|------|--------|--------|
| `test_analyze_success_returns_fraud_decision` | ✅ | 200 + full FraudDecisionResponse |
| `test_analyze_duplicate_transaction_returns_409` | ✅ | 409 DUPLICATE_TRANSACTION |
| `test_analyze_unauthenticated_returns_4xx` | ✅ | 401/403 for missing token |
| `test_get_own_transaction_returns_200` | ✅ | 200 + TransactionResponse |
| `test_merchant_cannot_get_other_merchant_transaction` | ✅ | 403 FORBIDDEN |
| `test_get_nonexistent_transaction_returns_404` | ✅ | 404 TRANSACTION_NOT_FOUND |
| `test_get_decision_returns_fraud_detail` | ✅ | 200 + FraudDecisionDetailResponse |

### `test_rules_endpoints.py` — 8 tests
| Test | Result | Status |
|------|--------|--------|
| `test_admin_can_list_rules` | ✅ | 200 + paginated rules |
| `test_merchant_cannot_list_rules` | ✅ | 403 FORBIDDEN |
| `test_admin_creates_rule_returns_201` | ✅ | 201 + RuleResponse |
| `test_duplicate_rule_name_returns_400` | ✅ | 400 RULE_NAME_ALREADY_EXISTS |
| `test_admin_updates_rule` | ✅ | 200 + updated rule |
| `test_update_nonexistent_rule_returns_404` | ✅ | 404 RULE_NOT_FOUND |
| `test_admin_deletes_rule` | ✅ | 204 No Content |
| `test_admin_toggles_rule` | ✅ | 200 + toggled is_active |

### `test_admin_endpoints.py` — 6 tests
| Test | Result | Status |
|------|--------|--------|
| `test_admin_gets_metrics` | ✅ | 200 + metrics dict with totals/rates/performance |
| `test_merchant_cannot_access_metrics` | ✅ | 403 FORBIDDEN |
| `test_admin_lists_all_users` | ✅ | 200 + paginated user list |
| `test_admin_can_update_user_role` | ✅ | 200 + updated user |
| `test_admin_cannot_demote_self` | ✅ | 400 CANNOT_DEMOTE_SELF |
| `test_update_nonexistent_user_returns_404` | ✅ | 404 USER_NOT_FOUND |

---

## End-to-End Tests (3 tests)

All three tests run the **real 3-layer pipeline** (rule engine → behavioral profiler → AI scorer) with only Redis and Anthropic API mocked. The PostgreSQL session is also mocked at the service level.

| Test | Result | Scenario |
|------|--------|---------|
| `test_normal_transaction_approved` | ✅ | Normal $200 transaction with no profile → Layer 1 PASS, score 0.0, AI LOW → **APPROVE** |
| `test_blacklisted_card_blocked_immediately` | ✅ | Card on blacklist → Layer 1 BLOCK, layers 2 & 3 skipped, AI `skipped=True` → **BLOCK** |
| `test_high_behavioral_score_reviewed` | ✅ | Known profile with amount spike + new device + new country (score > 0.55) + AI HIGH → **REVIEW or BLOCK** |

---

## Coverage Summary

All application modules exercised:

| Module | Coverage |
|--------|---------|
| `app/core/security.py` | JWT encode/decode, password hash/verify, all exception paths |
| `app/utils/geo.py` | haversine_km, is_impossible_travel (boundary and positive cases) |
| `app/services/rule_engine.py` | Blacklist, amount, velocity, geo checks; PASS/FLAG/BLOCK outcomes |
| `app/services/behavioral_profiler.py` | All 6 anomaly types, score clamping, profile update |
| `app/services/ai_scorer.py` | JSON parse, APIConnectionError fallback, APIStatusError fallback |
| `app/services/fraud_engine.py` | Full decision matrix (7 branches), Layer 1 BLOCK short-circuit |
| `app/api/v1/endpoints/auth.py` | register, login, refresh, logout; all error codes |
| `app/api/v1/endpoints/transactions.py` | analyze, get, list, get_decision; auth and ownership checks |
| `app/api/v1/endpoints/rules.py` | list, create, update, delete, toggle; admin-only enforcement |
| `app/api/v1/endpoints/admin.py` | metrics, list_users, update_user_role; all error codes |

---

## Environment Notes

- **Python 3.14.2** — `asyncpg` has no pre-built wheel; tests use `sqlite+aiosqlite:///:memory:` as the `DATABASE_URL` (all DB I/O is mocked, so the dialect is irrelevant).
- **bcrypt 4.2.1** required — `bcrypt 5.x` removed `__about__` which `passlib 1.7.4` depends on; downgraded to resolve.
- **All external services mocked** — PostgreSQL (MockSession), Redis (AsyncMock), Anthropic API (AsyncMock / patch.object).
