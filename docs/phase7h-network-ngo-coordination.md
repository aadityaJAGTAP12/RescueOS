# Phase 7H — Network ↔ NGO Intelligent Coordination

## Objective

Establish the controlled coordination workflow between the Network Main Agent and NGO Main Agents, enabling:
- Network identifies candidate organizations using public information only
- NGO Main Agent privately evaluates proposals
- Human approves publication of public responses
- Published offers enter the existing collaboration lifecycle

## Architecture

```
Network Main Agent
    ↓
Coordination Proposal
    ↓
Candidate Selection (public info only)
    ↓
NGO Main Agent (private evaluation)
    ↓
Private Recommendation
    ↓
Human Approval
    ↓
Published Resource Offer (existing shared model)
    ↓
Network Main Agent re-evaluation
    ↓
Existing Matching/Confirmation
    ↓
Operation (existing lifecycle)
```

## Modules Created

### `agent/coordination/proposal.py`
- `CoordinationProposal` dataclass
- `ProposalStatus` enum: PROPOSED → PENDING_ORG_REVIEW → ORG_RECOMMENDED → PENDING_HUMAN_APPROVAL → PUBLISHED → CONFIRMED / DECLINED / EXPIRED
- `CoordinationProposalStore` — in-memory persistence (file-backed)
- CRUD operations for proposals

### `agent/coordination/candidate_selection.py`
- `Candidate` dataclass with score
- `select_candidates(need, repo)` — ranks organizations using public offers, ops, geographic proximity
- **Privacy**: Only accesses `list_organizations()`, `list_resource_offers()`, `list_operations()`

### `agent/coordination/ngo_evaluation.py`
- `NGOEvaluation` dataclass with `private_factors` (NEVER published)
- `EvaluationDecision` enum: SUITABLE / POTENTIALLY_SUITABLE / UNSUITABLE / CONFLICT / INSUFFICIENT_INFO
- `evaluate_need_for_org(proposal, private_ctx, shared_ctx)` — analyzes private state

### `agent/coordination/publication.py`
- `prepare_publication(proposal, evaluation)` — maps private→public
- `execute_publication(proposal, evaluation, repo)` — creates Resource Offer
- `PublicationResult` dataclass
- **Privacy**: Filters out `private_factors`, only publishes approved fields

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/network/coordination/propose` | Create coordination proposal |
| GET | `/api/network/coordination/proposals` | List proposals |
| GET | `/api/network/coordination/proposals/<id>` | Get proposal |
| POST | `/api/network/coordination/proposals/<id>/send-to-org` | Send to NGO for evaluation |
| POST | `/api/orgs/<id>/agent/evaluate-coordination` | NGO evaluates proposal |
| POST | `/api/orgs/<id>/agent/approve-publication` | Human approves publication |

## Privacy Boundary

```
PRIVATE (never crosses boundary):
- raw inventory details
- team names and assignments
- mission details
- internal commitments
- private evaluation factors
- agent chain-of-thought

PUBLIC (crosses boundary via human approval):
- published offer (resource type, quantity, availability, service area)
- public organization profile
- public operations
- constraints explicitly approved for publication
```

## Human Approval Points

1. **Coordination proposal** → Network creates, human sends to NGO
2. **Publication approval** → NGO evaluates, human approves what to publish
3. **Collaboration confirmation** → Human confirms match → Operation created

AI may: detect, analyze, rank, recommend, draft, explain
AI may NOT: dispatch, commit, assign, accept, publish, confirm

## LLM Fallback

All coordination logic is deterministic:
- Candidate selection uses public offer type matching + geographic proximity + operational history
- NGO evaluation checks private resource status, team availability, mission conflicts
- Publication maps private→public with field filtering
- No LLM required for any critical path

## Tests

13 new tests in `tests/test_network_ngo_coordination.py`:
- Proposal lifecycle (create, send, decline)
- Privacy boundary (3 tests: public view, org view, API response)
- Human approval (2 tests: rejection without approval, approval status)
- Publication (2 tests: offer creation, constraint preservation)
- Candidate selection (public offers only)
- NGO evaluation (private state access)
- Audit trail (timestamps)

## Verification

- **211 tests passed** (all Phase 7B–7H + existing tests)
- **Frontend build**: 615KB JS, 51KB CSS ✅
- **DATABASE MODIFIED**: NO
- **DOCKER MODIFIED**: NO
- **OSM DATA MODIFIED**: NO
- **SENTINEL-1 DATA MODIFIED**: NO
- **NGO PRIVATE DATA MODIFIED**: NO (only through test fixtures)

## Files Changed

| File | Change |
|------|--------|
| `agent/coordination/__init__.py` | New — coordination package |
| `agent/coordination/proposal.py` | New — CoordinationProposal model |
| `agent/coordination/candidate_selection.py` | New — candidate ranking |
| `agent/coordination/ngo_evaluation.py` | New — private evaluation |
| `agent/coordination/publication.py` | New — publication workflow |
| `agent/api.py` | +6 coordination endpoints |
| `tests/test_network_ngo_coordination.py` | New — 13 tests |
| `docs/phase7h-network-ngo-coordination.md` | New documentation |

## What This Enables

The complete Network ↔ NGO coordination loop now works:

1. Network identifies Need and candidate organizations
2. Human requests NGO evaluation
3. NGO Main Agent evaluates privately
4. Human reviews and approves publication
5. Published offer enters existing collaboration lifecycle
6. Existing matching/confirmation creates Operation
7. Activity trail records full coordination lifecycle
