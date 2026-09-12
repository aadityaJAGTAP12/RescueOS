# ReliefOS Architecture

## System Architecture Diagram

```mermaid
flowchart TB
    subgraph WORLD["External World"]
        GIS["Disaster / GIS sources<br/>Sentinel-1 flood polygons · OpenStreetMap · OSRM"]
        FIELD["Field data<br/>free-text observations · community reports"]
        ORGDATA["NGO / organization data<br/>resources · teams · missions"]
    end

    subgraph INGEST["Data / Ingestion Layer"]
        ING["Ingestion & migration<br/>scripts/ingest · agent/data/migration"]
    end

    subgraph STATE["ReliefOS Operational State"]
        PG[("PostgreSQL + PostGIS<br/>districts · settlements · flood_snapshots · roads · bridges<br/>medical_facilities · needs · resource_offers · operations<br/>agent_events (outbox) · coordination_proposals · audit_logs")]
    end

    subgraph NMA["Network Main Agent (custom orchestration)"]
        N1["Situation Worker"]
        N2["Exposure Worker"]
        N3["Medical Worker"]
        N4["Logistics Worker"]
        N5["Access Worker"]
        N6["Field Worker"]
        N7["Coordination Worker"]
        N8["Evidence Worker"]
    end

    subgraph SHARED["Shared Operational State (public)"]
        SH["needs · published offers · operations<br/>activity events · notifications · findings"]
    end

    subgraph NGO["NGO Main Agents (custom orchestration, per org)"]
        O1["Inventory Worker"]
        O2["Team Worker"]
        O3["Mission Worker"]
        O4["Logistics Worker"]
        O5["Field Worker"]
        PRIV[("Private org state<br/>resources · teams · missions")]
    end

    subgraph HITL["Human-in-the-Loop Boundary"]
        APPROVE["Human approval<br/>publish offer · confirm match · create operation"]
    end

    subgraph ACTION["Consequential Action"]
        OFFER["Public Offer / Operation<br/>on shared state"]
    end

    GIS --> ING
    FIELD --> ING
    ORGDATA --> PRIV
    ING --> PG

    PG --> NMA
    N1 --> N8
    NMA --> SH

    SH --> NGO
    NGO -->|"evaluate proposal<br/>against private state"| HITL
    NMA -->|"coordination proposal"| NGO
    HITL --> OFFER
    OFFER --> PG

    subgraph STRANDS["Strands Agents — bounded reasoning layer"]
        QP["Query parsing agent"]
        FI["Field intelligence<br/>extraction agent"]
        CO["Coordinator agent<br/>+ specialist agent tools"]
        JN["Bounded need/offer judgment"]
    end

    FIELD -.->|"structure & verify"| FI
    WORLD -.->|"free-text queries"| QP
    SH -.->|"synthesize findings"| CO
    NGO -.->|"advisory interpretation (2s bound)"| JN
```

## Two Boundaries, One System

ReliefOS is one system with two clearly separated planes:

```text
                RELIEFOS
                   │
        ┌──────────┴──────────┐
        │                     │
 Deterministic Runtime    Strands Reasoning
        │                     │
 Event routing             Query parsing
 Outbox                    Field extraction
 Persistence               Coordinator
 HITL                      Specialist reasoning
 Privacy                   Bounded judgment
        │                     │
        └──────────┬──────────┘
                   │
             Operational State
```

## Architecture Explanation

**Data flow.** External sources (Sentinel-1-derived flood polygons, OpenStreetMap infrastructure, field reports, organizational data) enter through the ingestion layer into PostgreSQL + PostGIS, which is the single authoritative operational state. Spatial queries (point-in-polygon, intersects, radius) run database-side on GiST-indexed geometries.

**Deterministic runtime (custom ReliefOS architecture).** Domain events (`AgentEvent`) are persisted to a transactional outbox and dispatched by a deterministic router — a static table maps event types to the specialist domains that should process them; no LLM sits in the control loop. The **Network Main Agent** delegates to specialist workers with failure isolation (a failing worker produces an explicit data-gap finding, never a fabricated one). Idempotency, stale-claim recovery, and replay are built in. Agent contracts (`AgentFinding` with provenance, severity, confidence, evidence, uncertainty, data gaps) are ReliefOS-defined.

**Strands reasoning layer.** Strands Agents is used for bounded reasoning tasks: parsing free-text coordinator queries into structured intent, extracting structured fields from raw field observations, coordinator/specialist synthesis over pre-gathered evidence, and a time-bounded advisory need/offer judgment. All LLM output passes deterministic guardrails (fabricated-number detection, controlled vocabularies, preserved raw source), and the deterministic path keeps working when the LLM is unavailable. Strands provides the bounded reasoning layer **inside** the deterministic operational architecture — the orchestration hierarchy, outbox, persistence, HITL, and privacy boundaries are custom application architecture.

**Multi-organization privacy.** Organization Main Agents reason over `PrivateOrganizationContext` (inventory, teams, missions — never visible to the network) plus `SharedNetworkContext` (public needs, offers, operations). Network-facing routes serialize only sanitized public projections. There is no uncontrolled worker-to-worker communication: `Worker → Main Agent → shared operational object → other Main Agent`.

**Human-in-the-loop.** Every consequential action — publishing an offer, confirming a match, creating an operation — transitions through an explicit approval gate (`PROPOSED → PENDING_ORG_REVIEW → ORG_RECOMMENDED → PENDING_HUMAN_APPROVAL → PUBLISHED`), is performed by a human through the API, and is recorded in the audit log. Agents propose; humans dispose.
