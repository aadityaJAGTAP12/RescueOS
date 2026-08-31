# RELIEFOS — Phase 7A: Collaborative Response Workspace — Architecture + UX Design

> **Status:** Design Document — Inspection & Architecture Only
> **Date:** 2026-08-30
> **Constraint:** INSPECT → DESIGN → DOCUMENT → STOP. No code changes.

---

## Table of Contents

1. [Product Architecture](#1-product-architecture)
2. [Shared vs Private Boundary](#2-shared-vs-private-boundary)
3. [Network Main Agent Architecture](#3-network-main-agent-architecture)
4. [NGO Main Agent Architecture](#4-ngo-main-agent-architecture)
5. [Worker-Agent Hierarchy](#5-worker-agent-hierarchy)
6. [Shared Operational Object Model](#6-shared-operational-object-model)
7. [Data Visibility Model](#7-data-visibility-model)
8. [UI Information Architecture](#8-ui-information-architecture)
9. [Main Dashboard Wireframe](#9-main-dashboard-wireframe)
10. [Map Interaction Model](#10-map-interaction-model)
11. [Need Workflow](#11-need-workflow)
12. [Resource Offer Workflow](#12-resource-offer-workflow)
13. [Organization Workflow](#13-organization-workflow)
14. [Field Report Workflow](#14-field-report-workflow)
15. [Override Workflow](#15-override-workflow)
16. [Notification Model](#16-notification-model)
17. [AI Coordinator Behavior](#17-ai-coordinator-behavior)
18. [Permission Model](#18-permission-model)
19. [Existing-Code Reuse Analysis](#19-existing-code-reuse-analysis)
20. [Proposed Backend/Schema Changes](#20-proposed-backendschema-changes)
21. [Proposed Frontend Changes](#21-proposed-frontend-changes)
22. [Phase 7 Implementation Sequence](#22-phase-7-implementation-sequence)
23. [What Is Explicitly Deferred](#23-what-is-explicitly-deferred)

---

## 1. Product Architecture

### 1.1 Vision

ReliefOS is a shared operational coordination platform for disaster response. Unlike a chatbot or a static dashboard, the main product is a **Common Operating Picture** — a live, shared view of an emergency that multiple organizations can observe, contribute to, and act on.

### 1.2 Architectural Layers

```
┌─────────────────────────────────────────────────────────┐
│                    RELIEFOS PLATFORM                     │
│                                                         │
│  ┌───────────────────────────────────────────────────┐  │
│  │           SHARED NETWORK LAYER                     │  │
│  │  Common Operating Picture · Map · Needs · Offers  │  │
│  │  Incidents · Operations · Alerts · AI Coordinator │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │  NGO Org A   │  │  NGO Org B   │  │  NGO Org C   │    │
│  │  Workspace   │  │  Workspace   │  │  Workspace   │    │
│  │  (private)   │  │  (private)   │  │  (private)   │    │
│  └─────────────┘  └─────────────┘  └─────────────┘    │
│                                                         │
│  ┌───────────────────────────────────────────────────┐  │
│  │           FOUNDATION LAYER (existing)              │  │
│  │  PostgreSQL+PostGIS · Sentinel-1 · OSM · Flood    │  │
│  │  Exposure · Accessibility · Routing · PDC · Tools │  │
│  │  Planner · Agent Orchestration · Provenance       │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### 1.3 Core Principles

| # | Principle | Implication |
|---|-----------|-------------|
| 1 | The main product is NOT a chatbot | AI supports the workspace, it doesn't replace it |
| 2 | Common Operating Picture | One shared view all participants see |
| 3 | Map is central | Every operational object has a spatial dimension |
| 4 | Needs are collaboration objects | Organizations respond to shared Need records |
| 5 | Resource offers are voluntary | Organizations publish what they can contribute |
| 6 | Field reports update shared state | Community input flows into the common picture |
| 7 | Overrides modify operational map | Local knowledge is tracked alongside system data |
| 8 | AI watches for coordination gaps | Proactive detection of unmet needs and conflicts |
| 9 | Organizations collaborate voluntarily | No organization is forced to participate |
| 10 | AI proposes, humans decide | Advisory recommendations, never autonomous commands |
| 11 | No hardcoded scenarios | District-agnostic, event-agnostic reasoning |
| 12 | Real data, not synthetic | Historical incidents are evidence, not application branches |

---

## 2. Shared vs Private Boundary

### 2.1 The Boundary Model

```
NGO PRIVATE STATE
        │
        ▼
NGO MAIN AGENT
        │
        ▼
PUBLISHED NEEDS / OFFERS / OPERATIONS / UPDATES
        │
        ▼
RELIEFOS NETWORK
```

### 2.2 NGO Private State (Never Shared Automatically)

| Concept | Description |
|---------|-------------|
| Full inventory | Complete list of all resources, supplies, equipment |
| Staff roster | Names, roles, contact info of all team members |
| Internal commitments | Resources already committed to other operations |
| Internal missions | Planned but unpublished response activities |
| Financial state | Budget, funding sources, procurement status |
| Internal field reports | Reports not yet reviewed/verified for sharing |
| Operational plans | Detailed logistics, staging areas, supply chains |

### 2.3 Shared Network State (Published to Network)

| Concept | Description |
|---------|-------------|
| Resource offers | What the org can contribute (e.g., 2 boats, available now) |
| Published capabilities | General services the org provides (medical, transport, shelter) |
| Active public operations | Operations the org wants the network to know about |
| Public contact info | Coordination contact, radio channel, base location |
| Updates on shared needs | Status changes on needs the org is responding to |
| Verified field reports | Community intelligence the org has verified |

### 2.4 Boundary Rules

1. **Private state NEVER automatically becomes public.** The NGO Main Agent mediates.
2. **The network CANNOT directly access NGO internal workers.** It sees only published objects.
3. **NGO Main Agent decides what to publish.** This is a deliberate, auditable action.
4. **Published objects carry provenance.** Every shared item records who published it, when, and from what source.
5. **Organizations can unpublish.** They can withdraw offers or mark operations as private.

---

## 3. Network Main Agent Architecture

### 3.1 Role

The Network Main Agent is the AI backbone of the shared ReliefOS network. It:

- Maintains awareness of the common operating picture
- Monitors for coordination gaps and consequences
- Synthesizes cross-organization intelligence
- Proposes matches between needs and resource offers
- Summarizes situation changes
- **Never controls organizations directly**

### 3.2 Architecture

```
Network Main Agent
    │
    ├── Situation / Flood Worker
    │     Monitors flood snapshots across all districts
    │     Detects new flood events, changing extent
    │     Updates common operating picture
    │
    ├── Logistics Worker
    │     Tracks active operations and resource movement
    │     Detects supply chain disruptions
    │     Monitors road/bridge status changes
    │
    ├── Access / Routing Worker
    │     Evaluates route viability given overrides
    │     Detects when bridge/road closure affects operations
    │     Proposes alternative routes
    │
    ├── Medical Worker
    │     Monitors medical facility availability
    │     Tracks medical needs across organizations
    │     Detects medical resource gaps
    │
    ├── Field Intelligence Worker
    │     Processes incoming field reports
    │     Cross-references with existing intelligence
    │     Flags contradictions or verification needs
    │
    ├── Coordination Worker
    │     Matches needs to resource offers
    │     Detects duplicate responses to same need
    │     Detects high-priority needs with no responders
    │     Generates coordination gap alerts
    │
    └── Evidence Worker
          Maintains provenance and confidence tracking
          Validates data freshness
          Reports data gaps
```

### 3.3 Interaction Model

The Network Main Agent does NOT send commands to NGOs. It:

1. **Observes** shared state changes (new needs, offers, field reports, overrides)
2. **Analyzes** the common operating picture
3. **Surfaces** coordination gaps, recommendations, and alerts in the shared workspace
4. **Proposes** matches and actions — but humans approve
5. **Summarizes** situation changes for coordinators

---

## 4. NGO Main Agent Architecture

### 4.1 Role

Each organization has its own Main Agent that:

- Manages the organization's private operational state
- Mediates between internal workers and the shared network
- Decides what to publish (based on org policies)
- Responds to network-level coordination requests
- Protects private organizational information

### 4.2 Architecture

```
NGO Main Agent
    │
    ├── Inventory Worker
    │     Manages internal resource tracking
    │     Tracks what's available vs committed
    │     Feeds availability data to Main Agent for publishing
    │
    ├── Logistics Worker
    │     Plans internal supply movements
    │     Tracks team deployments
    │     Manages staging areas
    │
    ├── Team Worker
    │     Manages staff assignments
    │     Tracks team availability
    │     Handles shift planning
    │
    ├── Mission Worker
    │     Plans and tracks response missions
    │     Records mission outcomes
    │     Reports completion status
    │
    └── Field Worker
          Processes internal field reports
          Verifies community intelligence
          Prepares reports for potential sharing
```

### 4.3 Publishing Flow

```
Internal State Change
        │
        ▼
NGO Main Agent evaluates:
  - Is this relevant to the shared network?
  - Does the organization want to share this?
  - What level of detail should be shared?
        │
        ▼
Publish (or don't publish)
        │
        ▼
Shared Network sees published object
```

---

## 5. Worker-Agent Hierarchy

### 5.1 Design Rule

Worker agents report through their respective Main Agent. No peer-to-peer worker chaos.

### 5.2 Network Workers → Network Main Agent

| Worker | Reports To | Feeds Into |
|--------|-----------|------------|
| Situation/Flood Worker | Network Main Agent | Common Operating Picture |
| Logistics Worker | Network Main Agent | Operation tracking |
| Access/Routing Worker | Network Main Agent | Route viability alerts |
| Medical Worker | Network Main Agent | Medical gap detection |
| Field Intelligence Worker | Network Main Agent | Intelligence reports |
| Coordination Worker | Network Main Agent | Match proposals, gap alerts |
| Evidence Worker | Network Main Agent | Provenance tracking |

### 5.3 NGO Workers → NGO Main Agent

| Worker | Reports To | Feeds Into |
|--------|-----------|------------|
| Inventory Worker | NGO Main Agent | Resource availability |
| Logistics Worker | NGO Main Agent | Internal operations |
| Team Worker | NGO Main Agent | Staff availability |
| Mission Worker | NGO Main Agent | Mission status |
| Field Worker | NGO Main Agent | Internal intelligence |

### 5.4 Cross-Organization Interaction

```
NGO A Internal State
        │
        ▼
NGO A Main Agent publishes: "Offer: 2 rescue boats, available now"
        │
        ▼
ReliefOS Network receives published offer
        │
        ▼
Network Coordination Worker matches against needs
        │
        ▼
Network Main Agent surfaces match proposal in shared workspace
        │
        ▼
Human coordinator reviews and approves
        │
        ▼
Shared operation created
```

---

## 6. Shared Operational Object Model

### 6.1 Objects That Belong to the Shared Network

#### Need

A shared Need represents a gap in the response — something that requires resources or action.

```python
class Need:
    id: str                    # deterministic, e.g. "need_jorhat_food_20260729"
    type: str                  # "food" | "water" | "medical" | "shelter" | "transport" | "rescue" | "other"
    description: str           # human-readable description
    location: dict             # {lat, lon, location_name, district_id}
    urgency: str               # "critical" | "high" | "medium" | "low"
    status: str                # OPEN | UNDER_REVIEW | RESPONDING | PARTIALLY_RESOLVED | RESOLVED | CLOSED
    requested_resources: list  # [{type, quantity, unit}]
    evidence: dict             # supporting data (flood status, exposure, field reports)
    reporter: str              # who reported this need
    reporter_type: str         # "coordinator" | "field_team" | "community" | "ai_detector"
    created_at: datetime
    updated_at: datetime
    responders: list           # [{org_id, org_name, status, joined_at}]
    remaining_requirement: dict # what's still unmet
    activity_history: list     # [{action, actor, timestamp, detail}]
    provenance: str            # REAL | DERIVED | FIELD_REPORT | COORDINATOR_INPUT
    confidence: float          # 0.0-1.0
    metadata: dict             # flexible extra fields
```

**Status flow:**
```
OPEN → UNDER_REVIEW → RESPONDING → PARTIALLY_RESOLVED → RESOLVED → CLOSED
  │        │               │              │
  └────────┴───────────────┴──────────────┘ (can return to any earlier state)
```

#### Resource Offer

A published offer from an organization to contribute resources.

```python
class ResourceOffer:
    id: str                    # deterministic
    org_id: str                # organization making the offer
    org_name: str              # human-readable org name
    resource_type: str         # "boat" | "medical_team" | "food" | "water" | "shelter" | "vehicle" | "personnel" | "other"
    quantity: int
    unit: str                  # "units" | "people" | "kg" | "liters" | "kits"
    available_from: datetime
    available_until: datetime | None
    location: dict             # {lat, lon, location_name, district_id}
    status: str                # OFFERED | ACCEPTED | DEPLOYED | WITHDRAWN | EXPIRED
    notes: str                 # optional description
    created_at: datetime
    updated_at: datetime
    provenance: str
    metadata: dict
```

#### Incident

An incident is a specific event or occurrence that disrupts normal operations.

```python
class Incident:
    id: str
    type: str                  # "bridge_closure" | "road_blocked" | "facility_damage" | "flood_event" | "other"
    severity: str              # "critical" | "high" | "medium" | "low"
    location: dict             # {lat, lon, location_name, district_id}
    description: str
    affected_operations: list  # [operation_ids impacted]
    status: str                # ACTIVE | MONITORING | RESOLVED | CLOSED
    reported_by: str           # org_id or "network_coordinator"
    reported_at: datetime
    resolved_at: datetime | None
    evidence: dict             # field reports, sensor data, etc.
    activity_history: list
    metadata: dict
```

#### Operation

A coordinated response action involving one or more organizations.

```python
class Operation:
    id: str
    name: str                  # human-readable name
    type: str                  # "rescue" | "medical" | "supply_delivery" | "evacuation" | "assessment" | "other"
    status: str                # PLANNING | ACTIVE | PAUSED | COMPLETED | CANCELLED
    lead_org_id: str           # primary responsible organization
    participating_orgs: list   # [{org_id, org_name, role, joined_at}]
    needs_addressed: list      # [need_ids this operation responds to]
    location: dict             # {lat, lon, location_name, district_id}
    route: dict | None         # planned route if applicable
    resources_committed: list  # [{org_id, resource_type, quantity, unit}]
    start_time: datetime | None
    end_time: datetime | None
    created_at: datetime
    updated_at: datetime
    activity_history: list
    metadata: dict
```

#### Organization

```python
class Organization:
    id: str
    name: str
    type: str                  # "ngo" | "government" | "military" | "community" | "other"
    # SHARED (visible to network)
    published_capabilities: list  # ["medical", "transport", "shelter", ...]
    public_contact: dict       # {phone, email, radio_channel, base_location}
    active_public_operations: list  # [operation_ids]
    published_resource_offers: list  # [offer_ids]
    # PRIVATE (only visible to org)
    # These are NOT stored in the network database — they live in the org's private workspace
    # full_inventory: list
    # staff_roster: list
    # internal_missions: list
    # financial_state: dict
    created_at: datetime
    metadata: dict
```

### 6.2 Objects That Are Already Shared (Existing)

| Object | Current State | Phase 7 Addition |
|--------|--------------|------------------|
| FloodSnapshot | ✅ Exists, 4 districts | Add organization attribution for verified observations |
| FieldReport | ✅ Exists | Add org attribution, verification chain |
| Override | ✅ Exists | Add org attribution, network propagation |
| District/Settlement | ✅ Exists | No change |
| Building/MedicalFacility/Road | ✅ Exists | Add operational status overlay |

---

## 7. Data Visibility Model

### 7.1 Visibility Levels

| Level | Description | Who Sees It |
|-------|-------------|-------------|
| `network` | Shared operational state | All authenticated users |
| `organization` | Org-specific shared state | Members of that org + network coordinators |
| `private` | Org internal state | Only members of that org |
| `system` | System-generated data (flood, OSM) | Everyone (read-only) |
| `coordinator` | Network coordinator workspace | Network coordinators only |

### 7.2 Object-Level Visibility

Each shared object carries a `visibility` field:

- `Need.default_visibility = "network"` (needs are shared by design)
- `ResourceOffer.default_visibility = "network"` (offers are shared by design)
- `FieldReport.default_visibility = "network"` (community reports are shared)
- `Operation.default_visibility = "organization"` (can be promoted to network)
- `Incident.default_visibility = "network"` (incidents affect everyone)

### 7.3 Access Control Matrix

| Action | Community Reporter | NGO User | NGO Admin | Network Coordinator | System Admin |
|--------|:-:|:-:|:-:|:-:|:-:|
| View shared needs | ✅ | ✅ | ✅ | ✅ | ✅ |
| Create need (community report) | ✅ | ✅ | ✅ | ✅ | ✅ |
| Submit field report | ✅ | ✅ | ✅ | ✅ | ✅ |
| View org private state | ❌ | ✅ | ✅ | ❌ | ✅ |
| Publish resource offer | ❌ | ✅ | ✅ | ✅ | ✅ |
| Join response to need | ❌ | ✅ | ✅ | ✅ | ✅ |
| Create operation | ❌ | ❌ | ✅ | ✅ | ✅ |
| Apply override | ❌ | ✅ | ✅ | ✅ | ✅ |
| Verify field report | ❌ | ✅ | ✅ | ✅ | ✅ |
| Resolve need | ❌ | ✅ | ✅ | ✅ | ✅ |
| View AI recommendations | ❌ | ✅ | ✅ | ✅ | ✅ |
| Approve AI match proposal | ❌ | ❌ | ❌ | ✅ | ✅ |
| Manage organizations | ❌ | ❌ | ❌ | ✅ | ✅ |
| System configuration | ❌ | ❌ | ❌ | ❌ | ✅ |
| Manage permissions | ❌ | ❌ | ❌ | ❌ | ✅ |

---

## 8. UI Information Architecture

### 8.1 Primary Navigation (Top-level routes)

| Route | Label | Icon | Purpose |
|-------|-------|------|---------|
| `/` | Dashboard | LayoutDashboard | "What needs attention now?" — the main view |
| `/map` | Live Map | Map | Full operational map with all layers |
| `/needs` | Needs | AlertTriangle | All shared needs, filterable |
| `/operations` | Operations | Zap | Active and planned operations |
| `/organizations` | Organizations | Users | Network participants and their published state |
| `/field-reports` | Field Intelligence | FileText | Field reports and community intelligence |
| `/ai-coordinator` | AI Coordinator | Brain | AI analysis, gap detection, recommendations |

### 8.2 Secondary Navigation (Context-dependent panels/drawers)

| Panel | Context | Content |
|-------|---------|---------|
| Need Detail | From `/needs` or Dashboard | Full need, responders, activity, AI recommendations |
| Operation Detail | From `/operations` or Dashboard | Operation plan, resources, route, status |
| Org Profile | From `/organizations` | Org capabilities, published offers, active operations |
| Route Planner | From Map or Dashboard | Route between points, flood crossing analysis |
| Override Manager | From Map popup | Apply/modify/revoke overrides |
| Notification Center | Global (header) | Alert feed, notification categories |

### 8.3 Design Decision: Consolidated Views

Rather than twelve disconnected pages, the UI consolidates into:

1. **Dashboard** — the "what needs attention now" view (primary)
2. **Map** — the spatial operational picture (primary)
3. **Object views** — Needs, Operations, Organizations as list + detail
4. **Intelligence** — Field reports and AI analysis
5. **Settings** — Permissions, notifications, org management

The **Dashboard** and **Map** are always accessible. Everything else is one click away.

### 8.4 Dashboard Priority Stack

The main dashboard answers: **"What needs attention now?"**

```
┌─────────────────────────────────────────────────────┐
│  ALERTS / AI COORDINATOR RECOMMENDATIONS            │
│  (coordination gaps, unmet critical needs,          │
│   route disruptions, matching proposals)            │
├─────────────────────────────────────────────────────┤
│  CRITICAL / HIGH-URGENCY NEEDS                      │
│  (sorted by urgency × time open, with responder     │
│   count and remaining requirement)                  │
├─────────────────────────────────────────────────────┤
│  ACTIVE OPERATIONS STATUS                           │
│  (quick status cards: on-track / delayed / blocked) │
├─────────────────────────────────────────────────────┤
│  RECENT FIELD REPORTS                               │
│  (latest unverified and recently verified reports)  │
├─────────────────────────────────────────────────────┤
│  RESOURCE SHORTAGES                                 │
│  (needs with no or insufficient resource offers)    │
├─────────────────────────────────────────────────────┤
│  MINI MAP                                           │
│  (overview of flood extent + need locations +       │
│   active operations, clickable to full map)         │
└─────────────────────────────────────────────────────┘
```

---

## 9. Main Dashboard Wireframe

```
┌──────────────────────────────────────────────────────────────────────────┐
│  ReliefOS                                    [🔔 3] [👤 Coordinator ▾]  │
│  ─────────────────────────────────────────────────────────────────────── │
│  [Dashboard] [Map] [Needs] [Operations] [Orgs] [Field Intel] [AI]      │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────────────────────────┐  ┌───────────────────────────┐  │
│  │ 🧠 AI COORDINATOR                    │  │ 📍 SITUATION MAP (mini)   │  │
│  │                                     │  │                           │  │
│  │ ⚠ 2 orgs responding to same need   │  │   [flood polygons]        │  │
│  │    while Jorhat food need has       │  │   [need markers]          │  │
│  │    0 responders                     │  │   [operation markers]     │  │
│  │                                     │  │   [field report dots]     │  │
│  │ ⚠ Bridge closure affects 3 active  │  │                           │  │
│  │    operations in Charaideo          │  │                           │  │
│  │                                     │  │                           │  │
│  │ 📋 Proposed: Match Org-B boats     │  │                           │  │
│  │    to Jorhat rescue need #1042     │  │                           │  │
│  └─────────────────────────────────────┘  └───────────────────────────┘  │
│                                                                          │
│  ┌─────────────────────────────────────┐  ┌───────────────────────────┐  │
│  │ 🔴 URGENT NEEDS (4)                 │  │ 🚚 ACTIVE OPERATIONS (3)  │  │
│  │                                     │  │                           │  │
│  │  #1042 Food shortage — Jorhat      │  │  ● Rescue Op Jorhat       │  │
│  │     Urgency: CRITICAL  Resp: 0/2   │  │    Status: ACTIVE  ✓      │  │
│  │     Posted: 2h ago                 │  │                           │  │
│  │                                     │  │  ● Supply delivery —      │  │
│  │  #1041 Medical need — Golaghat     │  │    Sivasagar              │  │
│  │     Urgency: HIGH  Resp: 1/1      │  │    Status: DELAYED  ⚠     │  │
│  │     Posted: 4h ago                 │  │                           │  │
│  │                                     │  │  ● Assessment — Charaideo │  │
│  │  #1039 Rescue needed — Jorhat     │  │    Status: ACTIVE  ✓      │  │
│  │     Urgency: CRITICAL  Resp: 0/1  │  │                           │  │
│  │     Posted: 1h ago                 │  │                           │  │
│  │                                     │  │                           │  │
│  │  #1038 Water — Charaideo           │  │                           │  │
│  │     Urgency: HIGH  Resp: 0/1      │  │                           │  │
│  └─────────────────────────────────────┘  └───────────────────────────┘  │
│                                                                          │
│  ┌─────────────────────────────────────┐  ┌───────────────────────────┐  │
│  │ 📝 RECENT FIELD REPORTS (5)         │  │ 📦 RESOURCE GAPS (2)      │  │
│  │                                     │  │                           │  │
│  │  • "Road blocked near bridge"       │  │  Need: 5 rescue boats     │  │
│  │    Golaghat · 30 min ago · ⚠ UNVER │  │  Offered: 2              │  │
│  │                                     │  │  Gap: 3 boats             │  │
│  │  • "200 people at school need       │  │                           │  │
│  │    food and water"                  │  │  Need: Medical kits ×50   │  │
│  │    Jorhat · 1h ago · ⚠ UNVERIFIED │  │  Offered: 0              │  │
│  │                                     │  │  Gap: 50 kits             │  │
│  │  • "Hospital running but low       │  │                           │  │
│  │    supplies"                        │  │                           │  │
│  │    Sivasagar · 2h ago · ✓ VERIFIED │  │                           │  │
│  └─────────────────────────────────────┘  └───────────────────────────┘  │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │  💡 DATA GAPS                                                     │  │
│  │  • No field reports for Golaghat in last 6 hours                 │  │
│  │  • Road status not verified for Charaideo bridge area            │  │
│  │  • Flood data for Sivasagar is 29 days old                       │  │
│  └────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 10. Map Interaction Model

### 10.1 Layer Architecture

The map is the spatial Common Operating Picture. Layers combine static data with live operational state.

| Layer | Data Source | Default | Toggleable | Interactive |
|-------|-----------|:-------:|:----------:|:-----------:|
| Flood Extent | PostGIS flood_snapshots | ✅ | ✅ | Click for snapshot detail |
| District Boundaries | PostGIS districts | ✅ | ✅ | Click for district summary |
| Settlements | PostGIS settlements | ✅ | ✅ | Click for assessment |
| Buildings (exposed) | PostGIS buildings + flood zone | ❌ | ✅ | Hover for info |
| Roads | PostGIS roads | ✅ | ✅ | Click for status |
| Bridges | PostGIS roads (is_bridge) | ✅ | ✅ | Click for status |
| Medical Facilities | PostGIS medical_facilities | ✅ | ✅ | Click for status + override |
| Needs | Needs table (shared) | ✅ | ✅ | Click for need detail |
| Incidents | Incidents table | ✅ | ✅ | Click for incident detail |
| Resource Offers | ResourceOffers table | ❌ | ✅ | Click for offer detail |
| Active Operations | Operations table | ✅ | ✅ | Click for operation detail |
| Field Reports | FieldReports table | ✅ | ✅ | Click for report detail |
| Overrides | Overrides table | ✅ | ✅ | Visual indicator on affected objects |
| Routes | Routing tool | ❌ | ✅ | Click for route detail |

### 10.2 Operational State Overlay

The map combines raw data with operational state. Example:

```
Raw OSM Data:          Road = open (highway=primary)
    +
Local Override:        Override: road_blocked, reason: "flood damage verified by field team"
    =
Operational State:     Road = BLOCKED (displayed in red, with override badge)
```

The underlying OSM fact is never destroyed. The override is additive.

### 10.3 Map Interactions

| Interaction | Result |
|------------|--------|
| Click flood polygon | Show snapshot detail: date, source, area, polygon count |
| Click need marker | Show need detail panel (inline or slide-out) |
| Click operation marker | Show operation detail with route and resources |
| Click field report | Show report detail with verification state |
| Click medical facility | Show status, override option, nearest-needs |
| Click road/bridge | Show status, override option, affected operations |
| Right-click map | "Report issue here" → field report creation |
| Drag route endpoint | Re-calculate route, check flood crossing |
| Layer toggle | Show/hide any layer |
| District filter | Filter all layers to one district |
| Time slider | Filter flood snapshots by date |

---

## 11. Need Workflow

### 11.1 Need Lifecycle

```
1. CREATION
   Source: Coordinator, field report, AI detection, community report
   Action: Need record created with status=OPEN
   Visibility: network (shared by default)

2. REVIEW
   Action: Coordinator or AI reviews need
   Status: OPEN → UNDER_REVIEW
   AI may suggest: matching resource offers, similar past needs

3. RESPONSE
   Action: Organization(s) join the response
   Status: UNDER_REVIEW → RESPONDING
   Activity: "Org-X joined response"
   Resources committed tracked per organization

4. PARTIAL RESOLUTION
   Action: Some resources delivered, some still needed
   Status: RESPONDING → PARTIALLY_RESOLVED
   Remaining requirement updated

5. RESOLUTION
   Action: All requirements met
   Status: → RESOLVED
   Activity: "Need resolved by Org-A, Org-B"

6. CLOSURE
   Action: Coordinator confirms resolution
   Status: RESOLVED → CLOSED
```

### 11.2 Need Detail View

```
┌────────────────────────────────────────────────────┐
│  Need #1042 — Food Shortage                       │
│  Status: OPEN  │  Urgency: CRITICAL               │
│  Posted: 2h ago by Coordinator                     │
├────────────────────────────────────────────────────┤
│                                                    │
│  📍 Location: Jorhat (26.74°N, 94.21°E)           │
│  🌊 Flood context: 3,831 polygons, observed Jul 29│
│  📊 Evidence: 142 buildings in flood zone          │
│                                                    │
│  REQUESTED RESOURCES:                              │
│  • Food rations — 2,000 people × 3 days           │
│  • Water containers — 500 units                    │
│                                                    │
│  RESPONDING ORGANIZATIONS:                         │
│  (none yet)                                        │
│                                                    │
│  💡 AI RECOMMENDATION:                             │
│  "Org-B has 500 food kits available in Jorhat.     │
│   Org-C has water purification capacity.           │
│   Consider requesting both."                       │
│                                                    │
│  📋 ACTIVITY TIMELINE:                             │
│  • 2h ago — Need created by Coordinator            │
│  • 1h ago — AI detected: 2 orgs may have resources│
│                                                    │
│  [Join Response]  [Offer Resource]  [Share Update] │
└────────────────────────────────────────────────────┘
```

---

## 12. Resource Offer Workflow

### 12.1 Offer Lifecycle

```
1. PUBLICATION
   Action: Organization publishes an offer
   Status: OFFERED
   Visibility: network

2. ACCEPTANCE
   Action: Coordinator or need-response accepts the offer
   Status: OFFERED → ACCEPTED
   Linked to specific need or operation

3. DEPLOYMENT
   Action: Resources are deployed
   Status: ACCEPTED → DEPLOYED
   Activity logged

4. WITHDRAWAL (optional)
   Action: Organization withdraws the offer
   Status: → WITHDRAWN
   Reason recorded

5. EXPIRATION
   Action: Offer passes available_until date
   Status: → EXPIRED
   Auto-triggered by system
```

### 12.2 Matching Model

```
Need #1042: Food, Jorhat, CRITICAL
    │
    ▼
Network Coordination Worker searches:
  - Resource offers with type=food
  - In or near Jorhat district
  - Status=OFFERED
  - Available now
    │
    ▼
Found: Org-B offer (500 food kits, Jorhat)
Found: Org-C offer (water purification, Sivasagar)
    │
    ▼
Network Main Agent proposes match in shared workspace
    │
    ▼
Human coordinator reviews → Approves or Rejects
    │
    ▼
Operation created → Resources deployed
```

---

## 13. Organization Workflow

### 13.1 Organization States

```
REGISTRATION
  → Organization created with basic info
  → Published capabilities set
  → Contact info published

ACTIVE PARTICIPATION
  → Publishes resource offers
  → Joins responses to needs
  → Creates/manages operations
  → Submits field reports

COLLABORATION
  → Responds to network coordination proposals
  → Shares verified field intelligence
  → Updates operation status

WITHDRAWAL
  → Can temporarily pause participation
  → Can permanently leave network
  → Published objects archived
```

### 13.3 Organization Profile View

```
┌────────────────────────────────────────────────────┐
│  🏥 Org-B — Relief Services India                  │
│  Type: NGO  │  Status: ACTIVE                      │
├────────────────────────────────────────────────────┤
│                                                    │
│  PUBLISHED CAPABILITIES:                           │
│  [Medical] [Transport] [Shelter]                   │
│                                                    │
│  CONTACT:                                          │
│  📞 +91-XXX-XXXX  │  📻 Channel 7                 │
│  📍 Base: Jorhat Relief Camp                       │
│                                                    │
│  ACTIVE OPERATIONS: (2)                            │
│  • Rescue Op Jorhat (lead)                         │
│  • Medical support Golaghat (supporting)           │
│                                                    │
│  PUBLISHED OFFERS: (1)                             │
│  • 500 food kits, available now, Jorhat            │
│                                                    │
│  CONTRIBUTIONS:                                    │
│  • Joined 3 needs this response                    │
│  • 2 field reports verified                        │
│  • 1 operation completed                           │
│                                                    │
│  [Message]  [View Operations]  [View Offers]       │
└────────────────────────────────────────────────────┘
```

---

## 14. Field Report Workflow

### 14.1 Report Lifecycle

```
1. SUBMISSION
   Source: Community member, field team, coordinator
   Input: Raw text (no GIS knowledge required)
   System: AI extracts structured fields
   Status: UNVERIFIED

2. VERIFICATION
   Action: Authorized user verifies report
   Status: UNVERIFIED → VERIFIED
   Verification chain tracked

3. INTEGRATION
   Action: Report affects operational map
   Example: "Road blocked" → road status override proposed
   AI coordinator evaluates consequences

4. DISPUTED (optional)
   Action: Conflicting information received
   Status: → DISPUTED
   Resolution required
```

### 14.2 Community Report Form

The field report form is designed for non-GIS users:

```
┌────────────────────────────────────────────────────┐
│  📝 SUBMIT FIELD REPORT                            │
├────────────────────────────────────────────────────┤
│                                                    │
│  What did you observe?                             │
│  ┌──────────────────────────────────────────────┐  │
│  │ Road to Dibrugarh blocked near old bridge.   │  │
│  │ 200 people at school need food and water.    │  │
│  │ Hospital running but low supplies.           │  │
│  └──────────────────────────────────────────────┘  │
│                                                    │
│  Where? (optional — tap map or describe)           │
│  [📍 Tap map]  OR  [Type location description]    │
│                                                    │
│  Report type: (auto-detected from text)            │
│  [🚧 Road blocked] [🌊 Flooding] [🏥 Medical]     │
│  [🍞 Food shortage] [💧 Water shortage] [ Other]  │
│                                                    │
│  Photo (optional):  [📷 Add Photo]                 │
│                                                    │
│  Your name (optional): [_____________]             │
│                                                    │
│  ──────────────────────────────────────────────    │
│  ⓘ This report will be reviewed before it          │
│    affects the operational map.                     │
│                                                    │
│  [Submit Report]                                   │
└────────────────────────────────────────────────────┘
```

---

## 15. Override Workflow

### 15.1 Override Lifecycle

The existing override system (`agent/overrides.py`) already handles the core pattern. Phase 7 extends it with:

1. **Network propagation** — when an override affects operations, the system identifies impacted operations
2. **Organization attribution** — overrides record which org's member applied them
3. **AI consequence analysis** — AI coordinator evaluates the impact of overrides on active operations

### 15.2 Override + Consequence Flow

```
User applies override: "Bridge X — BLOCKED"
    │
    ▼
System records override (existing)
    │
    ▼
System queries: Which operations use Bridge X?
    │
    ▼
Found: 3 active operations affected
    │
    ▼
AI Coordinator:
  - Summarizes impact
  - Proposes route alternatives
  - Surfaces alert in shared workspace
    │
    ▼
Affected organizations notified
```

---

## 16. Notification Model

### 16.1 Notification Categories

| Category | Trigger | Recipients |
|----------|---------|-----------|
| `urgent_need` | New need with urgency=critical | All network coordinators + nearby orgs |
| `need_update` | Status change on a need | Orgs responding to that need |
| `resource_offer` | New offer matching an open need | Orgs with open needs of that type |
| `operation_update` | Status change on an operation | Orgs participating in that operation |
| `route_change` | Road/bridge status override | Orgs with operations in that area |
| `field_report` | New unverified field report | Network coordinators (for verification) |
| `field_report_verified` | Report verified/disputed | Reporter + network coordinators |
| `ai_recommendation` | AI proposes a match or detects a gap | Network coordinators |
| `coordination_gap` | High-priority need with no responders | Network coordinators |
| `override_applied` | Override affects shared state | Orgs with operations in that area |

### 16.2 Notification Delivery

| Method | Default | Audience |
|--------|:-------:|----------|
| In-app bell | ✅ | All users |
| Dashboard alert card | ✅ | All users |
| Map visual indicator | ✅ | All users |
| Email digest | Optional | Org admins, coordinators |
| Webhook | Optional | External systems |

### 16.3 Notification Preferences

Users can configure:
- Which categories to receive
- Delivery method per category
- Quiet hours
- Digest frequency (real-time, hourly, daily)

---

## 17. AI Coordinator Behavior

### 17.1 Three Modes

| Mode | Trigger | Example |
|------|---------|---------|
| **Reactive** | User asks a question | "Which needs have no responders?" |
| **Event-driven** | Meaningful state change | New field report, override applied, need created |
| **Proactive** | Pattern detection | "Two orgs responding to same need while another need has 0 responders" |

### 17.2 AI Coordinator Capabilities

```
MONITORING:
  - Watch for coordination gaps (needs with no responders)
  - Watch for resource conflicts (duplicate responses)
  - Watch for stale data (flood snapshots > 24h old)
  - Watch for consequence chains (bridge closure → affected operations)

ANALYSIS:
  - Match needs to resource offers
  - Evaluate field report credibility
  - Assess operation efficiency
  - Detect emerging patterns across districts

SURFACING:
  - Surface recommendations in the dashboard
  - Surface alerts in the notification center
  - Surface gap analysis in the AI Coordinator panel
  - Surface proposed matches for human approval

NEVER:
  - Directly control organizations
  - Auto-create operations without human approval
  - Override human decisions
  - Make resource allocation without human confirmation
```

### 17.3 AI Question Interface

The AI does NOT create a conversational interrogation flow. Instead:

1. **Contextual suggestions** — when a user reviews a proposed match, the AI asks only for missing info
2. **Dashboard cards** — AI recommendations appear as cards in the dashboard, not as chat messages
3. **Map overlays** — AI-detected issues appear as map indicators
4. **Notification cards** — AI alerts appear in the notification center

```
┌────────────────────────────────────────────────────┐
│  🧠 AI COORDINATOR                                 │
├────────────────────────────────────────────────────┤
│                                                    │
│  COORDINATION GAPS DETECTED:                       │
│                                                    │
│  ⚠ Need #1042 (Food — Jorhat, CRITICAL)           │
│    has 0 responders after 2 hours.                 │
│    Suggested: Contact Org-B (has food supplies)    │
│                                                    │
│  ⚠ Need #1039 (Rescue — Jorhat, CRITICAL)         │
│    has 0 responders after 1 hour.                  │
│    Suggested: Contact Org-A (has rescue boats)     │
│                                                    │
│  RESOURCE MATCH PROPOSALS:                         │
│                                                    │
│  📋 Proposal: Match Org-B → Need #1042             │
│    Org-B has 500 food kits in Jorhat (OFFERED)     │
│    Need #1042 needs food for 2,000 people          │
│    Match quality: HIGH (same district, right type) │
│    [Approve] [Reject] [View Details]               │
│                                                    │
│  CONSEQUENCE ALERTS:                               │
│                                                    │
│  ⚠ Bridge closure on NH-37 affects 2 active       │
│    operations in Golaghat.                         │
│    Suggested: Reroute via alternate bridge.        │
│    [View Affected Operations] [View Alternatives]  │
│                                                    │
│  DATA FRESHNESS:                                   │
│                                                    │
│  ℹ Sivasagar flood data is 29 days old.           │
│    Conditions may have changed significantly.      │
│    Consider requesting updated Sentinel-1 pass.   │
└────────────────────────────────────────────────────┘
```

---

## 18. Permission Model

### 18.1 Roles

| Role | Description | Scope |
|------|-------------|-------|
| `community_reporter` | Can submit field reports, view shared state | Network-wide (read), own reports (write) |
| `ngo_user` | Org member with operational access | Org private + shared network |
| `ngo_admin` | Org administrator | Org private + shared network + org management |
| `network_coordinator` | Emergency coordination authority | Shared network + all orgs (read) + AI proposals |
| `system_admin` | Technical administration | Full access |

### 18.2 Permission Matrix

| Permission | community_reporter | ngo_user | ngo_admin | network_coordinator | system_admin |
|------------|:-:|:-:|:-:|:-:|:-:|
| View shared map | ✅ | ✅ | ✅ | ✅ | ✅ |
| View shared needs | ✅ | ✅ | ✅ | ✅ | ✅ |
| Create need | ✅ | ✅ | ✅ | ✅ | ✅ |
| Submit field report | ✅ | ✅ | ✅ | ✅ | ✅ |
| Verify field report | — | ✅ | ✅ | ✅ | ✅ |
| View org private state | — | ✅ | ✅ | — | ✅ |
| Publish resource offer | — | ✅ | ✅ | ✅ | ✅ |
| Join need response | — | ✅ | ✅ | ✅ | ✅ |
| Create operation | — | — | ✅ | ✅ | ✅ |
| Apply override | — | ✅ | ✅ | ✅ | ✅ |
| View AI recommendations | — | ✅ | ✅ | ✅ | ✅ |
| Approve AI match | — | — | — | ✅ | ✅ |
| Manage organizations | — | — | — | ✅ | ✅ |
| Manage permissions | — | — | — | — | ✅ |
| System configuration | — | — | — | — | ✅ |

### 18.3 Implementation Approach

Phase 7 introduces role-based access but keeps it simple initially:

- **No complex RBAC framework** — use a simple role field on the user record
- **Middleware checks** on API endpoints
- **Frontend hides** actions the user cannot perform
- **Backend enforces** permissions regardless of frontend

---

## 19. Existing-Code Reuse Analysis

### 19.1 What Can Be Reused Directly

| Component | Current Location | Reuse Plan |
|-----------|-----------------|------------|
| Flood intelligence | `agent/tools/flood_tool.py` | ✅ Direct reuse — feeds map + dashboard |
| Building exposure | `agent/tools/exposure_tool.py` | ✅ Direct reuse — feeds map + need evidence |
| Medical accessibility | `agent/tools/accessibility_tool.py` | ✅ Direct reuse — feeds map + need evidence |
| Road status | `agent/tools/road_status_tool.py` | ✅ Direct reuse — feeds map + incident detection |
| Routing | `agent/tools/routing_tool.py` | ✅ Direct reuse — feeds operation routes |
| Allocation/PDC | `agent/tools/allocation_tool.py` | ✅ Direct reuse — feeds priority ranking |
| Field intelligence | `agent/tools/field_intelligence_tool.py` | ✅ Direct reuse — feeds report extraction |
| Query parser | `agent/tools/query_parser_tool.py` | ✅ Direct reuse — feeds AI coordinator queries |
| Operational planner | `agent/planner.py` | ✅ Direct reuse — feeds AI coordinator reasoning |
| Flood snapshots | `agent/data/models.py` (FloodSnapshot) | ✅ Direct reuse — foundation of flood layer |
| Field reports | `agent/data/models.py` (FieldReport) | ✅ Extend with org attribution |
| Overrides | `agent/overrides.py` | ✅ Extend with org attribution + propagation |
| District/Settlement | `agent/data/models.py` | ✅ Direct reuse — no changes |
| PostGIS schema | `agent/data/schema.py` | ✅ Extend with new tables |
| Repository | `agent/data/repository.py` | ✅ Extend with new query methods |
| API | `agent/api.py` | ✅ Extend with new endpoints |
| Assessment | `agent/assessment.py` | ✅ Direct reuse — feeds dashboard |
| Coordinator Agent | `agent/agents/coordinator_agent.py` | ✅ Extend into Network Main Agent |
| Map component | `frontend/src/components/SituationMap.jsx` | ✅ Extend with new layers |
| Dashboard | `frontend/src/App.jsx` (DashboardPage) | ✅ Redesign with new layout |
| Field Intelligence | `frontend/src/components/FieldIntelligencePage.jsx` | ✅ Extend with verification workflow |
| Agent Trace | `frontend/src/components/StagedReveal.jsx` | ✅ Reuse for AI coordinator trace |

### 19.2 What Needs Extension

| Component | Extension Needed |
|-----------|-----------------|
| `FloodSnapshot` model | Add organization attribution for verified observations |
| `FieldReport` model | Add org attribution, verification chain |
| `Override` model | Add org attribution, network propagation |
| Repository | Add queries for needs, offers, operations, orgs |
| API | Add CRUD endpoints for needs, offers, operations, orgs |
| Planner | Integrate with shared need/offer matching |
| Map component | Add need, offer, operation, incident layers |
| Dashboard | Redesign for shared operational picture |

### 19.3 What Needs to Be Created

| New Component | Purpose |
|---------------|---------|
| `Need` model + table | Shared need records |
| `ResourceOffer` model + table | Published resource offers |
| `Incident` model + table | Disruption events |
| `Operation` model + table | Coordinated response actions |
| `Organization` model + table | Network participants |
| `OrganizationUser` model + table | User-org membership |
| `Notification` model + table | Alert delivery |
| `ActivityEvent` model + table | Audit trail for all objects |
| Network Main Agent | AI backbone for shared network |
| NGO Main Agent | Per-org AI mediator |
| Need CRUD API | Create/read/update/close needs |
| Offer CRUD API | Publish/accept/withdraw offers |
| Operation CRUD API | Create/manage operations |
| Org CRUD API | Register/manage organizations |
| Notification API | Query/dismiss notifications |
| Dashboard redesign | Shared operational picture layout |
| Map layer extensions | Need, offer, operation, incident layers |
| Need detail panel | Full need workflow UI |
| Operation detail panel | Operation management UI |
| Org profile panel | Organization view UI |
| AI Coordinator panel | Recommendations, gaps, matches |
| Notification center | Alert feed with categories |

---

## 20. Proposed Backend/Schema Changes

### 20.1 New Tables

```sql
-- Organizations
CREATE TABLE organizations (
    id VARCHAR(256) PRIMARY KEY,
    name VARCHAR(512) NOT NULL,
    type VARCHAR(128) NOT NULL DEFAULT 'ngo',
    published_capabilities JSON NOT NULL DEFAULT '[]',
    public_contact JSON NOT NULL DEFAULT '{}',
    status VARCHAR(64) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSON NOT NULL DEFAULT '{}'
);

-- Organization users (membership)
CREATE TABLE organization_users (
    id VARCHAR(256) PRIMARY KEY,
    org_id VARCHAR(256) REFERENCES organizations(id) ON DELETE CASCADE,
    user_id VARCHAR(256) NOT NULL,
    role VARCHAR(64) NOT NULL DEFAULT 'member',  -- 'member' | 'admin'
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(org_id, user_id)
);

-- Network users (authentication)
CREATE TABLE network_users (
    id VARCHAR(256) PRIMARY KEY,
    username VARCHAR(256) NOT NULL UNIQUE,
    display_name VARCHAR(512) NOT NULL,
    role VARCHAR(64) NOT NULL DEFAULT 'community_reporter',
    org_id VARCHAR(256) REFERENCES organizations(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login TIMESTAMPTZ,
    metadata JSON NOT NULL DEFAULT '{}'
);

-- Shared Needs
CREATE TABLE needs (
    id VARCHAR(256) PRIMARY KEY,
    type VARCHAR(128) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    location_name VARCHAR(512),
    district_id VARCHAR(128) REFERENCES districts(id) ON DELETE SET NULL,
    lat FLOAT,
    lon FLOAT,
    location_geom Geometry('Point', 4326),
    urgency VARCHAR(64) NOT NULL DEFAULT 'medium',
    status VARCHAR(64) NOT NULL DEFAULT 'OPEN',
    requested_resources JSON NOT NULL DEFAULT '[]',
    evidence JSON NOT NULL DEFAULT '{}',
    reporter_id VARCHAR(256),
    reporter_type VARCHAR(128) NOT NULL DEFAULT 'coordinator',
    confidence FLOAT NOT NULL DEFAULT 0.5,
    provenance VARCHAR(64) NOT NULL DEFAULT 'COORDINATOR_INPUT',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSON NOT NULL DEFAULT '{}'
);
CREATE INDEX ix_needs_district_id ON needs(district_id);
CREATE INDEX ix_needs_status ON needs(status);
CREATE INDEX ix_needs_urgency ON needs(urgency);
CREATE INDEX ix_needs_location ON needs USING gist(location_geom);

-- Resource Offers
CREATE TABLE resource_offers (
    id VARCHAR(256) PRIMARY KEY,
    org_id VARCHAR(256) REFERENCES organizations(id) ON DELETE CASCADE,
    resource_type VARCHAR(128) NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 0,
    unit VARCHAR(64) NOT NULL DEFAULT 'units',
    available_from TIMESTAMPTZ NOT NULL DEFAULT now(),
    available_until TIMESTAMPTZ,
    lat FLOAT,
    lon FLOAT,
    location_name VARCHAR(512),
    district_id VARCHAR(128) REFERENCES districts(id) ON DELETE SET NULL,
    status VARCHAR(64) NOT NULL DEFAULT 'OFFERED',
    notes TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSON NOT NULL DEFAULT '{}'
);
CREATE INDEX ix_resource_offers_org_id ON resource_offers(org_id);
CREATE INDEX ix_resource_offers_status ON resource_offers(status);
CREATE INDEX ix_resource_offers_district_id ON resource_offers(district_id);

-- Incidents
CREATE TABLE incidents (
    id VARCHAR(256) PRIMARY KEY,
    type VARCHAR(128) NOT NULL,
    severity VARCHAR(64) NOT NULL DEFAULT 'medium',
    location_name VARCHAR(512),
    district_id VARCHAR(128) REFERENCES districts(id) ON DELETE SET NULL,
    lat FLOAT,
    lon FLOAT,
    location_geom Geometry('Point', 4326),
    description TEXT NOT NULL DEFAULT '',
    status VARCHAR(64) NOT NULL DEFAULT 'ACTIVE',
    reported_by VARCHAR(256),
    reported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ,
    affected_operations JSON NOT NULL DEFAULT '[]',
    evidence JSON NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSON NOT NULL DEFAULT '{}'
);
CREATE INDEX ix_incidents_district_id ON incidents(district_id);
CREATE INDEX ix_incidents_status ON incidents(status);
CREATE INDEX ix_incidents_location ON incidents USING gist(location_geom);

-- Operations
CREATE TABLE operations (
    id VARCHAR(256) PRIMARY KEY,
    name VARCHAR(512) NOT NULL,
    type VARCHAR(128) NOT NULL DEFAULT 'other',
    status VARCHAR(64) NOT NULL DEFAULT 'PLANNING',
    lead_org_id VARCHAR(256) REFERENCES organizations(id) ON DELETE SET NULL,
    participating_orgs JSON NOT NULL DEFAULT '[]',
    needs_addressed JSON NOT NULL DEFAULT '[]',
    location_name VARCHAR(512),
    district_id VARCHAR(128) REFERENCES districts(id) ON DELETE SET NULL,
    lat FLOAT,
    lon FLOAT,
    route JSON,
    resources_committed JSON NOT NULL DEFAULT '[]',
    start_time TIMESTAMPTZ,
    end_time TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSON NOT NULL DEFAULT '{}'
);
CREATE INDEX ix_operations_district_id ON operations(district_id);
CREATE INDEX ix_operations_status ON operations(status);
CREATE INDEX ix_operations_lead_org_id ON operations(lead_org_id);

-- Notifications
CREATE TABLE notifications (
    id VARCHAR(256) PRIMARY KEY,
    user_id VARCHAR(256) NOT NULL,
    category VARCHAR(128) NOT NULL,
    title VARCHAR(512) NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    entity_type VARCHAR(128),
    entity_id VARCHAR(256),
    read BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSON NOT NULL DEFAULT '{}'
);
CREATE INDEX ix_notifications_user_id ON notifications(user_id);
CREATE INDEX ix_notifications_read ON notifications(read);
CREATE INDEX ix_notifications_created_at ON notifications(created_at);

-- Activity Events (audit trail)
CREATE TABLE activity_events (
    id VARCHAR(256) PRIMARY KEY,
    entity_type VARCHAR(128) NOT NULL,
    entity_id VARCHAR(256) NOT NULL,
    action VARCHAR(128) NOT NULL,
    actor_id VARCHAR(256),
    actor_name VARCHAR(512),
    detail TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSON NOT NULL DEFAULT '{}'
);
CREATE INDEX ix_activity_events_entity ON activity_events(entity_type, entity_id);
CREATE INDEX ix_activity_events_created_at ON activity_events(created_at);
```

### 20.2 Schema Migration Strategy

- All new tables are **additive** — no existing tables are modified
- Existing `field_reports` table gets optional `org_id` column (nullable, backward-compatible)
- Existing `overrides` table gets optional `org_id` column (nullable, backward-compatible)
- Use `alembic` or manual SQL migration scripts
- Migration is idempotent (CREATE TABLE IF NOT EXISTS)

### 20.3 API Extensions

New Flask blueprint or extending `agent/api.py`:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/needs` | GET | List shared needs (filterable) |
| `/api/needs` | POST | Create a new need |
| `/api/needs/<id>` | GET | Get need detail |
| `/api/needs/<id>` | PATCH | Update need status |
| `/api/needs/<id>/respond` | POST | Join response to need |
| `/api/needs/<id>/activity` | GET | Get activity timeline |
| `/api/offers` | GET | List resource offers |
| `/api/offers` | POST | Publish a resource offer |
| `/api/offers/<id>` | PATCH | Update/withdraw offer |
| `/api/incidents` | GET | List incidents |
| `/api/incidents` | POST | Report an incident |
| `/api/incidents/<id>` | PATCH | Update incident status |
| `/api/operations` | GET | List operations |
| `/api/operations` | POST | Create an operation |
| `/api/operations/<id>` | GET | Get operation detail |
| `/api/operations/<id>` | PATCH | Update operation status |
| `/api/organizations` | GET | List network organizations |
| `/api/organizations` | POST | Register organization |
| `/api/organizations/<id>` | GET | Get org profile |
| `/api/organizations/<id>` | PATCH | Update org info |
| `/api/notifications` | GET | Get user notifications |
| `/api/notifications/<id>/read` | POST | Mark notification read |
| `/api/activity` | GET | Get activity feed (filterable) |
| `/api/ai-coordinator/analysis` | GET | Get AI coordinator analysis |
| `/api/ai-coordinator/matches` | GET | Get proposed matches |
| `/api/ai-coordinator/gaps` | GET | Get coordination gaps |

---

## 21. Proposed Frontend Changes

### 21.1 Framework & Stack

**Keep existing stack:**
- React 19 + Vite 8
- React Router DOM 7
- Leaflet + react-leaflet
- Tailwind CSS 4
- Lucide React icons
- Recharts (for charts when needed)

**Add (minimal):**
- `date-fns` (already installed) for date formatting
- No new UI framework needed — Tailwind handles all styling

### 21.2 New Routes

```jsx
<Routes>
  <Route path="/" element={<DashboardPage />} />
  <Route path="/map" element={<FullMapPage />} />
  <Route path="/needs" element={<NeedsPage />} />
  <Route path="/needs/:id" element={<NeedDetailPage />} />
  <Route path="/operations" element={<OperationsPage />} />
  <Route path="/operations/:id" element={<OperationDetailPage />} />
  <Route path="/organizations" element={<OrganizationsPage />} />
  <Route path="/organizations/:id" element={<OrgProfilePage />} />
  <Route path="/field-intelligence" element={<FieldIntelligencePage />} />
  <Route path="/ai-coordinator" element={<AICoordinatorPage />} />
  <Route path="/settings" element={<SettingsPage />} />
</Routes>
```

### 21.3 New Components

| Component | Purpose | Reuses |
|-----------|---------|--------|
| `DashboardPage` (redesigned) | Shared operational picture | Existing dashboard patterns |
| `FullMapPage` | Full-screen operational map | `SituationMap.jsx` extended |
| `NeedsPage` | Need list with filters | New |
| `NeedDetailPanel` | Full need workflow | New (follows existing card patterns) |
| `ResourceOfferCard` | Individual offer display | New |
| `OperationsPage` | Operation list | New |
| `OperationDetailPanel` | Operation management | New |
| `OrganizationsPage` | Org list | New |
| `OrgProfilePanel` | Org detail view | New |
| `AICoordinatorPage` | AI analysis dashboard | New (follows `StagedReveal` patterns) |
| `NotificationCenter` | Notification feed | New (follows existing badge patterns) |
| `AlertCard` | AI coordinator alert | New (follows `EvidenceCard` pattern) |
| `MatchProposalCard` | AI match proposal | New |
| `ActivityTimeline` | Activity feed for any entity | New |
| `NeedForm` | Create/edit need | New |
| `OfferForm` | Publish resource offer | New |
| `OperationForm` | Create operation | New |
| `ReportForm` (extended) | Field report with verification | Extended from existing |
| `OverridePanel` (extended) | Override with consequence analysis | Extended from existing `OverrideModal` |

### 21.4 Component Architecture

```
App.jsx (routing)
  │
  ├── Header.jsx (extended: notification bell, user menu)
  │
  ├── DashboardPage.jsx (redesigned)
  │     ├── AlertCard.jsx (AI coordinator alerts)
  │     ├── MiniMap.jsx (overview map)
  │     ├── NeedCard.jsx (urgent needs)
  │     ├── OperationStatusCard.jsx (active operations)
  │     ├── FieldReportCard.jsx (recent reports)
  │     ├── ResourceGapCard.jsx (shortages)
  │     └── DataGapCard.jsx (information gaps)
  │
  ├── FullMapPage.jsx (extended SituationMap)
  │     ├── LayerControl.jsx (extended with new layers)
  │     ├── NeedMarker.jsx
  │     ├── OfferMarker.jsx
  │     ├── OperationMarker.jsx
  │     ├── IncidentMarker.jsx
  │     ├── RouteOverlay.jsx
  │     └── OverrideModal.jsx (extended)
  │
  ├── NeedsPage.jsx
  │     ├── NeedFilters.jsx
  │     ├── NeedList.jsx
  │     └── NeedDetailPanel.jsx
  │
  ├── OperationsPage.jsx
  │     ├── OperationList.jsx
  │     └── OperationDetailPanel.jsx
  │
  ├── OrganizationsPage.jsx
  │     ├── OrgList.jsx
  │     └── OrgProfilePanel.jsx
  │
  ├── AICoordinatorPage.jsx
  │     ├── CoordinationGapList.jsx
  │     ├── MatchProposalList.jsx
  │     ├── ConsequenceAlertList.jsx
  │     └── DataFreshnessPanel.jsx
  │
  ├── FieldIntelligencePage.jsx (extended)
  │     ├── ReportForm.jsx (extended)
  │     ├── ExtractionCard.jsx (existing)
  │     ├── VerificationBadge.jsx
  │     └── VerificationActions.jsx
  │
  └── shared/
        ├── Badge.jsx
        ├── Card.jsx
        ├── Panel.jsx
        ├── Modal.jsx
        ├── ActivityTimeline.jsx
        └── StatusIndicator.jsx
```

---

## 22. Phase 7 Implementation Sequence

### 22.1 Implementation Order

| Phase | What | Depends On | Estimated Effort |
|-------|------|-----------|-----------------|
| **7B** | Database schema: new tables (organizations, needs, offers, incidents, operations, notifications, activity_events) | — | Medium |
| **7C** | Backend models: Need, ResourceOffer, Incident, Operation, Organization, Notification, ActivityEvent | 7B | Medium |
| **7D** | Backend repository: CRUD + queries for all new objects | 7C | Medium |
| **7E** | Backend API: REST endpoints for needs, offers, operations, orgs | 7D | Medium |
| **7F** | Frontend: Dashboard redesign (shared operational picture) | 7E | Large |
| **7G** | Frontend: Full map with new layers (needs, offers, operations, incidents) | 7E | Large |
| **7H** | Frontend: Needs workflow (list, detail, create, respond) | 7E | Medium |
| **7I** | Frontend: Operations workflow (list, detail, create, manage) | 7E | Medium |
| **7J** | Frontend: Organizations (list, profile, publish) | 7E | Medium |
| **7K** | AI Coordinator: Gap detection, match proposals, consequence analysis | 7D, 7E | Large |
| **7L** | AI Coordinator: Frontend panel (alerts, proposals, gaps) | 7K | Medium |
| **7M** | Field report verification workflow | 7E | Small |
| **7N** | Override propagation (consequence analysis) | 7E, 7K | Small |
| **7O** | Notifications: backend + frontend | 7E | Medium |
| **7P** | Permission model: roles, middleware, frontend guards | 7B | Medium |
| **7Q** | NGO workspace: private state, publishing flow | 7B-7E | Large |
| **7R** | Network/NGO Agent architecture | 7K, 7Q | Large |
| **7S** | Integration tests + acceptance tests | All above | Medium |

### 22.2 Dependency Graph

```
7B (schema)
 ├── 7C (models)
 │    ├── 7D (repository)
 │    │    ├── 7E (API)
 │    │    │    ├── 7F (Dashboard)
 │    │    │    ├── 7G (Map layers)
 │    │    │    ├── 7H (Needs UI)
 │    │    │    ├── 7I (Operations UI)
 │    │    │    ├── 7J (Organizations UI)
 │    │    │    ├── 7K (AI Coordinator logic)
 │    │    │    │    ├── 7L (AI Coordinator UI)
 │    │    │    │    └── 7N (Override propagation)
 │    │    │    ├── 7M (Field report verification)
 │    │    │    └── 7O (Notifications)
 │    │    └── 7P (Permissions)
 │    └── 7Q (NGO workspace)
 │         └── 7R (Agent architecture)
 └── 7S (Tests — runs throughout)
```

---

## 23. What Is Explicitly Deferred

| Feature | Reason | Phase |
|---------|--------|-------|
| Autonomous AI matching | Too risky without human oversight | Future (8+) |
| Real-time WebSocket updates | Complexity; polling is sufficient for MVP | Future (8+) |
| User authentication system | Simplified for initial deployment | 7P (minimal) |
| Email/SMS notifications | In-app notifications sufficient initially | Future (8+) |
| Mobile app | Web-first, responsive design | Future (8+) |
| External API integrations | KoboToolbox already partially integrated | Future |
| Multi-language support | English first | Future |
| Advanced analytics/dashboard | Recharts available but not priority | Future |
| User avatars/profiles | Nice-to-have, not essential | Future |
| Audit log export | Activity events stored, export deferred | Future |
| Complex RBAC | Simple role model sufficient initially | 7P |
| Peer-to-peer worker communication | Through Main Agent only | By design |

---

## Appendix A: Existing File Inventory (Phase 7A inspection)

### Frontend Files
| File | Purpose | Phase 7 Impact |
|------|---------|----------------|
| `frontend/src/App.jsx` | Routing + DashboardPage | **Redesign** |
| `frontend/src/components/Header.jsx` | Navigation bar | **Extend** (notifications, user menu) |
| `frontend/src/components/SituationMap.jsx` | Leaflet map with layers | **Extend** (new layers) |
| `frontend/src/components/OperationalAnswer.jsx` | PDC score display | Reuse in dashboard |
| `frontend/src/components/EvidencePanel.jsx` | Evidence cards | Reuse in dashboard + need detail |
| `frontend/src/components/EvidenceCard.jsx` | Individual evidence card | Reuse |
| `frontend/src/components/QueryInput.jsx` | Free-text query input | Reuse in AI coordinator |
| `frontend/src/components/StagedReveal.jsx` | Agent orchestration trace | Reuse in AI coordinator |
| `frontend/src/components/LocationSelector.jsx` | Location dropdown | Reuse |
| `frontend/src/components/DataGapsPanel.jsx` | Data gaps display | Reuse in dashboard |
| `frontend/src/components/FieldIntelligencePage.jsx` | Field report intake | **Extend** (verification) |
| `frontend/src/lib/utils.js` | Shared utilities | Reuse |

### Backend Files
| File | Purpose | Phase 7 Impact |
|------|---------|----------------|
| `agent/api.py` | Flask API | **Extend** with new endpoints |
| `agent/planner.py` | Operational planner | **Integrate** with shared needs |
| `agent/assessment.py` | Location assessment | Reuse |
| `agent/config.py` | Configuration | Extend with auth config |
| `agent/overrides.py` | Override system | **Extend** with org attribution |
| `agent/community_reports.py` | Field reports | **Extend** with org attribution |
| `agent/data_loader.py` | Data loading | Reuse |
| `agent/data/models.py` | Data models | **Extend** with new models |
| `agent/data/repository.py` | Repository interface | **Extend** with new queries |
| `agent/data/postgres_repository.py` | PostgreSQL implementation | **Extend** |
| `agent/data/schema.py` | Database schema | **Extend** with new tables |
| `agent/tools/flood_tool.py` | Flood intelligence | Reuse |
| `agent/tools/exposure_tool.py` | Building exposure | Reuse |
| `agent/tools/accessibility_tool.py` | Medical accessibility | Reuse |
| `agent/tools/road_status_tool.py` | Road status | Reuse |
| `agent/tools/routing_tool.py` | Routing | Reuse |
| `agent/tools/allocation_tool.py` | Priority/allocation | Reuse |
| `agent/tools/field_intelligence_tool.py` | Report extraction | Reuse |
| `agent/tools/query_parser_tool.py` | Query parsing | Reuse |
| `agent/agents/coordinator_agent.py` | Coordinator agent | **Extend** → Network Main Agent |
| `agent/agents/flood_assessment_agent.py` | Flood agent | Reuse |
| `agent/agents/accessibility_agent.py` | Accessibility agent | Reuse |
| `agent/agents/allocation_agent.py` | Allocation agent | Reuse |
| `agent/agents/supply_matching_agent.py` | Supply matching agent | Reuse |

---

## Appendix B: Answer to Acceptance Questions

### 1. Can the existing ReliefOS application evolve into a shared multi-organization workspace without replacing the existing planner?

**YES.** The existing planner (`agent/planner.py`) is already district-agnostic and tool-based. It can be extended to:
- Query shared needs instead of (or in addition to) raw location assessments
- Match needs to resource offers
- Generate coordination gap analysis
- Surface AI proposals

The planner is orchestration — the new shared workspace provides more objects to orchestrate.

### 2. Can Network and NGO Main Agents use the existing repository/tool architecture?

**YES.** The existing repository (`agent/data/repository.py`) and tools (`agent/tools/`) provide the foundation. New tables (needs, offers, operations, orgs) extend the repository. New agent classes extend the existing agent pattern (`agent/agents/`). The existing FloodSnapshot, FieldReport, and Override models are directly reused.

### 3. What is the minimum new backend state required?

- **7 new tables**: organizations, organization_users, network_users, needs, resource_offers, incidents, operations, notifications, activity_events
- **7 new models**: Need, ResourceOffer, Incident, Operation, Organization, NetworkUser, Notification, ActivityEvent
- **~20 new API endpoints**: CRUD for needs, offers, operations, orgs, notifications, activity
- **AI coordinator logic**: gap detection, match proposals, consequence analysis
- **Permissions middleware**: role-based access checks

### 4. What is the minimum new UI required?

- **Dashboard redesign**: shared operational picture with alert cards, need cards, operation status, field reports, resource gaps
- **Map extension**: 4 new layers (needs, offers, operations, incidents)
- **Needs page**: list + detail + create/respond workflow
- **Operations page**: list + detail + create/manage workflow
- **Organizations page**: list + profile + publish workflow
- **AI Coordinator page**: gaps, proposals, consequences
- **Notification center**: bell icon + feed
- **Header extension**: notifications, user menu

---

*End of Phase 7A Design Document.*
