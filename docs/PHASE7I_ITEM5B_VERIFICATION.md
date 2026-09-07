# Item #5B — Coordination Proposal PostgreSQL Persistence: Verification Evidence Report

**Date:** 2026-09-07
**Status:** VERIFIED — DB-backed persistence, round-trip, idempotency, dual-backend regression
**Scope:** Verification ONLY (test hygiene, migration rerun, dual-backend regression, evidence). No frontend UI, no new features, no AWS work, nothing committed.

---

## 1. Objective

Close Item 5B by proving, with repository-identity evidence, that:

1. `tests/test_org_context.py` no longer forces `RELIEFOS_MEMORY=1` and is DB-safe.
2. The legacy JSON → PostgreSQL proposal migration round-trips all important fields and is idempotent.
3. The complete backend regression passes with an explicitly-selected InMemoryRepository AND with real PostgreSQL (localhost:5433), with repository identity proven per run.
4. No new failures; the previously-known failures are accounted for.
5. No temporary/test data remains; the legacy JSON is not consulted or recreated at runtime.

---

## 2. Files Changed (this verification step)

| File | Change |
|------|--------|
| `tests/test_org_context.py` | Removed `os.environ["RELIEFOS_MEMORY"] = "1"` import-time forcing. All test orgs are now unique per run (`org_ctx_alpha/beta/evil_<run-tag>`, `need_ctx_<run-tag>`) so they can never collide with production `org_alpha`/`org_beta`. Added autouse cleanup fixtures: file-backed private workspace dirs (`data/orgs/<org_id>/`) removed before AND after each test; in PostgreSQL mode the run's shared-network rows (organizations, resource_offers, needs, coordination_proposals) are deleted from the DB with the run's unique ids. Cookieless default-org offers are tracked by server id and purged. Authorization semantics untouched — cleanup is data-layer only. |
| `tests/test_ai_coordinator.py`, `tests/test_phase7b.py`, `tests/test_phase7d.py` | Removed import-time `RELIEFOS_MEMORY=1` forcing; `fresh_repo` fixtures now call `set_repository(InMemoryRepository())` explicitly (same pattern as `test_phase3`/`test_phase4`). |
| `tests/test_override_routing.py`, `tests/test_step1_multidistrict.py` | Removed import-time `RELIEFOS_MEMORY=1` forcing (fixtures already explicitly set InMemoryRepository). |
| `tests/test_network_ngo_coordination.py` | **Critical fix:** DB cleanup deleted ALL proposals by `organization_id IN ("org_test","org_1")` — which wiped the entire migrated legacy `org_1` batch during the first PostgreSQL regression run. Cleanup now snapshots pre-existing proposal ids per test and deletes only ids created during the test. |
| `tests/conftest.py` | Added repository-identity recording: a `pytest_runtest_call` hook counts which backend was actually in use per test; written to `.repo_identity.json` at session finish. |

Not changed: `agent/api.py`, coordination modules, repositories, schema, org-context seam, any frontend file. No new features.

---

## 3. Test Hygiene Fix (RELIEFOS_MEMORY poisoning)

**Finding (Item 5B-relevant):** five test modules set `os.environ["RELIEFOS_MEMORY"] = "1"` at IMPORT time. Pytest imports every module before running any test, so in a `DATABASE_URL` run the whole process was silently downgraded to InMemoryRepository. Consequence: the earlier documented "PostgreSQL run" (576 passed / 3 failed) was actually a **100% memory-backed run — a false positive**. The strict conftest identity assertion (added in Phase C/D) exposed this: 625 setup errors in the first genuine DB attempt.

**Fix:** import-time env forcing removed everywhere in `tests/`; memory-specific modules now select InMemoryRepository explicitly via `set_repository()` (provable, module-scoped), and the conftest assertion guarantees every remaining test runs on the ambient backend (`PostgresRepository` when `DATABASE_URL` is set).

---

## 4. Migration Rerun (JSON → PostgreSQL)

Command: `DATABASE_URL=postgresql://reliefos:reliefos@localhost:5433/reliefos python -m agent.data.migrate_proposals`

| Aspect | Result |
|--------|--------|
| Source | `agent/data/coordination_proposals.json` — 275 records (PROPOSED 50, PENDING_ORG_REVIEW 25, DECLINED 25, ORG_RECOMMENDED 100, PUBLISHED 75) |
| Run 1 | **275 imported, 0 failed, 0 skipped** (table had been emptied by the test-cleanup bug, see §2) |
| Run 2 (idempotency) | **0 imported, 275 already present** — re-run duplicates nothing |
| Validation | ids unique, statuses valid, `created_at` parseable, `organization_id` present — all 275 records passed |

Note: an earlier migration attempt (before the test-cleanup fix) produced "275 imported + 1 pre-existing = 276 total"; the extra row (`prop_56b9a3db`/`org_dbg2`) was leftover debug test data and was deleted as part of §9 cleanup.

---

## 5. Round-Trip Preservation

Temporary verification script (run once, then deleted): every legacy JSON record compared field-by-field against its PostgreSQL row.

| Check | Result |
|-------|--------|
| Records compared | 275 / 275 |
| Fields compared | id, need_id, organization_id, organization_name, proposal_type, summary, public_evidence, network_findings, constraints, uncertainty, recommended_action, status, created_at, updated_at, approved_by, published_offer_id, operation_id, org_evaluation, private_factors |
| Timestamp comparisons | 550 (created_at + updated_at × 275), parsed-comparison, all equal |
| Missing rows | 0 |
| Field mismatches | **0** |
| `roundtrip_ok` | **true** |

`org_evaluation` and `private_factors` (JSONB private payloads) round-trip exactly.

---

## 6. Full Regression — Run 1: Explicit InMemoryRepository

Command: `RELIEFOS_MEMORY=1 python -m pytest tests/ -q -p no:cacheprovider`

| Metric | Result |
|--------|--------|
| Passed | **615** |
| Failed | **0** |
| Skipped | 13 (DB-specific tests that legitimately require `DATABASE_URL`) |
| Repository identity | `.repo_identity.json`: `{"mode": "memory", "counts_by_backend": {"InMemoryRepository": 615}}` — **100% of executed tests proven InMemoryRepository** |
| Duration | ~3m20s |

---

## 7. Full Regression — Run 2: Real PostgreSQL (localhost:5433)

Command: `DATABASE_URL=postgresql://reliefos:reliefos@localhost:5433/reliefos python -m pytest tests/ -q -p no:cacheprovider`
(Database: Docker container `reliefos-postgis` (postgis/postgis:16-3.4), port 5433→5432, started for this run.)

| Metric | Result |
|--------|--------|
| Passed | **628** (615 + the 13 tests that skip without `DATABASE_URL`) |
| Failed | **0** |
| Skipped | 0 |
| Repository identity | `.repo_identity.json`: `{"mode": "postgres", "counts_by_backend": {"PostgresRepository": 383, "InMemoryRepository": 244, "none": 1}}` |
| Duration | ~3m52s |

**Identity interpretation (no false positives possible):**
- **383 tests** executed on `PostgresRepository` — enforced by the conftest assertion (`assert type(repo).__name__ == "PostgresRepository"`); any downgrade aborts the test at setup.
- **244 tests** are pure in-memory unit tests in modules that explicitly call `set_repository(InMemoryRepository())` (`test_phase3`, `test_phase4`, `test_export_district`, `test_override_routing`, `test_step1_multidistrict`, `test_ai_coordinator`, `test_phase7b`, `test_phase7d`). Their backend is a deliberate, code-visible selection, not an accident.
- **1 "none"** = the restart-persistence test that deliberately calls `reset_repository()` mid-test to prove durability via a fresh subprocess.
- Post-run integrity: the migrated 275 proposals were still present after the full PostgreSQL run (cleanup bug fixed, §2).

---

## 8. Known Failures / Previously-Known Failures

| Item | Status |
|------|--------|
| 3 known planner failures (`test_planner.py::TestPlannerIntegration::{test_cross_district_real_db, test_allocation_real_db, test_general_query_real_db}`) | **No longer failing.** They failed historically with psycopg2 `OperationalError` because the dev database was DOWN (environmental, documented in `docs/PHASE7I_COORDINATION_PRIVACY_AUDIT.md` §8). With PostgreSQL running, `tests/test_planner.py` passes **17/17** in the PostgreSQL run. |
| New failures introduced by this step | **None.** Both full runs finished with 0 failures. |

The requirement "the only remaining failures are the three already-known planner failures" is satisfied in the strongest sense: there are **zero failures**, and the three known ones are explained (DB-down) and now pass.

---

## 9. Cleanup

| Item | Result |
|------|--------|
| Temporary tools | `tools/_tmp_roundtrip_check.py` deleted |
| `.repo_identity.json` | regenerated per run, deleted after evidence capture |
| File-backed test orgs | `data/orgs/` contains no `org_ctx_*` / `org_priv_*` directories |
| DB test residue | `org_dbg2` debug row + its proposal deleted; all test fixtures purge their own rows (unique ids / id-snapshot diffing) |
| Production org files | `data/orgs/org_alpha/*`, `data/orgs/org_beta/*`, `data/community_reports.json` restored to committed state (prior test runs had appended `tag*`-named test items) |
| Legacy JSON | `agent/data/coordination_proposals.json` retained ONLY as migration source/history — see §10 |

---

## 10. JSON-Runtime-Independence

- No runtime module (outside `agent/data/migrate_proposals.py`, the migration tool itself) references `coordination_proposals.json` — verified by repo-wide grep. The only mentions are comments stating it is "no longer read or written".
- Regression test `tests/test_proposal_persistence.py::test_runtime_works_without_legacy_json_file` renames the file away and proves the full API flow works and the file is NOT recreated (no dual-write).
- The domain layer (`agent/coordination/proposal.py`) has no JSON load/save helpers and delegates entirely to the repository singleton.

---

## 11. Privacy Result

The Item 5 Step 1 privacy boundary was re-proven against PostgreSQL in the full DB run: all 16 adversarial tests in `tests/test_coordination_privacy.py` passed on the real database (they are part of the 383 Postgres-proven tests), plus the 17 org-context seam tests (`test_org_context.py`) in both modes. No private keys (`private_factors`, `org_evaluation`, `team_assessment`, `mission_assessment`) and no cross-org secrets in any HTTP response.

---

## 12. Remaining Gaps / Limitations

1. **244 unit tests are deliberately memory-only** — they are repository-behavior/lifecycle unit tests that assume clean in-memory state with fixed ids. The 383 Postgres-proven tests cover the API surface, persistence, privacy, org-context, planner, and DB-specific behaviors (restart persistence, JSONB round-trip, FK enforcement).
2. **Browser-level proposal flow** — still no proposal frontend UI exists (explicitly out of scope; not started).
3. **Notification fan-out** for `coordination_proposed` events still not wired (pre-existing gap, unchanged).
4. **`get_org_view()`** still has no API caller (pre-existing, unchanged).
5. **No authentication** — the identity seam remains context separation, not auth (by design, unchanged).
6. **No AWS work performed.**
7. The dev PostgreSQL runs in a local Docker container started manually (`docker start reliefos-postgis`); no compose/CI wiring changed.

---

## 13. Verdict

**Item 5B is genuinely ready to close.**

- PostgreSQL is the single authoritative persistence source for coordination proposals (round-trip exact, migration idempotent, restart-proven, JSON-independent).
- Both repository backends are verified with per-test identity evidence; the historical silent-downgrade false positive has been eliminated at the root (no import-time env forcing anywhere in `tests/`).
- 0 failures across both full regressions; the historical 3 planner failures were environmental (DB down) and now pass.
- Test suites are DB-safe: nothing writes to production org data, nothing destroys migrated data, everything cleans up after itself.
- No scope creep: no frontend, no features, no AWS, no commits.
