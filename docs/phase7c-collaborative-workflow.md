# ReliefOS Phase 7C — Collaborative Response Workflow

## Overview

Phase 7C connects the existing collaboration backend (Needs → Offers → Matching → Operations → Resolution) to the Phase 7B operational console. The GitHub-like collaboration model is now a first-class interaction inside the map-first workspace.

## Architecture

```
Need Discovery → Need Dossier → Find Resources → Match Proposal → Confirm → Operation → Resolution
     ↑               ↑              ↑               ↑              ↑          ↑           ↑
   Map Click    ContextPanel    API/Matching    MatchCard      Human     Operation   Status
                 (NeedDetail)   (/api/matches)  (inline)       Confirm   Dossier     Update
                                                        (/api/matches/.../confirm)
```

## What Was Built

### Enhanced Need Dossier (NeedDetail)

**Before Phase 7C:**
- Title, status, urgency, location, description
- Requested resources
- Timestamps
- Coordination actions (Find Resources, Join Response, Mark Resolved, Close)
- Resource matches with Confirm button
- Basic activity history

**After Phase 7C:**
- Need ID displayed in subtitle
- Confidence score shown when available
- Reporter info (who reported, reporter type)
- Resource gap display with progress bar (committed/requested)
- Responders section showing participating organizations
- Enhanced activity timeline with GitHub-like dots and timestamps
- Resource matches with compatibility badges, reasons, and capacity info

### Enhanced Operation Dossier (OperationDetail)

**Before Phase 7C:**
- Title, status, type, description
- Location, participants
- Coordination actions (Activate, Pause, Complete, Cancel)
- Basic metadata

**After Phase 7C:**
- Operation ID in subtitle
- Lead organization shown
- Linked Need card (clickable → opens Need dossier)
- Activity timeline with event dots and timestamps
- Cleaner action buttons (removed buggy `||` precedence issue)

### Enhanced Offer Dossier (OfferDetail)

**Before Phase 7C:**
- Resource type, quantity, status
- Location, notes, organization

**After Phase 7C:**
- Offer ID in subtitle
- Quantity/unit displayed as badge
- Published timestamp
- Matching Needs section showing compatible needs in same district

### Need Filtering (LayerRail)

Added urgency and status filter chips:
- **Urgency:** critical, high, medium, low
- **Status:** OPEN, RESPONDING, RESOLVED
- Filters apply to both map markers and data display

### Activity Timeline

Reusable GitHub-like timeline pattern used in both NeedDetail and OperationDetail:
- Vertical timeline with colored dots per event type
- Event color coding: need_created (red), need_resolved (green), operation_created (blue), status_changed (amber), match_confirmed (green)
- Actor and relative timestamp
- Limited to 10 most recent events with "+N more" overflow

## Existing Backend Reused

| Endpoint | Purpose | Used By |
|----------|---------|---------|
| `GET /api/needs` | List needs with filters | MapCanvas, LayerRail |
| `POST /api/needs` | Create need | CreateNeedForm |
| `PATCH /api/needs/<id>` | Update need status | NeedDetail |
| `GET /api/offers` | List offers | MapCanvas |
| `POST /api/offers` | Create offer | CreateOfferForm |
| `GET /api/needs/<id>/matches` | Find matching offers | NeedDetail "Find Resources" |
| `POST /api/matches/<id>/<id>/confirm` | Confirm match → create Operation | NeedDetail "Confirm Collaboration" |
| `GET /api/operations` | List operations | MapCanvas |
| `PATCH /api/operations/<id>` | Update operation status | OperationDetail |
| `GET /api/activity` | Activity events | ActivityBar, NeedDetail, OperationDetail |
| `GET /api/ai-coordinator/analysis` | AI coordinator findings | AIAnalysisPanel |

## Existing Frontend Reused

| Component | File | Status |
|-----------|------|--------|
| NetworkWorkspace | NetworkWorkspace.jsx | Reused |
| MapCanvas | MapCanvas.jsx | Reused (urgency/status filtering already supported) |
| LayerRail | LayerRail.jsx | Enhanced (added filter chips) |
| WorkspaceHeader | WorkspaceHeader.jsx | Reused |
| ActivityBar | ActivityBar.jsx | Reused |
| workspaceContext | workspaceContext.jsx | Reused |
| ContextPanel | ContextPanel.jsx | Enhanced (NeedDetail, OperationDetail, OfferDetail) |

## New/Refactored Components

None created as new files. All improvements were made by enhancing existing components:
- NeedDetail: +resource gap, +responders, +enhanced timeline
- OperationDetail: +linked need, +activity timeline, +lead org
- OfferDetail: +matching needs, +timestamps
- LayerRail: +urgency chips, +status chips

## Need Workflow

1. **Discovery:** Need appears as colored marker on map (color = urgency)
2. **Selection:** Click → opens NeedDetail in context panel
3. **Status:** Badge shows OPEN/RESPONDING/RESOLVED/CLOSED
4. **Gap Display:** Progress bar shows committed vs requested
5. **Responders:** Organizations participating are listed
6. **Find Resources:** Button triggers `/api/needs/<id>/matches`
7. **Match Review:** Candidate offers shown with compatibility, reasons, capacity
8. **Confirm:** Human clicks "Confirm Collaboration" → `/api/matches/.../confirm`
9. **Operation Created:** Backend creates Operation, updates Need to RESPONDING
10. **Navigation:** NeedDetail opens Operation dossier on confirmation
11. **Resolution:** "Mark Resolved" button updates Need status

## Match Workflow

1. **Search:** "Find Resources" calls matching engine
2. **Results:** Candidates shown with compatibility badge (HIGH/MEDIUM/LOW)
3. **Details:** Each candidate shows offer, organization, location, reasons
4. **Capacity:** Requested vs available vs unmet quantity
5. **Action:** "Confirm Collaboration" button (only when need is OPEN)
6. **Idempotent:** Re-confirming same pair returns existing Operation

## Operation Workflow

1. **Creation:** Automatic from match confirmation
2. **Dossier:** Shows ID, status, type, lead org, description
3. **Linked Need:** Clickable card linking back to Need
4. **Participants:** Organizations from operation metadata
5. **Actions:** Activate → Complete, or Cancel
6. **Activity:** Timeline of operation events

## Activity Timeline

- All events come from backend `/api/activity` endpoint
- No fabricated events on frontend
- Event types: need_created, need_resolved, match_confirmed, operation_created, resource_offered, status_changed, field_update
- Each event has: type, actor, detail, timestamp
- Timeline uses colored dots for visual scanning

## AI Coordinator Integration

- AI findings reference specific needs and operations via `review_target`
- "Review Need" / "Review Operation" buttons open relevant dossiers
- AI detects: coordination gaps, duplicate responses, route consequences
- All recommendations are advisory — no automatic actions

## Privacy

- No private NGO inventory exposed
- Organizations shown only through published offers and operations
- `organization_id` from public offer/operation data
- Private state boundary preserved (no internal inventory, staff, or commitments)

## Responsive Behavior

- **Desktop:** Full layout with all panels
- **Tablet:** LayerRail collapses, right panel becomes floating
- **Mobile:** Not yet implemented (later phase)

## Empty States

- Map shows message when no needs/operations visible
- NeedDetail shows "No activity yet" when no events
- Resource matches show "No compatible offers found" when empty
- Filter chips show counts for each urgency/status

## Tests

All existing tests pass:
- `test_ai_coordinator.py`: 147 passed
- `test_planner.py`: 31 passed
- `test_routing.py`: 31 passed
- `test_community_reports.py`: 14 passed
- **Total: 223+ passed, 0 failed**

## Files Changed

| File | Change Type | Description |
|------|-------------|-------------|
| frontend/src/components/workspace/ContextPanel.jsx | Enhanced | NeedDetail +resource gap, +responders, +timeline; OperationDetail +linked need, +activity; OfferDetail +matching needs |
| frontend/src/components/workspace/LayerRail.jsx | Enhanced | +urgency filter chips, +status filter chips |
| docs/phase7c-collaborative-workflow.md | New | This documentation |

## Verification

```
Frontend build: ✅ (582KB JS, 50KB CSS)
Backend tests: ✅ (223+ passed)
DATABASE MODIFIED: NO
DATABASE DATA CHANGED: NO
DOCKER MODIFIED: NO
FLOOD DATA MODIFIED: NO
OSM DATA MODIFIED: NO
```

## What Was NOT Changed

- Database schema
- API endpoints
- Matching engine
- Backend business logic
- Flood/OSM data
- Docker configuration
- Agent/planner architecture
- Data models
