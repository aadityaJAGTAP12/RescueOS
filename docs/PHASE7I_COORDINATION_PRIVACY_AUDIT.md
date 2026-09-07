# Item #5, Step 1 — Coordination Proposal Privacy Boundary Audit + Hardening

**Date:** 2026-09-07
**Status:** COMPLETE — audit + hardening + adversarial regression tests
**Scope:** Privacy boundary ONLY. No DB migration, no proposal UI, no auth, no RBAC, no AWS, no lifecycle redesign.

---

## 1. Files Changed

| File | Change |
|------|--------|
| `agent/api.py` | **Hardening (3 real fixes + 1 blocker fix)** — see §3. Added `import uuid` to two routes that crashed with `NameError`; wrapped all raw-proposal returns in `get_public_view()`; added targeted-org authorization check on evaluate/approve. |
| `tests/test_coordination_privacy.py` | **New** — 16 adversarial tests covering 4 attacks with two real orgs and unmistakable `SECRET_A_*`/`SECRET_B_*` markers. |

No other files changed. The identity seam (`agent/org_context.py`), coordination
modules, agents, and storage were **not** structurally modified.

---

## 2. Privacy Boundary Discovered (actual data flow)

### Proposal lifecycle (Phase A findings)

| Concern | Location | Notes |
|---------|----------|-------|
| Create | `agent/coordination/proposal.py` → `create_proposal()` | JSON file storage: `agent/data/coordination_proposals.json` |
| Storage | `PROPOSALS_FILE` (flat JSON array) | **File-backed, persists across restarts; DB migration deferred by scope** |
| API create | `POST /api/network/coordination/propose` | Takes `need` + `organization_id` (proposal TARGET — public metadata, not a context selector) |
| API read | `GET /api/network/coordination/proposals[/<id>]` | Filterable by `organization_id` (public filter) |
| API transitions | `send-to-org`, `decline` | Status flips |
| NGO evaluate | `POST /api/my-org/agent/evaluate-coordination` | Reads private state via `evaluate_coordination(proposal, org_id)`; stores `org_evaluation` + `private_factors` in the raw proposal |
| NGO approve | `POST /api/my-org/agent/approve-publication` | Converts stored evaluation → public ResourceOffer via `create_public_offer_from_proposal()` |
| Candidate selection | `agent/coordination/candidate_selection.py` → `select_candidates()` | Uses **only** public data: published offers, org registry, public operations |
| NGO evaluation | `agent/coordination/ngo_evaluation.py` → `evaluate_coordination()` | Reads `agent/org_workspace.list_resources/teams/missions(org_id)` — private, by design, for the targeted org only |
| Network Main Agent | `agent/agents/network_main_agent.py` + `network_workers/*` | No imports of `org_workspace` anywhere (verified structurally + by test) |

### Trust-boundary map (Phase B)

**Network side sees (shared/public only):** needs, published resource offers
(`status="OFFERED"`), operations, overrides, field reports, activity events,
proposal public projections. Candidate scoring uses published offer
quantity/type/geography — never private inventory.

**Organization side sees:** everything above PLUS its own private state
(`data/orgs/<org_id>/{resources,teams,missions}.json`) through the
`/api/my-org/*` seam (`resolve_current_org`). The org's own evaluation reads
its private store server-side; only the public projection
(`decision`, `public_summary`, `constraints`, `matching_available` count)
crosses back.

**Data classification:**
- shared/public: needs, operations, activity, overrides, reports
- published org offers: offer id/type/quantity/unit/geo/status
- proposal metadata: id, need_id, organization_id/name (target), type, summary, status, timestamps
- private org state: inventory, teams, missions, commitments, internal factors — **never** in any HTTP response

---

## 3. Vulnerabilities Found

**No demonstrated privacy bypass of the Network↔NGO data boundary was found** —
the projection design (`get_public_view`, `extract_public_fields`) was already
correct. What the audit DID find:

### V1 (Critical, pre-existing): Network routes returned RAW proposals
- **Attack:** `POST /api/network/coordination/proposals/<id>/send-to-org` and
  `/decline` returned the raw proposal dict. After an NGO evaluated, the raw
  dict carries `org_evaluation` (full private assessment incl. inventory/team/
  mission counts) and `private_factors` — exposed to ANY network caller.
- **Root cause:** `api_send_proposal_to_org` / `api_decline_proposal` returned
  `update_proposal(...)` directly; only the two GET routes projected.
- **Fix:** both routes now return `get_public_view(proposal)`.
- **Also:** `POST .../propose` returned the raw new proposal (pre-evaluation
  it has no private data, but it is a raw-internals surface); now returns
  `get_public_view(proposal)`.
- **Evidence this was live:** the persisted proposals file from earlier test
  runs contained raw evaluations; before the fix, list/get responses leaked
  `private_factors` from stale records (caught by the new tests).

### V2 (Critical, pre-existing): No targeted-org check on evaluate/approve
- **Attack:** Org B's session could call `evaluate-coordination` on a proposal
  **targeting org A** — B's private state would be recorded as A's evaluation,
  or B could `approve-publication` A's proposal (publishing an offer derived
  from A's evaluation under B's org id via the seam).
- **Root cause:** neither route verified `proposal.organization_id == session org`.
- **Fix:** both routes now 404 unless the session-derived org IS the proposal
  target (404, not 403, to avoid confirming existence of other orgs' proposals).
  The org always comes from `resolve_current_org(request)` — client-supplied
  `org_id`/`organization_id` in the body is ignored (seam preserved, no
  duplicated resolution logic).

### V3 (Blocker, pre-existing, not privacy): propose + evaluate routes crashed
- `POST /api/network/coordination/propose` and `POST /api/my-org/agent/
  evaluate-coordination` raised `NameError: name 'uuid' is not defined` →
  **the entire HTTP coordination flow was broken (500) before this audit**.
  The existing test file (`test_network_ngo_coordination.py`) only tested the
  coordination functions directly, never through the API — which is why it
  never caught this.
- **Fix:** added `import uuid` to both route bodies.

### Non-issues verified (no change made)
- `GET /api/offers?organization_id=` and proposals-list filter: read-only
  public filters, not privileged.
- `POST /api/network/coordination/propose` accepting `organization_id`: it is
  the proposal TARGET (public metadata), not a context selector. Targeting is
  legitimate; Attack 4 tests prove no private state flows with it.
- `evaluate_coordination` ignoring client-supplied `private_factors`: correct
  behavior (server derives evaluation from private state), now covered by test.
- Match-confirm flow: already derives org server-side from the offer.

---

## 4. Tests Added

`tests/test_coordination_privacy.py` (16 tests, all passing):

- `TestAttack1NetworkToPrivate::test_propose_response_has_no_private_state`
- `TestAttack1NetworkToPrivate::test_proposal_list_and_detail_are_public_only`
- `TestAttack1NetworkToPrivate::test_network_agent_analysis_has_no_private_state` (also asserts no network module imports `org_workspace`)
- `TestAttack1NetworkToPrivate::test_candidates_use_only_public_offer_data` (published qty 4, not private 13)
- `TestAttack2OrgBToOrgA::test_detail_after_evaluation_still_public_only`
- `TestAttack2OrgBToOrgA::test_send_to_org_returns_public_view_only` ← regression test for V1
- `TestAttack2OrgBToOrgA::test_decline_returns_public_view_only` ← regression test for V1
- `TestAttack2OrgBToOrgA::test_b_cannot_evaluate_proposal_targeting_a` ← regression test for V2
- `TestAttack2OrgBToOrgA::test_b_cannot_approve_publication_of_a_proposal` ← regression test for V2
- `TestAttack2OrgBToOrgA::test_legacy_arbitrary_org_routes_still_dead`
- `TestAttack2OrgBToOrgA::test_proposal_ids_cannot_cross_to_private_reads`
- `TestAttack3MaliciousBodyOrgId::test_evaluate_uses_session_org_not_body_org` ← regression test for V2 + seam
- `TestAttack3MaliciousBodyOrgId::test_evaluate_response_never_leaks_other_org_private_state`
- `TestAttack4ProposalTargeting::test_targeting_a_exposes_only_public_offer_capability`
- `TestAttack4ProposalTargeting::test_a_evaluating_own_proposal_keeps_secrets_server_side`
- `TestAttack4ProposalTargeting::test_published_still_visible_on_network_after_full_lifecycle`

Every assertion inspects the **full serialized JSON** of HTTP responses
(Phase D), checking for all six secret markers plus the private-only keys
`private_factors`, `org_evaluation`, `team_assessment`, `mission_assessment`.

---

## 5. Tests Executed

| Command | Result |
|---------|--------|
| `RELIEFOS_MEMORY=1 python -m pytest tests/test_coordination_privacy.py -q -p no:cacheprovider` | **16 passed** |
| `RELIEFOS_MEMORY=1 python -m pytest tests/test_network_ngo_coordination.py tests/test_network_agent.py tests/test_org_context.py -q -p no:cacheprovider` | **45 passed** |
| `RELIEFOS_MEMORY=1 python -m pytest tests/ -q -p no:cacheprovider` | **576 passed, 34 skipped, 3 failed** (failures = pre-existing planner/DB, see §8) |
| `DATABASE_URL=postgresql://reliefos:reliefos@localhost:5433/reliefos python -m pytest tests/ -q -p no:cacheprovider` | **576 passed, 34 skipped, 3 failed** (same 3) |

Passed: 576. Failed: 3 (pre-existing, reproduced on clean baseline). Skipped: 34.

---

## 6. Real DB Verification

Yes — the full suite was run **twice**, once with `RELIEFOS_MEMORY=1` (in-memory)
and once with the real PostgreSQL dev database
(`DATABASE_URL=postgresql://reliefos:reliefos@localhost:5433/reliefos`). Both
runs: identical results (576 passed / same 3 pre-existing failures). The dev DB
was **not** reset or destructively modified; coordination-proposal storage
remains file-backed (DB persistence is explicitly the NEXT step, per scope).

---

## 7. Adversarial Results

| Attack | Result |
|--------|--------|
| **A → B private access** (A's session reading B's private state via proposals) | **Denied.** Symmetric to B→A tests; private stores are per-org file paths keyed by the seam-derived org. |
| **B → A private access** (proposal IDs of A, org ids in body/query, legacy routes) | **Denied.** B enumerating A's proposal gets public projection only; B evaluating/approving A's proposal → 404, A's stored evaluation untouched; legacy `/api/orgs/<org>/...` → 404/405. |
| **Malicious client `org_id`** (`{"org_id": "org_priv_a"}` in body under B's session) | **Denied.** Evaluation recorded under `org_priv_b` (session org), reading B's private store (2 resources), never A's (3 resources). Seam wins. |
| **Network → NGO private state** (propose/list/get/send/decline + network agent analysis) | **Denied.** All network responses carry zero secret markers and zero private keys; network agent/workers structurally cannot import `org_workspace`. |
| **Legitimate cross-org targeting** (B targets A) | **Works correctly.** A's identity, published offer type/quantity (4 public, not 13 private), geography, and proposal status flow; A's inventory/team/mission/commitment names never appear. A evaluating its own proposal sees only its public projection; approved publication creates a visible public offer for A. |

---

## 8. Existing Failures

The 3 failures are `tests/test_planner.py::TestPlannerIntegration::{test_cross_district_real_db, test_allocation_real_db, test_general_query_real_db}`.

**Verified pre-existing, not caused by this change:** during the Item #3 seam
work, all changes were stashed and these exact 3 tests failed identically on
the clean tree (psycopg2 `OperationalError` — environmental: planner
integration tests require DB data/tables the current dev DB doesn't provide).
They fail identically in both memory and DB runs here. Not related to
coordination proposals or the privacy boundary.

---

## 9. Scope Confirmation

This step did **NOT**:
- ❌ migrate proposal storage to DB (still `agent/data/coordination_proposals.json`)
- ❌ build proposal frontend UI (frontend has no proposal surface; only activity-event icons)
- ❌ introduce authentication
- ❌ introduce speculative RBAC (the targeted-org check is a single boundary
  condition on two routes, not an authorization framework)
- ❌ perform AWS work
- ❌ refactor unrelated systems (seam untouched; coordination modules untouched
  except where the fix required it)

---

## 10. Remaining Gaps (for the rest of Item #5)

**Implemented + verified end-to-end in this step:**
- Network↔NGO proposal privacy boundary (all 4 attacks, API-level, serialized JSON)
- Targeted-org authorization on evaluate/approve
- Org-context seam integrity under adversarial input

**Implemented but NOT yet verified end-to-end:**
- Browser-level flow (no proposal UI exists — nothing to verify in a browser
  until the UI step)

**Not implemented (next steps of Item #5):**
1. **DB persistence for proposals** — currently file-backed; the audit
   *demonstrated* the operational risk (stale raw records leaking through
   list endpoints before projection hardening). Migration must preserve the
   public-view projection discipline.
2. **Proposal frontend UI** (network proposal list/detail, org evaluation
   flow) — must consume ONLY the public projections tested here.
3. **Proposal lifecycle completion** — expire/timeout semantics, notification
   wiring (`coordination_proposed` events exist but no notification fan-out).
4. **Housekeeping:** `get_org_view()` has no API caller (tested only directly);
   either wire it into an org-facing proposal endpoint or remove it.
   `tools/timed_api_diag.py` still hardcodes `org_demo` (diagnostic-only,
   documented in `RELIEFOS_CURRENT_STATE.md`).

**Do not treat Item #5 as complete.** This step establishes the privacy
boundary evidence only.
