# ReliefOS Phase 7B — Map-First Operational Workspace: UX Architecture & Design Specification

> **Status:** Design Document — Architecture & UX Specification  
> **Date:** 2026-08-30  
> **Constraint:** DESIGN → DOCUMENT → STOP. No code changes.  
> **Replaces:** Phase 7A §8 (UI Information Architecture) UX model  
> **Preserves:** Phase 7A §1-§7, §10-§23 (data model, backend, schema, implementation sequence)

---

## Table of Contents

1. [Design Philosophy](#1-design-philosophy)
2. [Reference Implementation Analysis](#2-reference-implementation-analysis)
3. [ReliefOS Workspace Architecture](#3-reliefos-workspace-architecture)
4. [Layout Model](#4-layout-model)
5. [Map-First Interaction Model](#5-map-first-interaction-model)
6. [Layer System](#6-layer-system)
7. [Contextual Panel System](#7-contextual-panel-system)
8. [Activity Stream](#8-activity-stream)
9. [AI Coordinator Panel](#9-ai-coordinator-panel)
10. [Need Workflow — Map-First](#10-need-workflow--map-first)
11. [Resource Offer Workflow — Map-First](#11-resource-offer-workflow--map-first)
12. [Operation Workflow — Map-First](#12-operation-workflow--map-first)
13. [Community Report Workflow — Map-First](#13-community-report-workflow--map-first)
14. [Override Workflow — Map-First](#14-override-workflow--map-first)
15. [Notification Model](#15-notification-model)
16. [NGO Private Workspace](#16-ngo-private-workspace)
17. [Component Hierarchy](#17-component-hierarchy)
18. [State Model](#18-state-model)
19. [Route Model](#19-route-model)
20. [Mapping Existing Features to the Workspace](#20-mapping-existing-features-to-the-workspace)
21. [Component Reuse & Redesign Inventory](#21-component-reuse--redesign-inventory)
22. [Responsive Behavior](#22-responsive-behavior)
23. [Future Extensibility](#23-future-extensibility)

---

## 1. Design Philosophy

### 1.1 The Shift

Phase 7A proposed a conventional multi-page UI with 7+ separate routes (Dashboard, Map, Needs, Operations, Organizations, Field Intelligence, AI Coordinator). This is a **CRUD application** pattern — users navigate between disconnected pages to piece together situational awareness.

**Phase 7B replaces this with a map-first operational workspace.**

The core insight from World Monitor and OSIRIS: when the primary task is understanding a spatial situation, the map IS the application. Everything else is a contextual overlay, a slide-out panel, or a compact status indicator that lives around the map.

### 1.2 Design Principles

| # | Principle | Implication |
|---|-----------|-------------|
| 1 | **Map is the canvas** | The map occupies the full viewport. All data is spatially expressed on it. |
| 2 | **No page navigation for core tasks** | Needs, offers, operations, reports, and overrides are all accessible FROM the map without leaving it. |
| 3 | **Contextual, not categorical** | Users don't browse "all needs" — they see needs relevant to the map region they're looking at. |
| 4 | **Layer-first architecture** | Data types are layers, not pages. Users toggle layers to compose their operational picture. |
| 5 | **Panels, not pages** | Detailed inspection happens in slide-out panels that overlay the map, not on separate routes. |
| 6 | **Activity as ambient awareness** | A compact activity stream shows what's happening without requiring navigation. |
| 7 | **AI is a co-pilot, not a destination** | AI recommendations appear contextually on the map and in panels, not on a separate page. |
| 8 | **Progressive disclosure** | The workspace starts simple (map + key layers) and reveals complexity on demand. |
| 9 | **Spatial reasoning first** | Every operational object (need, offer, operation, report) has a location and is visible on the map. |
| 10 | **One connected workspace** | There is ONE primary workspace. The NGO private workspace is a separate, clearly-delineated view. |

### 1.3 What We Are NOT Building

- A dashboard with cards arranged in a grid (that's the Phase 7A model)
- A series of CRUD list pages (Needs page, Operations page, Organizations page)
- A chatbot interface as the primary interaction
- A multi-page wizard for any core workflow
- A mobile-first design (web-first, responsive)

### 1.4 What We ARE Building

- A single operational canvas where the map is the primary surface
- A left-side layer rail that lets users compose their view
- Contextual right-side panels that appear when inspecting objects
- An activity stream that shows what's happening across the network
- An AI coordinator that surfaces insights on the map and in panels
- Inline creation flows (create a need, submit a report, offer resources) without leaving the map

---

## 2. Reference Implementation Analysis

### 2.1 World Monitor (koala73/worldmonitor)

**Information Architecture:**
- Single-page application with a central 3D globe/flat map
- Left sidebar: toggleable data layers (military flights, naval vessels, satellites, earthquakes, fires, cyber, disease, radiation, etc.)
- Top bar: search, variant selector, date range
- Right panel: contextual intelligence synthesis (AI briefs, country analysis)
- Bottom bar: market data ticker, live feed
- Keyboard shortcuts (Cmd+K command palette) for power users
- Layer toggle is the primary interaction — users compose their view by enabling/disabling data streams

**Key Patterns for ReliefOS:**
- Layer catalog as the primary navigation (not page navigation)
- The map fills the viewport — panels overlay it
- AI synthesis appears in contextual panels, not on a separate page
- Activity feeds are ambient (ticker, side panel), not destinations
- Progressive loading — data fetched on-demand when layers are activated
- Viewport-aware — only loads relevant data for the visible region

### 2.2 OSIRIS (simplifaisoul/osiris)

**Information Architecture:**
- Single-page application with MapLibre GL (WebGL) as the central canvas
- Left sidebar: 16 toggleable intelligence layers with real-time entity counts
- Right side: HUD panels for detailed inspection (flight details, CCTV feeds, earthquake data)
- Top bar: domain tabs (Aviation, Maritime, Seismic, Conflict, etc.)
- Keyboard shortcuts for layer toggles (F = flights, E = earthquakes, S = satellites)
- RECON toolkit: contextual tools that appear when inspecting specific objects
- GPU-accelerated rendering for thousands of concurrent entities
- Progressive loading with viewport-aware data fetching

**Key Patterns for ReliefOS:**
- Layer count badges show how many entities are in each layer
- Domain tabs provide quick filtering without leaving the map
- Contextual tool panels (RECON) appear when clicking map objects
- Keyboard shortcuts for power users
- Layer toggling is instant with visual feedback
- Entity inspection happens in slide-out panels, not page navigation

### 2.3 Adapted Principles for ReliefOS

| World Monitor/OSIRIS Pattern | ReliefOS Adaptation |
|------------------------------|---------------------|
| Layer catalog sidebar | Left-side layer rail with disaster-specific layers |
| GPU-accelerated map (MapLibre/deck.gl) | Keep Leaflet for now; upgrade path to MapLibre is available |
| HUD panels for entity inspection | Right-side contextual panels for need/offer/operation detail |
| AI briefs in sidebar | AI Coordinator panel as a toggleable overlay |
| Domain tabs | Quick-filter chips above the map (All, Floods, Needs, Operations) |
| Keyboard shortcuts | Cmd+K command palette for power users |
| Activity ticker | Bottom-bar activity stream |
| Entity count badges | Layer rail shows entity counts per layer |

---

## 3. ReliefOS Workspace Architecture

### 3.1 The One Workspace

```
┌─────────────────────────────────────────────────────────────────────┐
│                    ReliefOS OPERATIONAL WORKSPACE                    │
│                                                                     │
│  ┌──────┐  ┌──────────────────────────────┐  ┌──────────────────┐  │
│  │ LAYER│  │                              │  │  CONTEXT PANEL   │  │
│  │ RAIL │  │         MAP CANVAS           │  │  (slide-out)     │  │
│  │      │  │                              │  │                  │  │
│  │ ──── │  │   Flood polygons             │  │  Need detail     │  │
│  │ 🌊   │  │   Need markers               │  │  Offer detail    │  │
│  │ 🚨   │  │   Operation markers           │  │  Operation detail│  │
│  │ 🏥   │  │   Field report dots           │  │  Org profile     │  │
│  │ 🛤️   │  │   Medical facilities          │  │  Report detail   │  │
│  │ 🏘️   │  │   Roads + bridges             │  │  AI analysis     │  │
│  │ 📋   │  │   Routes                      │  │                  │  │
│  │ 🤖   │  │   Override indicators          │  │                  │  │
│  │      │  │   Resource offers              │  │                  │  │
│  │      │  │   Organization activity        │  │                  │  │
│  │      │  │                              │  │                  │  │
│  └──────┘  └──────────────────────────────┘  └──────────────────┘  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  ACTIVITY STREAM  │  URGENT NEEDS  │  AI ALERTS  │ STATUS   │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 Spatial Zones

The workspace has four spatial zones:

| Zone | Position | Purpose | Behavior |
|------|----------|---------|----------|
| **Layer Rail** | Left, full height | Compose the operational picture | Always visible, collapsible |
| **Map Canvas** | Center, fills available space | The spatial Common Operating Picture | Always visible, primary interaction surface |
| **Context Panel** | Right, slides in/out | Inspect objects in detail | Hidden by default, appears on map click |
| **Activity Bar** | Bottom, full width | Ambient awareness of what's happening | Always visible, compact, scrollable |

### 3.3 Header

The header is minimal — it does NOT contain page navigation (there are no pages). It contains:

```
┌──────────────────────────────────────────────────────────────────────┐
│  [🛡️ ReliefOS]  [Sivasagar District ▾]  [🔍 Search]  [🔔 3] [👤 ▾] │
└──────────────────────────────────────────────────────────────────────┘
```

- **Logo** — ReliefOS branding
- **District/Region selector** — scopes the map and all data to a region
- **Search** — Cmd+K command palette for quick navigation
- **Notification bell** — with unread count badge
- **User menu** — role, settings, NGO workspace switch

---

## 4. Layout Model

### 4.1 CSS Grid Layout

```
┌──────────────────────────────────────────────────────────────┐
│ Header (sticky, h-14)                                        │
├──────┬──────────────────────────────────┬────────────────────┤
│      │                                  │                    │
│ Left │         Map Canvas               │   Context Panel    │
│ Rail │         (flex: 1)                │   (w-96, slides)   │
│(w-16 │                                  │                    │
│ col- │                                  │                    │
│ lapse│                                  │                    │
│ d:w- │                                  │                    │
│ 72)  │                                  │                    │
│      │                                  │                    │
├──────┴──────────────────────────────────┴────────────────────┤
│ Activity Bar (h-12, scrollable)                              │
└──────────────────────────────────────────────────────────────┘
```

### 4.2 Layout State

```typescript
interface WorkspaceLayout {
  headerVisible: boolean;          // always true
  layerRailCollapsed: boolean;     // false by default
  layerRailWidth: number;          // 64px collapsed, 288px expanded
  contextPanelOpen: boolean;       // false by default
  contextPanelWidth: number;       // 384px
  contextPanelContent: PanelContent | null;
  activityBarVisible: boolean;     // true by default
  activityBarHeight: number;       // 48px
  mapZoom: number;                 // current zoom level
  mapCenter: [number, number];     // [lat, lon]
  activeFilters: FilterState;      // district, urgency, status, org
}
```

### 4.3 Responsive Behavior

| Breakpoint | Layout |
|------------|--------|
| ≥1280px (xl) | Full layout: Layer Rail + Map + Context Panel + Activity Bar |
| ≥1024px (lg) | Layer Rail collapsed, Map + Context Panel + Activity Bar |
| ≥768px (md) | Layer Rail collapsed, Map + Activity Bar, Context Panel as modal overlay |
| <768px (sm) | Mobile: Map fills screen, bottom sheet for layers/panels |

---

## 5. Map-First Interaction Model

### 5.1 Map as Primary Surface

The map is NOT one of many views. It IS the application. Every interaction either:
1. Changes what's visible on the map (layer toggling, filtering)
2. Inspects something on the map (clicking objects)
3. Creates something on the map (submitting reports, creating needs)
4. Gets context about the map (AI insights, activity stream)

### 5.2 Map Interactions

| Interaction | Result | UI Feedback |
|------------|--------|-------------|
| Click flood polygon | Context Panel opens with flood snapshot detail | Panel slides in from right |
| Click need marker | Context Panel opens with full need workflow | Panel shows need status, responders, activity |
| Click operation marker | Context Panel opens with operation detail | Panel shows route, resources, status |
| Click field report dot | Context Panel opens with report detail | Panel shows report, verification state |
| Click medical facility | Context Panel opens with facility status | Panel shows override option, nearest needs |
| Click road/bridge | Context Panel opens with road status | Panel shows override option, affected operations |
| Click resource offer marker | Context Panel opens with offer detail | Panel shows org, resources, status |
| Right-click map | Context menu: "Report issue here" → inline report form | Modal or panel |
| Hover object | Tooltip with summary info | Lightweight tooltip |
| Drag route endpoint | Re-calculate route | Route line updates on map |
| Scroll wheel | Zoom in/out | Map zooms |
| Double-click | Zoom in to clicked point | Map zooms |

### 5.3 Map Cursor Modes

| Mode | Cursor | Trigger | Behavior |
|------|--------|---------|----------|
| **Pan** (default) | Grab/Grapping | Default | Pan the map |
| **Inspect** | Pointer | Click on object | Open context panel for that object |
| **Report** | Crosshair | Right-click → "Report issue" | Click to place report location |
| **Measure** | Crosshair | Toolbar button | Click两点 to measure distance |

### 5.4 Map Object Rendering

Each data type has a distinct visual treatment on the map:

| Object | Visual | Color | Size | Interaction |
|--------|--------|-------|------|-------------|
| Flood polygon | Filled polygon | Cyan (#0891b2), 18% opacity | Full polygon | Click for detail |
| Need (critical) | Pulsing circle | Red (#dc2626) | 28px | Click for panel |
| Need (high) | Circle | Orange (#d97706) | 24px | Click for panel |
| Need (medium) | Circle | Yellow (#eab308) | 20px | Click for panel |
| Need (resolved) | Checkmark circle | Green (#16a34a) | 18px | Click for panel |
| Operation (active) | Diamond | Blue (#2563eb) | 26px | Click for panel |
| Operation (planning) | Diamond (outline) | Blue (#2563eb) | 22px | Click for panel |
| Resource offer | Triangle | Teal (#0d9488) | 20px | Click for panel |
| Field report (unverified) | Square | Indigo (#4f46e5) | 20px | Click for panel |
| Field report (verified) | Square (filled) | Green (#16a34a) | 18px | Click for panel |
| Medical facility | Hospital icon | Cyan (#0891b2) | 30px | Click for panel + override |
| Medical facility (overridden) | Hospital icon | Amber (#f59e0b) | 30px | Click for panel |
| Road (open) | Line | Green (#16a34a) | 2px | Click for status |
| Road (blocked) | Line (dashed) | Red (#dc2626) | 3px | Click for status + override |
| Bridge (open) | Line (thick) | Green (#16a34a) | 3px | Click for status |
| Bridge (blocked) | Line (thick, dashed) | Red (#dc2626) | 4px | Click for status + override |
| Settlement | Dot | Stone (#78716c) | 8px | Click for summary |
| Route | Line | Blue (#2563eb) | 4px | Hover for details |
| Route (flood crossing) | Line | Amber (#d97706) | 5px | Hover for warning |
| AI recommendation | Star | Purple (#7c3aed) | 20px | Click for AI analysis |
| Override indicator | Badge on object | Amber (#f59e0b) | Small badge | Shows override status |

### 5.5 Map Popup vs Context Panel

Two levels of map interaction:

1. **Hover tooltip** — lightweight, shows 1-2 lines of summary (e.g., "Need: Food shortage — CRITICAL")
2. **Click → Context Panel** — full detail in the right-side panel (need workflow, responders, activity timeline, AI recommendations)

The popup is for quick scanning. The panel is for deep inspection.

---

## 6. Layer System

### 6.1 Layer Rail Structure

The left-side layer rail is the primary navigation for composing the operational picture. It is NOT a page list — it is a layer catalog.

```
┌──────────────────────────┐
│  LAYERS                  │
│                          │
│  ── ENVIRONMENT ──────── │
│  [✓] 🌊 Flood Extent    │
│  [✓] 🏘️ Settlements     │
│  [✓] 🛤️ Roads & Bridges │
│  [ ] 🏥 Medical Facilities│
│  [ ] 🏢 Buildings        │
│                          │
│  ── OPERATIONAL ──────── │
│  [✓] 🚨 Needs           │
│  [✓] 🔄 Operations      │
│  [ ] 📦 Resource Offers  │
│  [ ] ⚠️ Incidents        │
│                          │
│  ── INTELLIGENCE ─────── │
│  [✓] 📋 Field Reports   │
│  [✓] 🛡️ Overrides       │
│  [ ] 🤖 AI Insights     │
│                          │
│  ── FILTERS ──────────── │
│  District: [All ▾]       │
│  Urgency: [All ▾]        │
│  Status: [All ▾]         │
│  Time: [Last 24h ▾]      │
│                          │
│  ── QUICK ACTIONS ────── │
│  [+ Report Issue]        │
│  [+ Create Need]         │
│  [+ Offer Resource]      │
└──────────────────────────┘
```

### 6.2 Layer Configuration

Each layer has:

```typescript
interface LayerConfig {
  id: string;                    // unique identifier
  group: 'environment' | 'operational' | 'intelligence';
  label: string;                 // display name
  icon: string;                  // Lucide icon name
  defaultVisible: boolean;       // shown by default
  entityCount: number | null;    // live count of entities on map
  color: string;                 // primary color for this layer
  dataSource: string;            // API endpoint or data source
  minZoom: number;               // minimum zoom to show this layer
  maxZoom: number;               // maximum zoom to show this layer
  viewportAware: boolean;        // only load data for visible region
}
```

### 6.3 Layer Toggle Behavior

| Action | Result |
|--------|--------|
| Toggle layer ON | Fetch data for current viewport, render on map, show entity count |
| Toggle layer OFF | Remove from map, hide entity count |
| Click layer label | Toggle ON/OFF |
| Click layer icon | Open layer settings (opacity, style) |
| Right-click layer | Quick actions (zoom to all entities, export data) |

### 6.4 Layer Entity Counts

Inspired by OSIRIS, each layer shows a live count of visible entities:

```
[✓] 🚨 Needs           (4)
[✓] 🔄 Operations      (2)
[ ] 📦 Resource Offers  (1)
```

The count updates when:
- Data is fetched
- Filters change
- Map viewport changes (for viewport-aware layers)
- New data arrives (polling or manual refresh)

### 6.5 Filter System

Filters are scoped to the current map view and apply across all layers:

| Filter | Options | Effect |
|--------|---------|--------|
| District | All, Sivasagar, Jorhat, Golaghat, Charaideo, ... | Restricts all data to selected district |
| Urgency | All, Critical, High, Medium, Low | Filters needs/incidents by urgency |
| Status | All, Open, In Progress, Resolved | Filters needs/operations by status |
| Time Range | Last 6h, 24h, 7d, 30d, All | Filters by creation/observation time |
| Organization | All, [specific org] | Filters by contributing organization |

---

## 7. Contextual Panel System

### 7.1 Panel Architecture

When a user clicks a map object, a Context Panel slides in from the right. This replaces the Phase 7A model of separate detail pages.

```
┌──────────────────────────────────────────────────────────────────┐
│  MAP CANVAS                              │  CONTEXT PANEL       │
│                                          │  ┌────────────────┐  │
│    [flood polygon]                       │  │ ← Back to map  │  │
│         [need marker ◉] ← click ────────│  │                │  │
│              [operation ◆]               │  │ Need #1042     │  │
│                                          │  │ Food — Jorhat  │  │
│                                          │  │ Status: OPEN   │  │
│                                          │  │ Urgency: CRIT  │  │
│                                          │  │                │  │
│                                          │  │ Resources:     │  │
│                                          │  │ • Food ×2000   │  │
│                                          │  │ • Water ×500   │  │
│                                          │  │                │  │
│                                          │  │ Responders:    │  │
│                                          │  │ (none yet)     │  │
│                                          │  │                │  │
│                                          │  │ AI: "Org-B has │  │
│                                          │  │ food kits..."  │  │
│                                          │  │                │  │
│                                          │  │ Activity:      │  │
│                                          │  │ • 2h ago:      │  │
│                                          │  │   Created      │  │
│                                          │  │                │  │
│                                          │  │ [Join Response]│  │
│                                          │  │ [Offer Resource]│  │
│                                          │  └────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

### 7.2 Panel Types

| Panel Type | Trigger | Content |
|------------|---------|---------|
| **NeedDetailPanel** | Click need marker | Full need workflow: status, urgency, resources, responders, AI matches, activity timeline, join/offer actions |
| **OperationDetailPanel** | Click operation marker | Operation plan: status, lead org, participants, route, resources, activity timeline |
| **OfferDetailPanel** | Click offer marker | Resource offer: org, type, quantity, status, linked needs |
| **OrgProfilePanel** | Click org badge on map or panel | Org profile: capabilities, published offers, active operations |
| **FieldReportPanel** | Click field report dot | Report detail: raw text, extracted fields, verification state, actions |
| **FacilityDetailPanel** | Click medical facility | Facility status: operational/overridden, nearest needs, override action |
| **RoadDetailPanel** | Click road/bridge | Road status: open/blocked, override action, affected operations |
| **FloodDetailPanel** | Click flood polygon | Flood snapshot: date, source, polygon count, affected buildings |
| **AIAnalysisPanel** | Click AI insight star | AI analysis: recommendation, evidence chain, proposed actions |
| **CreateNeedPanel** | Click "+ Create Need" in layer rail or right-click | Inline need creation form |
| **CreateReportPanel** | Right-click map → "Report issue" | Inline field report form |
| **OfferResourcePanel** | Click "+ Offer Resource" in layer rail | Inline resource offer form |

### 7.3 Panel Interaction Model

| Action | Result |
|--------|--------|
| Click map object | Panel slides in from right, replacing any existing panel |
| Click "← Back to map" | Panel slides out, returns to full map |
| Click another map object | Current panel replaced by new panel |
| Press Escape | Panel closes |
| Scroll panel | Panel scrolls independently of map |
| Click action button in panel | Triggers workflow (e.g., "Join Response" creates response) |
| Panel shows form | Form submits inline, panel updates with result |

### 7.4 Panel Header Pattern

Every panel follows a consistent header:

```
┌────────────────────────────────────┐
│  ← [icon] [Title]        [× close]│
│  [Status Badge] [Urgency Badge]   │
├────────────────────────────────────┤
│  [Panel body - scrollable]         │
│                                    │
├────────────────────────────────────┤
│  [Action buttons]                  │
└────────────────────────────────────┘
```

---

## 8. Activity Stream

### 8.1 Activity Bar Position

The activity bar sits at the bottom of the workspace, always visible. It provides ambient awareness of what's happening across the network without requiring navigation.

### 8.2 Activity Bar Layout

```
┌──────────────────────────────────────────────────────────────────────┐
│  📋 2m ago  "Road blocked near Demow" — community report            │
│  🚨 5m ago  NEW: Food shortage need — Jorhat (CRITICAL)             │
│  🤖 8m ago  AI: "Two orgs responding to same need while..."         │
│  🔄 12m ago Operation "Rescue Op Jorhat" → ACTIVE                   │
│  📦 15m ago Org-B published: 500 food kits, Jorhat                  │
│  🛡️ 20m ago Override applied: Bridge X — BLOCKED                    │
└──────────────────────────────────────────────────────────────────────┘
```

### 8.3 Activity Item Structure

```typescript
interface ActivityItem {
  id: string;
  type: 'need_created' | 'need_updated' | 'need_resolved' |
        'offer_published' | 'offer_accepted' | 'offer_withdrawn' |
        'operation_created' | 'operation_updated' | 'operation_completed' |
        'report_submitted' | 'report_verified' |
        'override_applied' | 'override_revoked' |
        'ai_recommendation' | 'ai_gap_detected' |
        'org_joined' | 'org_withdrew';
  timestamp: string;
  actor: string;           // org name or "AI Coordinator" or "Community"
  entity_type: string;     // "need" | "operation" | "offer" | "report" | etc.
  entity_id: string;
  title: string;           // human-readable summary
  detail: string;          // optional additional context
  urgency: 'critical' | 'high' | 'medium' | 'low' | null;
}
```

### 8.4 Activity Bar Behavior

| Feature | Behavior |
|---------|----------|
| Auto-scroll | New items appear at left, stream scrolls left |
| Click item | Opens Context Panel for that entity on the map |
| Hover item | Shows tooltip with full detail |
| Filter | Click activity type icons to filter (needs, ops, reports, AI) |
| Expand | Click expand button to see full activity log in a panel |
| Max items | Shows last 20 items; "View all" link for full history |

---

## 9. AI Coordinator Panel

### 9.1 AI as Ambient Intelligence

The AI Coordinator is NOT a separate page or a chat box. It is an ambient intelligence layer that:

1. **Surfaces on the map** — AI-detected issues appear as purple star markers
2. **Appears in the activity bar** — AI recommendations show as activity items
3. **In contextual panels** — When inspecting a need/operation, AI shows relevant analysis
4. **In a toggleable overlay** — A dedicated AI panel can be opened from the layer rail

### 9.2 AI Overlay Panel

When the user clicks the AI layer toggle in the layer rail, an AI analysis panel appears as an overlay:

```
┌────────────────────────────────────┐
│  🤖 AI COORDINATOR          [×]   │
├────────────────────────────────────┤
│                                    │
│  ⚠ COORDINATION GAPS (2)          │
│                                    │
│  Need #1042 (Food, Jorhat)        │
│  has 0 responders after 2h.       │
│  → Suggested: Contact Org-B       │
│  [View on Map] [Propose Match]    │
│                                    │
│  Need #1039 (Rescue, Jorhat)      │
│  has 0 responders after 1h.       │
│  → Suggested: Contact Org-A       │
│  [View on Map] [Propose Match]    │
│                                    │
│  ──────────────────────────────── │
│                                    │
│  📋 MATCH PROPOSALS (1)           │
│                                    │
│  Match: Org-B → Need #1042        │
│  Org-B has 500 food kits          │
│  Match quality: HIGH              │
│  [Approve] [Reject] [Details]     │
│                                    │
│  ──────────────────────────────── │
│                                    │
│  ⚠ CONSEQUENCE ALERTS (1)         │
│                                    │
│  Bridge closure affects 2 active  │
│  operations in Golaghat.          │
│  [View Affected] [Alternatives]   │
│                                    │
│  ──────────────────────────────── │
│                                    │
│  ℹ DATA FRESHNESS                 │
│                                    │
│  Sivasagar flood data: 29 days old│
│  Consider updating.               │
│                                    │
└────────────────────────────────────┘
```

### 9.3 AI in Context Panels

When inspecting a need, the Context Panel includes an AI section:

```
┌────────────────────────────────────┐
│  ← Need #1042 — Food Shortage     │
│  Status: OPEN │ Urgency: CRITICAL │
├────────────────────────────────────┤
│  ... need details ...              │
├────────────────────────────────────┤
│  🤖 AI ANALYSIS                    │
│                                    │
│  Possible response chain:          │
│  • Org-B has 500 food kits (2km)  │
│  • Org-C has water purif. (15km)  │
│  • Both within operational range   │
│  • Road access: blocked via NH-37  │
│  • Water route recommended         │
│                                    │
│  [Propose Match] [View Evidence]   │
├────────────────────────────────────┤
│  ... activity timeline ...         │
└────────────────────────────────────┘
```

### 9.4 AI Map Markers

AI-detected issues appear as purple star markers on the map:

- **Coordination gap** — need with no responders
- **Match proposal** — AI suggests org-need pairing
- **Consequence alert** — override/incident affecting operations
- **Data freshness warning** — stale data in critical area

Clicking an AI marker opens the AI Analysis Panel with full evidence chain.

---

## 10. Need Workflow — Map-First

### 10.1 Need Lifecycle (Unchanged from Phase 7A)

```
OPEN → UNDER_REVIEW → RESPONDING → PARTIALLY_RESOLVED → RESOLVED → CLOSED
```

### 10.2 Creating a Need

**From the Layer Rail:**
1. Click "+ Create Need" in the layer rail
2. CreateNeedPanel slides in from right
3. Form fields: type, title, description, location (tap map or type), urgency, requested resources
4. Submit → need appears on map as a new marker
5. Activity bar shows: "NEW: [need title] — [urgency]"

**From the Map (Right-Click):**
1. Right-click map location
2. Context menu: "Create need here"
3. CreateNeedPanel opens with location pre-filled
4. Submit → need appears at clicked location

**From an AI Recommendation:**
1. AI detects unmet need (e.g., from field report analysis)
2. AI star marker appears on map
3. Click marker → AI proposes creating a need
4. User reviews and approves → need created

### 10.3 Responding to a Need

**From the Context Panel:**
1. Click need marker on map
2. NeedDetailPanel opens
3. Panel shows: status, urgency, requested resources, current responders
4. Click "Join Response" → org joins the response
5. Click "Offer Resource" → offer form appears with need context pre-filled
6. Panel updates with new responder

**From the AI Match Proposal:**
1. AI proposes org-need match
2. Match appears in AI overlay panel
3. User clicks "Approve" → operation created, need status updates

### 10.4 Need Map Visualization

| Status | Marker Style | Color |
|--------|-------------|-------|
| OPEN | Solid circle, pulsing | Red (critical) / Orange (high) / Yellow (medium) |
| UNDER_REVIEW | Solid circle | Blue |
| RESPONDING | Circle with dot | Blue |
| PARTIALLY_RESOLVED | Circle with check | Green-Yellow |
| RESOLVED | Checkmark circle | Green |
| CLOSED | Faded checkmark | Gray |

---

## 11. Resource Offer Workflow — Map-First

### 11.1 Creating an Offer

1. Click "+ Offer Resource" in the layer rail
2. OfferResourcePanel slides in
3. Form: resource type, quantity, unit, location, availability window, notes
4. Submit → offer appears on map as a teal triangle marker
5. Activity bar shows: "Org-[X] published: [quantity] [type], [location]"

### 11.2 Viewing Offers

Offers appear on the map when the "Resource Offers" layer is toggled on. Each offer is a teal triangle at the offer's location.

Click an offer marker → OfferDetailPanel shows:
- Organization name and capabilities
- Resource type, quantity, unit
- Availability window
- Status (offered/accepted/deployed)
- Linked needs (if any)
- Action: "Withdraw Offer"

### 11.3 Matching Offers to Needs

The AI Coordination Worker automatically matches offers to open needs. Matches appear:
1. As purple star markers on the map (at the midpoint between offer and need)
2. In the AI overlay panel as match proposals
3. In the need's Context Panel as "Suggested responders"

---

## 12. Operation Workflow — Map-First

### 12.1 Creating an Operation

**From the Need Context Panel:**
1. Click need marker → NeedDetailPanel
2. Click "Create Operation" (available to NGO admins and coordinators)
3. OperationForm appears in panel with need context pre-filled
4. Form: name, type, lead org, participants, route
5. Submit → operation diamond marker appears on map

**From the Layer Rail:**
1. Click quick action (if available for user role)
2. OperationForm slides in

### 12.2 Operation Map Visualization

Operations appear as diamond markers on the map:
- **Planning** — outlined diamond, blue
- **Active** — filled diamond, blue, with route line
- **Paused** — filled diamond, amber
- **Completed** — filled diamond, green
- **Cancelled** — filled diamond, gray

Route lines connect operation origin to destination, showing:
- Blue line for accessible routes
- Amber line for routes crossing flood zones
- Red dashed line for blocked routes

### 12.3 Operation Detail Panel

Click operation marker → OperationDetailPanel:
- Operation name, type, status
- Lead organization
- Participating organizations
- Needs addressed
- Route (shown on map with highlights)
- Resources committed
- Activity timeline
- Actions: Update Status, Add Participant, Pause/Resume

---

## 13. Community Report Workflow — Map-First

### 13.1 Submitting a Report

**From Right-Click:**
1. Right-click map location
2. Context menu: "Report issue here"
3. CreateReportPanel opens with location pre-filled
4. Form: observation text (free text), report type (auto-detected), photo (optional)
5. Submit → report dot appears on map
6. Activity bar shows: "Community report: [summary]"

**From the Layer Rail:**
1. Click "+ Report Issue"
2. If no location context, user must tap map to place report

### 13.2 Report Map Visualization

Reports appear as small square markers:
- **Unverified** — indigo square
- **Verified** — green square
- **Disputed** — amber square with border

### 13.3 Report Verification

1. Click unverified report → FieldReportPanel opens
2. Panel shows: raw text, extracted fields, reporter info
3. Actions: "Verify" | "Dispute" | "Create Need from Report"
4. Verify → report marker turns green, may trigger override or need creation
5. Activity bar shows: "Report verified by [actor]"

---

## 14. Override Workflow — Map-First

### 14.1 Applying an Override

**From Map Object Click:**
1. Click medical facility → FacilityDetailPanel
2. Panel shows current status + "Override Status" button
3. Click → OverrideModal opens (existing component, extended)
4. Select new status, provide reason
5. Apply → facility marker changes color, override indicator appears

**From Road/Bridge Click:**
1. Click road/bridge → RoadDetailPanel
2. Panel shows current status + "Override Status" button
3. Apply override → road line changes color/style

### 14.2 Override Propagation Visualization

When an override is applied:
1. The affected object changes visual state on the map
2. If the override affects operations, affected operation markers get an amber warning badge
3. Activity bar shows: "Override applied: [object] — [new status]"
4. AI may surface a consequence alert in the AI overlay panel

---

## 15. Notification Model

### 15.1 Notification Bell

The header notification bell shows unread count. Clicking it opens a dropdown:

```
┌────────────────────────────────────┐
│  NOTIFICATIONS           [Mark all]│
├────────────────────────────────────┤
│  🚨 CRITICAL: Food shortage need  │
│     has 0 responders (2h)         │
│     [View on Map]                 │
├────────────────────────────────────┤
│  🤖 AI: Proposed match: Org-B →   │
│     Need #1042                    │
│     [Review]                      │
├────────────────────────────────────┤
│  🛡️ Override: Bridge X blocked,   │
│     affects your operation         │
│     [View]                        │
├────────────────────────────────────┤
│  📋 Report verified: "Road        │
│     blocked near Demow"           │
│     [View]                        │
└────────────────────────────────────┘
```

### 15.2 Notification Types (Unchanged from Phase 7A)

| Category | Trigger | Recipients |
|----------|---------|-----------|
| `urgent_need` | New need with urgency=critical | All coordinators + nearby orgs |
| `need_update` | Status change on a need | Orgs responding to that need |
| `resource_offer` | New offer matching an open need | Orgs with open needs |
| `operation_update` | Status change on an operation | Participating orgs |
| `route_change` | Road/bridge override | Orgs with operations in area |
| `field_report` | New unverified report | Coordinators |
| `ai_recommendation` | AI proposes match/gap | Coordinators |
| `override_applied` | Override affects shared state | Orgs with operations in area |

---

## 16. NGO Private Workspace

### 16.1 Separation Model

The NGO private workspace is a **separate view**, not a layer in the shared workspace. It is accessed via the user menu → "NGO Workspace".

```
┌──────────────────────────────────────────────────────────────────────┐
│  Header: [🛡️ ReliefOS NGO] [Org Name] [Switch to Network ▾] [🔔] [👤]│
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────┐  ┌──────────────────────────────────────────────┐  │
│  │ NGO SIDEBAR  │  │  NGO OPERATIONAL MAP                        │  │
│  │             │  │                                              │  │
│  │ 📦 Inventory│  │  Map showing only this org's:               │  │
│  │ 👥 Team     │  │  - Published offers                         │  │
│  │ 🚗 Vehicles │  │  - Active operations                        │  │
│  │ 🎯 Missions │  │  - Team deployments                         │  │
│  │ 📋 Reports  │  │  - Internal staging areas                   │  │
│  │ 🤖 Agent    │  │                                              │  │
│  │             │  │  + Shared network context:                  │  │
│  │ PUBLISH:    │  │  - Open needs (faded)                       │  │
│  │ [Offer →]   │  │  - Other org operations (faded)             │  │
│  │ [Publish →] │  │                                              │  │
│  └─────────────┘  └──────────────────────────────────────────────┘  │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  NGO ACTIVITY: Inventory changes, team assignments, missions │   │
│  └──────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

### 16.2 NGO Sidebar Sections

| Section | Content | Visibility |
|---------|---------|-----------|
| **Inventory** | Full resource list (private) | Org members only |
| **Team** | Staff roster, assignments (private) | Org members only |
| **Vehicles** | Boats, trucks, equipment (private) | Org members only |
| **Missions** | Internal mission plans (private) | Org members only |
| **Reports** | Internal field reports (private until verified) | Org members only |
| **Agent** | NGO Main Agent status and recommendations | Org members only |
| **Publish** | Actions to publish to network | Org admins only |

### 16.3 Publishing Flow

From the NGO sidebar, the user can publish to the shared network:
1. Click "Publish Resource Offer" → offer form
2. Click "Publish Operation" → operation form
3. Click "Publish Capability" → capability selector
4. Click "Request Assistance" → request form

Each publish action creates a shared object visible on the network workspace map.

### 16.4 Private vs Shared Visualization

On the NGO map:
- **Private data** (inventory, team, internal missions) shown with normal styling
- **Shared network data** (open needs, other org operations) shown with reduced opacity (40%)
- **Published data** (this org's published offers/operations) shown with highlight styling

---

## 17. Component Hierarchy

### 17.1 Application Shell

```
App.jsx
├── BrowserRouter
│   ├── Routes
│   │   ├── "/" → NetworkWorkspace (map-first)
│   │   ├── "/ngo" → NGOWorkspace (private)
│   │   └── "/ngo/:orgId" → NGOWorkspace (specific org)
│   └── (no other top-level routes needed)
│
├── NetworkWorkspace.jsx (the ONE workspace)
│   ├── Header.jsx (extended)
│   │   ├── Logo + brand
│   │   ├── RegionSelector (district/region)
│   │   ├── SearchBar (Cmd+K)
│   │   ├── NotificationBell
│   │   └── UserMenu (role, NGO workspace switch)
│   │
│   ├── LayerRail.jsx (left side)
│   │   ├── LayerGroup ("Environment")
│   │   │   ├── LayerToggle (flood)
│   │   │   ├── LayerToggle (settlements)
│   │   │   ├── LayerToggle (roads)
│   │   │   ├── LayerToggle (medical)
│   │   │   └── LayerToggle (buildings)
│   │   ├── LayerGroup ("Operational")
│   │   │   ├── LayerToggle (needs)
│   │   │   ├── LayerToggle (operations)
│   │   │   ├── LayerToggle (offers)
│   │   │   └── LayerToggle (incidents)
│   │   ├── LayerGroup ("Intelligence")
│   │   │   ├── LayerToggle (field reports)
│   │   │   ├── LayerToggle (overrides)
│   │   │   └── LayerToggle (AI insights)
│   │   ├── FilterBar (district, urgency, status, time)
│   │   └── QuickActions (create need, report, offer)
│   │
│   ├── MapCanvas.jsx (center, fills space)
│   │   ├── MapContainer (Leaflet)
│   │   ├── TileLayer
│   │   ├── FloodLayer (GeoJSON polygons)
│   │   ├── SettlementLayer (markers)
│   │   ├── RoadLayer (polylines with status)
│   │   ├── BridgeLayer (polylines with status)
│   │   ├── MedicalFacilityLayer (markers with override state)
│   │   ├── BuildingLayer (markers, clustered)
│   │   ├── NeedLayer (markers by urgency)
│   │   ├── OperationLayer (markers by status + route)
│   │   ├── OfferLayer (markers by type)
│   │   ├── IncidentLayer (markers by severity)
│   │   ├── FieldReportLayer (markers by verification)
│   │   ├── OverrideIndicators (badges on affected objects)
│   │   ├── AILayer (star markers for AI insights)
│   │   ├── RouteLayer (polylines with flood crossing)
│   │   └── FlyToHandler
│   │
│   ├── ContextPanel.jsx (right side, slides in/out)
│   │   ├── PanelHeader (back button, title, close)
│   │   ├── NeedDetailPanel
│   │   ├── OperationDetailPanel
│   │   ├── OfferDetailPanel
│   │   ├── OrgProfilePanel
│   │   ├── FieldReportPanel
│   │   ├── FacilityDetailPanel
│   │   ├── RoadDetailPanel
│   │   ├── FloodDetailPanel
│   │   ├── AIAnalysisPanel
│   │   ├── CreateNeedPanel (inline form)
│   │   ├── CreateReportPanel (inline form)
│   │   └── OfferResourcePanel (inline form)
│   │
│   └── ActivityBar.jsx (bottom)
│       ├── ActivityStream (horizontal scroll)
│       │   └── ActivityItem (compact, clickable)
│       ├── UrgentNeedsStrip (critical needs count)
│       ├── AIAlertsStrip (AI alerts count)
│       └── StatusIndicators (system health)
│
└── NGOWorkspace.jsx (separate workspace)
    ├── Header.jsx (NGO variant)
    ├── NGOSidebar.jsx
    │   ├── InventorySection
    │   ├── TeamSection
    │   ├── VehiclesSection
    │   ├── MissionsSection
    │   ├── ReportsSection
    │   ├── AgentSection
    │   └── PublishSection
    ├── MapCanvas.jsx (NGO-scoped)
    └── ActivityBar.jsx (NGO-scoped)
```

### 17.2 Shared Components

```
shared/
├── Badge.jsx              (status/urgency badges)
├── Card.jsx               (generic card wrapper)
├── Panel.jsx              (slide-out panel container)
├── Modal.jsx              (modal dialog)
├── ActivityTimeline.jsx   (vertical timeline for entity detail)
├── StatusIndicator.jsx    (colored dot + label)
├── MapMarker.jsx          (generic marker with tooltip)
├── EntityCount.jsx        (layer entity count badge)
├── FormField.jsx          (form field wrapper)
├── ConfirmButton.jsx      (action button with confirmation)
├── EmptyState.jsx         (no data placeholder)
└── LoadingSkeleton.jsx    (loading placeholder)
```

---

## 18. State Model

### 18.1 Global Workspace State

```typescript
interface WorkspaceState {
  // Map state
  map: {
    center: [number, number];       // [lat, lon]
    zoom: number;
    bounds: [[number, number], [number, number]];  // [[sw_lat, sw_lon], [ne_lat, ne_lon]]
  };

  // Layer visibility
  layers: {
    flood: boolean;
    settlements: boolean;
    roads: boolean;
    medical: boolean;
    buildings: boolean;
    needs: boolean;
    operations: boolean;
    offers: boolean;
    incidents: boolean;
    fieldReports: boolean;
    overrides: boolean;
    aiInsights: boolean;
  };

  // Filters
  filters: {
    district: string | null;        // null = all
    urgency: string | null;         // null = all
    status: string | null;          // null = all
    timeRange: string | null;       // null = all
    organization: string | null;    // null = all
  };

  // Panel state
  panel: {
    isOpen: boolean;
    type: string | null;            // panel type identifier
    entityId: string | null;        // entity being inspected
    entityData: any | null;         // cached entity data
  };

  // Activity
  activity: {
    items: ActivityItem[];
    unreadCount: number;
  };

  // Notifications
  notifications: {
    items: Notification[];
    unreadCount: number;
  };

  // AI state
  ai: {
    isVisible: boolean;             // AI overlay panel visible
    gaps: AIGap[];
    matches: AIMatch[];
    consequences: AIConsequence[];
  };

  // User context
  user: {
    id: string;
    role: string;                   // 'community_reporter' | 'ngo_user' | etc.
    orgId: string | null;
  };
}
```

### 18.2 Data Fetching Strategy

| Data Type | Fetch Trigger | Refresh Interval | Viewport-Aware |
|-----------|--------------|------------------|----------------|
| Flood polygons | Map load + district filter | 30 min | Yes |
| Roads/bridges | Map load + district filter | 1 hour | Yes |
| Medical facilities | Map load + district filter | 1 hour | Yes |
| Buildings | Map load + district filter | 1 hour | Yes (clustered) |
| Settlements | Map load + district filter | Static | Yes |
| Needs | Map load + filters | 5 min | Yes |
| Operations | Map load + filters | 5 min | Yes |
| Resource offers | Map load + filters | 5 min | Yes |
| Incidents | Map load + filters | 5 min | Yes |
| Field reports | Map load + filters | 5 min | Yes |
| Overrides | Map load | 5 min | No (global) |
| AI insights | Map load + filters | 10 min | Yes |
| Activity stream | Continuous | 30 sec | No (global) |
| Notifications | Continuous | 30 sec | No (global) |

### 18.3 State Management

Use React Context + useReducer for workspace state. No external state management library needed at this scale.

```typescript
// Context providers
<WorkspaceProvider>          // map, layers, filters, panel state
  <DataProvider>             // fetched entity data (needs, ops, etc.)
    <ActivityProvider>       // activity stream + notifications
      <AIProvider>           // AI coordinator state
        <App />
      </AIProvider>
    </ActivityProvider>
  </DataProvider>
</WorkspaceProvider>
```

---

## 19. Route Model

### 19.1 Simplified Routes

The Phase 7A model had 10+ routes. The map-first model has only 2:

| Route | Component | Purpose |
|-------|-----------|---------|
| `/` | `NetworkWorkspace` | The ONE shared operational workspace |
| `/ngo` | `NGOWorkspace` | NGO private workspace |
| `/ngo/:orgId` | `NGOWorkspace` | Specific NGO workspace (admin view) |

That's it. There are no separate pages for Needs, Operations, Organizations, Field Intelligence, or AI Coordinator. All of these are layers and panels within the workspace.

### 19.2 Why Only 2 Routes?

- The map IS the application — no need for separate map pages
- Needs, operations, offers are layers on the map — no need for list pages
- Detailed inspection happens in Context Panels — no need for detail pages
- AI is ambient — no need for a dedicated page
- Field reports are a layer — no need for a separate page
- Organizations are profiles accessible from panels — no need for a list page

### 19.3 Deep Linking

When a user receives a notification or shares a link, the URL encodes:
- Map center and zoom
- Active layers
- Open panel (entity type + ID)
- Active filters

Example: `/?center=26.74,94.21&zoom=12&panel=need:need_jorhat_food_20260729&layers=flood,needs,roads`

---

## 20. Mapping Existing Features to the Workspace

### 20.1 Feature → Workspace Mapping

| Existing Feature | Current Location | Workspace Integration |
|-----------------|-----------------|----------------------|
| Flood intelligence | `agent/tools/flood_tool.py` | Flood Layer on map |
| Building exposure | `agent/tools/exposure_tool.py` | Building Layer + flood detail evidence |
| Medical accessibility | `agent/tools/accessibility_tool.py` | Medical Facility Layer + facility detail panel |
| Road status | `agent/tools/road_status_tool.py` | Road/Bridge Layer with status coloring |
| Routing | `agent/tools/routing_tool.py` | Route Layer on map + operation routes |
| Allocation/PDC | `agent/tools/allocation_tool.py` | AI Coordinator evidence + need priority |
| Field intelligence | `agent/tools/field_intelligence_tool.py` | Field Report Layer + report panel |
| Query parser | `agent/tools/query_parser_tool.py` | Search bar (Cmd+K) + AI Coordinator |
| Operational planner | `agent/planner.py` | AI Coordinator reasoning engine |
| Flood snapshots | `agent/data/models.py` (FloodSnapshot) | Flood Layer data source |
| Field reports | `agent/data/models.py` (FieldReport) | Field Report Layer data source |
| Overrides | `agent/overrides.py` | Override Layer + override indicators |
| District/Settlement | `agent/data/models.py` | Settlement Layer + district filter |
| PostGIS schema | `agent/data/schema.py` | All layer data sources |
| Repository | `agent/data/repository.py` | All data queries |
| API | `agent/api.py` | All frontend data fetching |
| Assessment | `agent/assessment.py` | Need evidence + AI analysis |
| Coordinator Agent | `agent/agents/coordinator_agent.py` | AI Coordinator Panel |
| SituationMap | `frontend/src/components/SituationMap.jsx` | **Extended → MapCanvas.jsx** |
| Dashboard | `frontend/src/App.jsx` (DashboardPage) | **Replaced → NetworkWorkspace.jsx** |
| Field Intelligence | `frontend/src/components/FieldIntelligencePage.jsx` | **Merged → Field Report Layer + Panel** |
| Agent Trace | `frontend/src/components/StagedReveal.jsx` | **Reused → AI Analysis Panel** |
| Evidence Panel | `frontend/src/components/EvidencePanel.jsx` | **Reused → Flood/Need detail panel sections** |
| Evidence Card | `frontend/src/components/EvidenceCard.jsx` | **Reused → Panel content sections** |
| Operational Answer | `frontend/src/components/OperationalAnswer.jsx` | **Reused → Need/Location detail panel** |
| Data Gaps | `frontend/src/components/DataGapsPanel.jsx` | **Reused → AI data freshness section** |
| Query Input | `frontend/src/components/QueryInput.jsx` | **Reused → Search bar + AI panel input** |
| Location Selector | `frontend/src/components/LocationSelector.jsx` | **Reused → District filter in layer rail** |
| Header | `frontend/src/components/Header.jsx` | **Extended → NetworkWorkspace header** |

### 20.2 Data Source → Layer Mapping

| Data Source | API Endpoint | Map Layer | Panel |
|-------------|-------------|-----------|-------|
| Flood GeoJSON | `/api/flood-geojson` | Flood Layer | FloodDetailPanel |
| Buildings (exposed) | `/api/assess` (evidence.exposure) | Building Layer | — |
| Medical facilities | `/api/assess` (evidence.accessibility) | Medical Layer | FacilityDetailPanel |
| Roads | PostGIS `roads` table | Road Layer | RoadDetailPanel |
| Bridges | PostGIS `roads` table (is_bridge) | Bridge Layer | RoadDetailPanel |
| Settlements | PostGIS `settlements` table | Settlement Layer | — |
| Needs | `/api/needs` (new) | Need Layer | NeedDetailPanel |
| Operations | `/api/operations` (new) | Operation Layer | OperationDetailPanel |
| Resource offers | `/api/offers` (new) | Offer Layer | OfferDetailPanel |
| Field reports | `/api/field-intelligence/history` | Report Layer | FieldReportPanel |
| Overrides | `/api/overrides` | Override indicators | FacilityDetailPanel / RoadDetailPanel |
| AI insights | `/api/ai-coordinator/analysis` (new) | AI Layer | AIAnalysisPanel |
| Activity | `/api/activity` (new) | — | ActivityBar |
| Notifications | `/api/notifications` (new) | — | NotificationBell |

---

## 21. Component Reuse & Redesign Inventory

### 21.1 Components to REUSE Directly

| Component | File | Reuse As |
|-----------|------|----------|
| `EvidenceCard` | `EvidenceCard.jsx` | Panel content sections (flood, exposure, accessibility evidence) |
| `EvidencePanel` | `EvidencePanel.jsx` | Need/Flood detail panel evidence section |
| `StagedReveal` | `StagedReveal.jsx` | AI Analysis Panel trace display |
| `DataGapsPanel` | `DataGapsPanel.jsx` | AI data freshness section |
| `QueryInput` | `QueryInput.jsx` | Search bar + AI panel input |
| `LocationSelector` | `LocationSelector.jsx` | District filter in layer rail |
| `OperationalAnswer` | `OperationalAnswer.jsx` | Need/Location detail priority display |
| `OverrideModal` | `SituationMap.jsx` (inline) | Override workflow (move to shared component) |
| `utils.js` | `lib/utils.js` | All shared utilities |

### 21.2 Components to EXTEND

| Component | File | Extension |
|-----------|------|-----------|
| `SituationMap` | `SituationMap.jsx` | → `MapCanvas.jsx`: add need/operation/offer/report layers, right-click menu, object click handlers |
| `Header` | `Header.jsx` | Add notification bell, user menu, region selector, search bar |
| `LayerControl` | `SituationMap.jsx` (inline) | → `LayerRail.jsx`: expand to full left rail with groups, filters, quick actions, entity counts |
| `FieldIntelligencePage` | `FieldIntelligencePage.jsx` | Simplify to just the report submission form (used in CreateReportPanel) |
| `QueryInput` | `QueryInput.jsx` | Add Cmd+K command palette mode |

### 21.3 Components to CREATE

| Component | Purpose | Complexity |
|-----------|---------|-----------|
| `NetworkWorkspace` | The ONE main workspace layout | Large |
| `NGOWorkspace` | NGO private workspace | Large |
| `LayerRail` | Left-side layer catalog | Medium |
| `LayerToggle` | Individual layer toggle with count | Small |
| `LayerGroup` | Grouped layer section | Small |
| `FilterBar` | District/urgency/status/time filters | Medium |
| `MapCanvas` | Full map with all layers | Large |
| `ContextPanel` | Slide-out panel container | Medium |
| `NeedDetailPanel` | Need workflow in panel | Medium |
| `OperationDetailPanel` | Operation detail in panel | Medium |
| `OfferDetailPanel` | Offer detail in panel | Small |
| `OrgProfilePanel` | Org profile in panel | Medium |
| `FieldReportPanel` | Report detail in panel | Small |
| `FacilityDetailPanel` | Facility status + override | Small |
| `RoadDetailPanel` | Road status + override | Small |
| `FloodDetailPanel` | Flood snapshot detail | Small |
| `AIAnalysisPanel` | AI insights overlay | Medium |
| `CreateNeedPanel` | Inline need creation form | Medium |
| `CreateReportPanel` | Inline report submission | Medium |
| `OfferResourcePanel` | Inline offer creation | Medium |
| `ActivityBar` | Bottom activity stream | Medium |
| `ActivityItem` | Individual activity entry | Small |
| `NotificationBell` | Header notification dropdown | Small |
| `SearchPalette` | Cmd+K command palette | Medium |
| `NeedMarker` | Map marker for needs | Small |
| `OperationMarker` | Map marker for operations | Small |
| `OfferMarker` | Map marker for offers | Small |
| `ReportMarker` | Map marker for reports | Small |
| `AIMarker` | Map marker for AI insights | Small |
| `RegionSelector` | District/region dropdown | Small |
| `NGOSidebar` | NGO workspace sidebar | Medium |

---

## 22. Responsive Behavior

### 22.1 Desktop (≥1280px)

Full workspace layout:
- Layer Rail: expanded (288px)
- Map Canvas: fills remaining space
- Context Panel: slides in from right (384px)
- Activity Bar: full width bottom bar (48px)

### 22.2 Laptop (≥1024px, <1280px)

- Layer Rail: collapsed to icons (64px), expands on hover
- Map Canvas: fills remaining space
- Context Panel: slides in from right (384px)
- Activity Bar: full width bottom bar (48px)

### 22.3 Tablet (≥768px, <1024px)

- Layer Rail: collapsed to icons (64px)
- Map Canvas: fills remaining space
- Context Panel: modal overlay (full height, 384px width)
- Activity Bar: reduced height (40px), fewer items

### 22.4 Mobile (<768px)

- Layer Rail: bottom sheet (swipe up to expand)
- Map Canvas: full viewport
- Context Panel: full-screen modal
- Activity Bar: bottom sheet with tap to expand
- Header: simplified (logo, notifications, menu)

---

## 23. Future Extensibility

### 23.1 Map Engine Upgrade Path

The current Leaflet implementation works for the MVP. Future upgrade to MapLibre GL JS would enable:
- WebGL-accelerated rendering for thousands of entities
- Vector tile support for roads/settlements
- 3D terrain visualization
- Better performance with many overlapping layers

This upgrade is architecturally clean because:
- All data fetching is in the `DataProvider` context
- All rendering is in layer components within `MapCanvas`
- The layer toggle system is independent of the map engine

### 23.2 Real-Time Collaboration

The current polling-based model (5-30 second refresh) is sufficient for MVP. Future WebSocket upgrade would enable:
- Live cursor positions of other coordinators
- Real-time entity updates without polling
- Collaborative editing of needs/operations
- Live activity stream

This upgrade is architecturally clean because:
- Activity and notification providers can swap polling for WebSocket subscriptions
- Entity data providers can subscribe to change events
- The UI components don't need to change

### 23.3 Agent Hierarchy

The Network Main Agent and NGO Main Agent architecture from Phase 7A is preserved. The workspace provides:
- AI Coordinator Panel for Network Main Agent output
- NGO Agent Section in NGO Workspace for NGO Main Agent output
- Worker agents communicate through their Main Agent (no peer-to-peer)

### 23.4 District Agnosticism

The workspace is district-agnostic by design:
- District selector in the header scopes all data
- No hardcoded district names in UI components
- All data sources are queried with district_id parameter
- Adding a new district requires only data ingestion, no UI changes

---

## Appendix A: Acceptance Criteria Checklist

| Criterion | Status | How Addressed |
|-----------|--------|---------------|
| The UX is clearly map-first | ✅ | Map occupies full viewport, all data is spatially expressed |
| It feels like a situational-awareness workspace | ✅ | Layer rail + map canvas + contextual panels + activity bar |
| Needs/incidents behave like collaborative operational issues | ✅ | Need workflow with responders, AI matches, activity timeline |
| Community knowledge can modify/override the operational map | ✅ | Field reports + overrides visible on map and in panels |
| Flood + roads + bridges + resources + organizations + needs coexist spatially | ✅ | All are map layers composited on the same canvas |
| AI Coordinator connects information across layers | ✅ | AI layer, AI panel, contextual AI in need/operation panels |
| NGO private state remains private | ✅ | Separate NGO workspace, never auto-published |
| Shared network state is explicitly published | ✅ | Publishing flow in NGO workspace |
| Existing planner/tools remain reusable | ✅ | All existing tools feed into map layers and AI analysis |
| Supports additional districts without district-specific UI logic | ✅ | District selector, no hardcoded district names |
| Supports future real-time without WebSockets now | ✅ | Polling-based refresh, clean upgrade path |

## Appendix B: Interaction Quick Reference

| User Goal | How to Achieve It |
|-----------|-------------------|
| "What's the situation?" | Open ReliefOS → map shows flood extent + needs + operations |
| "Where are the critical needs?" | Toggle Need Layer → red pulsing markers |
| "What's blocking access?" | Toggle Road Layer → red dashed lines for blocked roads |
| "Who's responding to Need X?" | Click need marker → Context Panel shows responders |
| "Create a need" | Layer Rail → "+ Create Need" → form in panel |
| "Report a blocked road" | Right-click map → "Report issue here" → form in panel |
| "Offer resources" | Layer Rail → "+ Offer Resource" → form in panel |
| "What does AI recommend?" | Toggle AI Layer → purple stars + AI panel |
| "What's happening now?" | Activity Bar at bottom → scrollable activity feed |
| "Switch to NGO workspace" | User menu → "NGO Workspace" |
| "Filter to one district" | Layer Rail → District filter dropdown |
| "See all open needs" | Toggle Need Layer → all need markers visible |

---

*End of Phase 7B Design Document.*
