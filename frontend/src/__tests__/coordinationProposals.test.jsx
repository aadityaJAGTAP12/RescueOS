/**
 * Coordination Proposals Frontend Integration Tests
 *
 * Verifies:
 * 1. Workspace Context: proposals state, fetchProposals filtering, CLEAR_ORG_DATA flushing.
 * 2. NeedDetail: Propose coordination workflow, list linked proposals, send-to-org, decline.
 * 3. ProposalDetail: Dossier presentation, public projection, metadata, navigation, actions.
 * 4. OrganizationWorkspace: IncomingProposals tab, AI evaluation trigger, Human-in-the-loop
 *    publication approval with double-click protection, decline.
 * 5. ActivityBar: Navigation on coordination entity events.
 * 6. Privacy boundary: Strict verification that DOM never exposes private NGO data
 *    (private_factors, private_reasoning, private inventory/teams).
 * 7. Identity Seam: Org switching flushes stale proposals and enforces cookie-derived org context.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import React from "react";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { WorkspaceProvider, useWorkspace } from "../lib/workspaceContext";
import { resetOrgContextCache } from "../lib/orgContext";
import ContextPanel from "../components/workspace/ContextPanel";
import OrganizationWorkspace from "../components/workspace/OrganizationWorkspace";
import ActivityBar from "../components/workspace/ActivityBar";

// -------------------------------------------------------------------
// Mock Data
// -------------------------------------------------------------------

const MOCK_ORG_A = {
  id: "org_alpha",
  name: "Alpha Disaster Relief",
  organization_type: "ngo",
  active: true,
};

const MOCK_ORG_B = {
  id: "org_beta",
  name: "Beta Medical Corps",
  organization_type: "ngo",
  active: true,
};

const MOCK_NEED = {
  id: "need_water_001",
  title: "Drinking Water for 500 Families",
  need_type: "water",
  urgency: "critical",
  status: "OPEN",
  district_id: "jorhat",
  location_name: "Jorhat Relief Camp",
  description: "Urgent need for clean drinking water and purification kits.",
  requested_resources: [{ type: "water_purification", quantity: 50, unit: "kits" }],
  created_at: "2026-09-08T00:00:00Z",
  updated_at: "2026-09-08T01:00:00Z",
};

const MOCK_PROPOSAL_PROPOSED = {
  id: "prop_001",
  need_id: "need_water_001",
  organization_id: "org_alpha",
  organization_name: "Alpha Disaster Relief",
  proposal_type: "coordination",
  status: "PROPOSED",
  summary: "Alpha NGO can supply 50 purification kits to Jorhat camp.",
  recommended_action: "Deploy 50 kits via road route NH-37.",
  public_evidence: [
    { type: "satellite", detail: "Road NH-37 clear of major flooding" }
  ],
  network_findings: [
    { type: "network_fit", detail: "Alpha has historical response presence in Jorhat" }
  ],
  constraints: ["Dispatch within 6 hours", "Requires high-clearance truck"],
  uncertainty: ["Possible flash flood warning near bypass"],
  created_at: "2026-09-08T02:00:00Z",
  updated_at: "2026-09-08T02:30:00Z",
  published_offer_id: null,
};

const MOCK_PROPOSAL_RECOMMENDED = {
  id: "prop_002",
  need_id: "need_water_001",
  organization_id: "org_alpha",
  organization_name: "Alpha Disaster Relief",
  proposal_type: "coordination",
  status: "ORG_RECOMMENDED",
  summary: "Evaluation recommended: Alpha inventory has matching water kits.",
  recommended_action: "Approve publication of offer for 50 units.",
  constraints: ["Stock allocated from warehouse Alpha-Central"],
  uncertainty: [],
  created_at: "2026-09-08T02:00:00Z",
  updated_at: "2026-09-08T03:00:00Z",
  published_offer_id: null,
};

const MOCK_PROPOSAL_PUBLISHED = {
  id: "prop_003",
  need_id: "need_water_001",
  organization_id: "org_alpha",
  organization_name: "Alpha Disaster Relief",
  proposal_type: "coordination",
  status: "PUBLISHED",
  summary: "Offer published to network for 50 purification kits.",
  recommended_action: "Await responder dispatch.",
  constraints: [],
  uncertainty: [],
  created_at: "2026-09-08T02:00:00Z",
  updated_at: "2026-09-08T03:15:00Z",
  published_offer_id: "offer_pub_999",
};

// -------------------------------------------------------------------
// Mock Fetch Factory
// -------------------------------------------------------------------

function setupCoordinationFetchMock({
  sessionOrg = "org_alpha",
  proposals = [MOCK_PROPOSAL_PROPOSED],
  organizations = [MOCK_ORG_A, MOCK_ORG_B],
  needs = [MOCK_NEED],
  events = [],
} = {}) {
  let currentProposals = [...proposals];

  const fetchMock = vi.fn(async (url, options = {}) => {
    const u = typeof url === "string" ? url : url.toString();
    const method = options.method || "GET";

    // Session Org endpoint
    if (u === "/api/session/org") {
      if (method === "POST") {
        const body = JSON.parse(options.body || "{}");
        sessionOrg = body.org_id;
        return {
          ok: true,
          json: async () => ({ org_id: sessionOrg, name: sessionOrg }),
        };
      }
      return {
        ok: true,
        json: async () => ({ org_id: sessionOrg, registered: true, organizations }),
      };
    }

    // Network Coordination Proposals: Query
    if (u.startsWith("/api/network/coordination/proposals")) {
      // Check for actions: send-to-org or decline
      const sendMatch = u.match(/\/api\/network\/coordination\/proposals\/([^/]+)\/send-to-org$/);
      if (sendMatch && method === "POST") {
        const propId = sendMatch[1];
        currentProposals = currentProposals.map((p) =>
          p.id === propId ? { ...p, status: "PENDING_ORG_REVIEW" } : p
        );
        const updated = currentProposals.find((p) => p.id === propId);
        return { ok: true, json: async () => ({ proposal: updated }) };
      }

      const declineMatch = u.match(/\/api\/network\/coordination\/proposals\/([^/]+)\/decline$/);
      if (declineMatch && method === "POST") {
        const propId = declineMatch[1];
        currentProposals = currentProposals.map((p) =>
          p.id === propId ? { ...p, status: "DECLINED" } : p
        );
        const updated = currentProposals.find((p) => p.id === propId);
        return { ok: true, json: async () => ({ proposal: updated }) };
      }

      // Query listing with filters
      const parsedUrl = new URL(u, "http://localhost");
      const needFilter = parsedUrl.searchParams.get("need_id");
      const orgFilter = parsedUrl.searchParams.get("organization_id");
      const statusFilter = parsedUrl.searchParams.get("status");

      let filtered = [...currentProposals];
      if (needFilter) filtered = filtered.filter((p) => p.need_id === needFilter);
      if (orgFilter) filtered = filtered.filter((p) => p.organization_id === orgFilter);
      if (statusFilter) filtered = filtered.filter((p) => p.status === statusFilter);

      return {
        ok: true,
        json: async () => ({ proposals: filtered }),
      };
    }

    // Network Coordination Propose: Create Proposal
    if (u === "/api/network/coordination/propose" && method === "POST") {
      const body = JSON.parse(options.body || "{}");
      const newProposal = {
        id: `prop_${Math.random().toString(36).slice(2, 7)}`,
        need_id: body.need?.id || "need_generic",
        organization_id: body.organization_id,
        organization_name: body.organization_name || body.organization_id,
        proposal_type: "coordination",
        status: "PROPOSED",
        summary: `Coordinated response by ${body.organization_name}`,
        constraints: [],
        uncertainty: [],
        public_evidence: [],
        created_at: new Date().toISOString(),
      };
      currentProposals.push(newProposal);
      return {
        ok: true,
        status: 201,
        json: async () => ({ proposal: newProposal, candidates: [] }),
      };
    }

    // NGO Private Agent: Evaluate Coordination
    if (u === "/api/my-org/agent/evaluate-coordination" && method === "POST") {
      const body = JSON.parse(options.body || "{}");
      const proposal = currentProposals.find((p) => p.id === body.proposal_id);
      if (!proposal) {
        return { ok: false, status: 404, json: async () => ({ error: "Proposal not found" }) };
      }
      currentProposals = currentProposals.map((p) =>
        p.id === body.proposal_id ? { ...p, status: "ORG_RECOMMENDED" } : p
      );
      return {
        ok: true,
        json: async () => ({
          status: "evaluated",
          evaluation: {
            decision: "ACCEPT",
            public_summary: "Stock matches need requirement; ready to commit 50 units.",
            resource_assessment: {
              matching_available: 50,
            },
            constraints: ["Vehicle dispatch available at 08:00"],
            // Note: private fields like internal inventory IDs, private reasoning are NOT in public evaluation
          },
        }),
      };
    }

    // NGO Private Agent: Approve Publication (Human in the loop)
    if (u === "/api/my-org/agent/approve-publication" && method === "POST") {
      const body = JSON.parse(options.body || "{}");
      const proposal = currentProposals.find((p) => p.id === body.proposal_id);
      if (!proposal) {
        return { ok: false, status: 404, json: async () => ({ error: "Proposal not found" }) };
      }
      const offerId = `offer_${Math.random().toString(36).slice(2, 8)}`;
      currentProposals = currentProposals.map((p) =>
        p.id === body.proposal_id
          ? { ...p, status: "PUBLISHED", published_offer_id: offerId }
          : p
      );
      return {
        ok: true,
        json: async () => ({
          success: true,
          message: "Offer published to network",
          offer: {
            id: offerId,
            resource_type: "water_purification",
            quantity: 50,
            organization_id: sessionOrg,
          },
        }),
      };
    }

    // My Org Summary
    if (u === "/api/my-org/summary") {
      return {
        ok: true,
        json: async () => ({
          org_id: sessionOrg,
          profile: { id: sessionOrg, name: `${sessionOrg} Name` },
          summary: {
            total_resources: 120,
            available_resources: 80,
            total_teams: 4,
            available_teams: 2,
            active_missions: 1,
            published_offers: 1,
            network_requests: 3,
          },
        }),
      };
    }

    // Standard workspace read endpoints
    if (u.startsWith("/api/needs")) return { ok: true, json: async () => ({ needs }) };
    if (u.startsWith("/api/offers")) return { ok: true, json: async () => ({ offers: [] }) };
    if (u.startsWith("/api/operations")) return { ok: true, json: async () => ({ operations: [] }) };
    if (u.startsWith("/api/districts")) return { ok: true, json: async () => ({ districts: [] }) };
    if (u.startsWith("/api/settlements")) return { ok: true, json: async () => ({ settlements: [] }) };
    if (u.includes("/flood-geojson")) return { ok: true, json: async () => ({ type: "FeatureCollection", features: [] }) };
    if (u.includes("/roads")) return { ok: true, json: async () => ({ roads: [] }) };
    if (u.includes("/bridges")) return { ok: true, json: async () => ({ bridges: [] }) };
    if (u.includes("/medical-facilities")) return { ok: true, json: async () => ({ facilities: [] }) };
    if (u.includes("/field-intelligence/history")) return { ok: true, json: async () => ({ reports: [] }) };
    if (u.includes("/overrides")) return { ok: true, json: async () => ({ overrides: [] }) };
    if (u.includes("/activity")) return { ok: true, json: async () => ({ events }) };
    if (u.includes("/notifications")) return { ok: true, json: async () => ({ notifications: [] }) };
    if (u.includes("/ai-coordinator")) return { ok: true, json: async () => ({ findings: [], summary: { total: 0 } }) };
    if (u.includes("/delta")) return { ok: true, json: async () => ({ summary: {}, directional: {} }) };
    if (u.includes("/flood-snapshots")) return { ok: true, json: async () => ({ snapshots: [] }) };
    if (u.includes("/incidents")) return { ok: true, json: async () => ({ incidents: [] }) };
    if (u.includes("/api/organizations")) return { ok: true, json: async () => ({ organizations }) };
    if (u.includes("/api/evidence/need")) return { ok: true, json: async () => ({ evidence_items: [] }) };

    return { ok: false, status: 404, json: async () => ({}) };
  });

  global.fetch = fetchMock;
  return {
    fetchMock,
    getCurrentProposals: () => currentProposals,
  };
}

// -------------------------------------------------------------------
// Helper Component to control and inspect workspace state in tests
// -------------------------------------------------------------------

function TestController({ onState, panelToOpen }) {
  const ws = useWorkspace();

  React.useEffect(() => {
    if (onState) onState(ws);
  }, [onState, ws.state]);

  React.useEffect(() => {
    if (panelToOpen) {
      ws.openPanel(panelToOpen.type, panelToOpen.entityId, panelToOpen.data);
    }
  }, [panelToOpen]); // eslint-disable-line react-hooks/exhaustive-deps

  return null;
}

// -------------------------------------------------------------------
// Tests
// -------------------------------------------------------------------

describe("Coordination Proposals Frontend Integration (Item #5C)", () => {
  beforeEach(() => {
    document.cookie = "reliefos_org_id=; max-age=0; path=/";
    resetOrgContextCache();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe("Workspace Context Reducer & fetchProposals", () => {
    it("initializes proposals as an empty array and fetches proposals via /api/network/coordination/proposals", async () => {
      const { fetchMock } = setupCoordinationFetchMock({
        proposals: [MOCK_PROPOSAL_PROPOSED],
      });

      let capturedState;
      render(
        <WorkspaceProvider>
          <TestController onState={(ws) => { capturedState = ws.state; }} />
        </WorkspaceProvider>
      );

      await waitFor(() => {
        expect(capturedState?.proposals).toHaveLength(1);
        expect(capturedState.proposals[0].id).toBe("prop_001");
      });

      expect(fetchMock).toHaveBeenCalledWith("/api/network/coordination/proposals");
    });

    it("fetchProposals constructs correct query string when filtering by need_id, organization_id, and status", async () => {
      const { fetchMock } = setupCoordinationFetchMock();
      let capturedWs;
      render(
        <WorkspaceProvider>
          <TestController onState={(ws) => { capturedWs = ws; }} />
        </WorkspaceProvider>
      );

      await waitFor(() => {
        expect(capturedWs?.state.proposals).toBeDefined();
      });

      await act(async () => {
        await capturedWs.fetchProposals({
          need_id: "need_water_001",
          organization_id: "org_alpha",
          status: "PROPOSED",
        });
      });

      expect(fetchMock).toHaveBeenCalledWith(
        "/api/network/coordination/proposals?need_id=need_water_001&organization_id=org_alpha&status=PROPOSED"
      );
    });

    it("CLEAR_ORG_DATA flushes proposals and switchOrganization refreshes data for the new org context", async () => {
      const { fetchMock } = setupCoordinationFetchMock({
        sessionOrg: "org_alpha",
        proposals: [MOCK_PROPOSAL_PROPOSED],
      });

      let capturedWs;
      render(
        <WorkspaceProvider>
          <TestController onState={(ws) => { capturedWs = ws; }} />
        </WorkspaceProvider>
      );

      await waitFor(() => {
        expect(capturedWs?.state.orgId).toBe("org_alpha");
        expect(capturedWs?.state.proposals).toHaveLength(1);
      });

      // Switch organization to org_beta
      await act(async () => {
        await capturedWs.switchOrganization({ orgId: "org_beta" });
      });

      expect(capturedWs.state.orgId).toBe("org_beta");
      expect(document.cookie).toContain("reliefos_org_id=org_beta");
      // fetchProposals called during refreshAll
      expect(fetchMock).toHaveBeenCalledWith("/api/network/coordination/proposals");
    });
  });

  describe("NeedDetail Coordination Section", () => {
    it("renders linked proposals for the need, allows proposing coordination to an NGO, and sending proposal to org", async () => {
      const { fetchMock } = setupCoordinationFetchMock({
        proposals: [MOCK_PROPOSAL_PROPOSED],
        needs: [MOCK_NEED],
      });

      render(
        <WorkspaceProvider>
          <TestController
            panelToOpen={{
              type: "need",
              entityId: MOCK_NEED.id,
              data: MOCK_NEED,
            }}
          />
          <ContextPanel />
        </WorkspaceProvider>
      );

      // Verify Need header and coordination section
      await waitFor(() => {
        expect(screen.getByText("Coordination")).toBeInTheDocument();
      });

      // Existing proposal should appear in the list
      await waitFor(() => {
        expect(screen.getByText("Coordination Proposals (1)")).toBeInTheDocument();
        expect(screen.getByText("Alpha Disaster Relief")).toBeInTheDocument();
        expect(screen.getByText("Send to Org")).toBeInTheDocument();
      });

      // Click "Send to Org"
      const sendButton = screen.getByRole("button", { name: "Send to Org" });
      await act(async () => {
        fireEvent.click(sendButton);
      });

      await waitFor(() => {
        expect(fetchMock).toHaveBeenCalledWith(
          "/api/network/coordination/proposals/prop_001/send-to-org",
          expect.objectContaining({ method: "POST" })
        );
      });

      // Now test "Propose Coordination" form
      const proposeBtn = screen.getByRole("button", { name: /Propose Coordination/i });
      fireEvent.click(proposeBtn);

      expect(screen.getByText("Target Organization")).toBeInTheDocument();
      const selectOrg = screen.getByRole("combobox");
      fireEvent.change(selectOrg, { target: { value: "org_beta" } });

      const submitBtn = screen.getByRole("button", { name: "Submit Proposal" });
      await act(async () => {
        fireEvent.click(submitBtn);
      });

      await waitFor(() => {
        expect(fetchMock).toHaveBeenCalledWith(
          "/api/network/coordination/propose",
          expect.objectContaining({
            method: "POST",
            body: expect.stringContaining('"organization_id":"org_beta"'),
          })
        );
      });
    });

    it("allows declining a proposal directly from the NeedDetail list", async () => {
      const { fetchMock } = setupCoordinationFetchMock({
        proposals: [MOCK_PROPOSAL_PROPOSED],
        needs: [MOCK_NEED],
      });

      render(
        <WorkspaceProvider>
          <TestController
            panelToOpen={{
              type: "need",
              entityId: MOCK_NEED.id,
              data: MOCK_NEED,
            }}
          />
          <ContextPanel />
        </WorkspaceProvider>
      );

      await waitFor(() => {
        expect(screen.getByText("Coordination Proposals (1)")).toBeInTheDocument();
      });

      const declineButton = screen.getByRole("button", { name: "Decline" });
      await act(async () => {
        fireEvent.click(declineButton);
      });

      await waitFor(() => {
        expect(fetchMock).toHaveBeenCalledWith(
          "/api/network/coordination/proposals/prop_001/decline",
          expect.objectContaining({ method: "POST" })
        );
      });
    });
  });

  describe("ProposalDetail Dossier (ContextPanel)", () => {
    it("renders full proposal dossier including public evidence, constraints, uncertainty, and links", async () => {
      const { fetchMock } = setupCoordinationFetchMock({
        proposals: [MOCK_PROPOSAL_PROPOSED],
      });

      render(
        <WorkspaceProvider>
          <TestController
            panelToOpen={{
              type: "proposal",
              entityId: MOCK_PROPOSAL_PROPOSED.id,
              data: MOCK_PROPOSAL_PROPOSED,
            }}
          />
          <ContextPanel />
        </WorkspaceProvider>
      );

      await waitFor(() => {
        expect(screen.getByText("Proposal Summary")).toBeInTheDocument();
        expect(screen.getByText(MOCK_PROPOSAL_PROPOSED.summary)).toBeInTheDocument();
        expect(screen.getAllByText("Alpha Disaster Relief").length).toBeGreaterThan(0);
        expect(screen.getByText(/Road NH-37 clear of major flooding/i)).toBeInTheDocument();
        expect(screen.getByText(/Dispatch within 6 hours/i)).toBeInTheDocument();
        expect(screen.getByText(/Possible flash flood warning near bypass/i)).toBeInTheDocument();
      });

      // Actions in PROPOSED status
      const sendButton = screen.getByRole("button", { name: "Send to Organization" });
      expect(sendButton).toBeInTheDocument();

      const declineButton = screen.getByRole("button", { name: "Decline Proposal" });
      expect(declineButton).toBeInTheDocument();

      await act(async () => {
        fireEvent.click(sendButton);
      });

      expect(fetchMock).toHaveBeenCalledWith(
        `/api/network/coordination/proposals/${MOCK_PROPOSAL_PROPOSED.id}/send-to-org`,
        expect.objectContaining({ method: "POST" })
      );
    });

    it("displays published offer link when proposal is PUBLISHED", async () => {
      setupCoordinationFetchMock({
        proposals: [MOCK_PROPOSAL_PUBLISHED],
      });

      render(
        <WorkspaceProvider>
          <TestController
            panelToOpen={{
              type: "proposal",
              entityId: MOCK_PROPOSAL_PUBLISHED.id,
              data: MOCK_PROPOSAL_PUBLISHED,
            }}
          />
          <ContextPanel />
        </WorkspaceProvider>
      );

      await waitFor(() => {
        expect(screen.getByText("Published Resource Offer")).toBeInTheDocument();
        expect(screen.getByText(MOCK_PROPOSAL_PUBLISHED.published_offer_id)).toBeInTheDocument();
        expect(screen.getByRole("button", { name: /Open Offer Details/i })).toBeInTheDocument();
      });
    });
  });

  describe("NGO Workspace: Incoming Proposals & Human-in-the-Loop", () => {
    it("renders Proposals tab in OrganizationWorkspace, allows AI evaluation, and human approval to publish offer", async () => {
      const { fetchMock } = setupCoordinationFetchMock({
        sessionOrg: "org_alpha",
        proposals: [MOCK_PROPOSAL_PROPOSED],
      });

      render(
        <WorkspaceProvider>
          <OrganizationWorkspace />
        </WorkspaceProvider>
      );

      // Wait for workspace summary to load, then click "Proposals" tab
      await waitFor(() => {
        expect(screen.getByRole("button", { name: /Proposals/i })).toBeInTheDocument();
      });

      fireEvent.click(screen.getByRole("button", { name: /Proposals/i }));

      // Verify fetch for org's incoming proposals
      await waitFor(() => {
        expect(fetchMock).toHaveBeenCalledWith(
          expect.stringContaining("/api/network/coordination/proposals?organization_id=org_alpha")
        );
        expect(screen.getByText(MOCK_PROPOSAL_PROPOSED.summary)).toBeInTheDocument();
      });

      // Trigger "Evaluate with NGO Context"
      const evalBtn = screen.getByRole("button", { name: "Evaluate with NGO Context" });
      await act(async () => {
        fireEvent.click(evalBtn);
      });

      // Verify POST to /api/my-org/agent/evaluate-coordination with proposal_id only (no client org_id param)
      await waitFor(() => {
        expect(fetchMock).toHaveBeenCalledWith(
          "/api/my-org/agent/evaluate-coordination",
          expect.objectContaining({
            method: "POST",
            body: JSON.stringify({ proposal_id: MOCK_PROPOSAL_PROPOSED.id }),
          })
        );
      });

      // Proposal status changes to ORG_RECOMMENDED and reveals "Approve & Publish Offer"
      await waitFor(() => {
        expect(screen.getByText("ORG_RECOMMENDED")).toBeInTheDocument();
        expect(screen.getByText(/Stock matches need requirement/i)).toBeInTheDocument();
        expect(screen.getByText(/Available Matching: 50 units/i)).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Approve & Publish Offer" })).toBeInTheDocument();
      });

      // Trigger Human-in-the-loop "Approve & Publish Offer"
      const approveBtn = screen.getByRole("button", { name: "Approve & Publish Offer" });
      await act(async () => {
        fireEvent.click(approveBtn);
      });

      // Verify POST to /api/my-org/agent/approve-publication with proposal_id only
      await waitFor(() => {
        expect(fetchMock).toHaveBeenCalledWith(
          "/api/my-org/agent/approve-publication",
          expect.objectContaining({
            method: "POST",
            body: JSON.stringify({ proposal_id: MOCK_PROPOSAL_PROPOSED.id }),
          })
        );
      });
    });

    it("verifies double-click prevention on publication approval", async () => {
      const { fetchMock } = setupCoordinationFetchMock({
        sessionOrg: "org_alpha",
        proposals: [MOCK_PROPOSAL_RECOMMENDED],
      });

      render(
        <WorkspaceProvider>
          <OrganizationWorkspace />
        </WorkspaceProvider>
      );

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /Proposals/i })).toBeInTheDocument();
      });

      fireEvent.click(screen.getByRole("button", { name: /Proposals/i }));

      await waitFor(() => {
        expect(screen.getByRole("button", { name: "Approve & Publish Offer" })).toBeInTheDocument();
      });

      const approveBtn = screen.getByRole("button", { name: "Approve & Publish Offer" });

      // Click twice in immediate succession
      act(() => {
        fireEvent.click(approveBtn);
        fireEvent.click(approveBtn);
      });

      // Wait for fetch calls
      await waitFor(() => {
        const publishCalls = fetchMock.mock.calls.filter(
          ([url]) => url === "/api/my-org/agent/approve-publication"
        );
        // Synchronous ref guard ensures only 1 publication request is fired
        expect(publishCalls).toHaveLength(1);
      });
    });
  });

  describe("ActivityBar Navigation on Coordination Events", () => {
    it("navigates to proposal panel when coordination activity event is clicked", async () => {
      const mockActivityEvent = {
        id: "evt_coord_01",
        event_type: "coordination_proposed",
        entity_type: "coordination",
        entity_id: "prop_001",
        detail: "New coordination proposal submitted for water need",
        created_at: "2026-09-08T02:00:00Z",
      };

      setupCoordinationFetchMock({
        proposals: [MOCK_PROPOSAL_PROPOSED],
        events: [mockActivityEvent],
      });

      let capturedWs;
      render(
        <WorkspaceProvider>
          <TestController onState={(ws) => { capturedWs = ws; }} />
          <ActivityBar />
        </WorkspaceProvider>
      );

      // Inject activity event into workspace state
      act(() => {
        capturedWs.dispatch({
          type: "SET_ACTIVITY",
          payload: [mockActivityEvent],
        });
      });

      await waitFor(() => {
        expect(screen.getByText("New coordination proposal submitted for water need")).toBeInTheDocument();
      });

      const eventItem = screen.getByText("New coordination proposal submitted for water need");
      fireEvent.click(eventItem);

      expect(capturedWs.state.panelOpen).toBe(true);
      expect(capturedWs.state.panelType).toBe("proposal");
      expect(capturedWs.state.panelEntityId).toBe("prop_001");
    });
  });

  describe("Strict Privacy Boundary Verification", () => {
    it("never renders private internal fields in public proposal projections", async () => {
      // Create a proposal that contains private fields (simulating leaked backend data)
      const proposalWithPrivateLeaks = {
        ...MOCK_PROPOSAL_PROPOSED,
        private_factors: {
          available_inventory: 1500,
          secret_depot_location: "Warehouse-Classified-Sector-9",
          staff_overtime_budget: 45000,
        },
        private_reasoning: "Do not expose: NGO reserved inventory for government contract",
      };

      setupCoordinationFetchMock({
        proposals: [proposalWithPrivateLeaks],
      });

      const { container } = render(
        <WorkspaceProvider>
          <TestController
            panelToOpen={{
              type: "proposal",
              entityId: proposalWithPrivateLeaks.id,
              data: proposalWithPrivateLeaks,
            }}
          />
          <ContextPanel />
        </WorkspaceProvider>
      );

      await waitFor(() => {
        expect(screen.getByText("Proposal Summary")).toBeInTheDocument();
      });

      // Confirm private content is completely absent from DOM
      expect(container.textContent).not.toContain("Warehouse-Classified-Sector-9");
      expect(container.textContent).not.toContain("secret_depot_location");
      expect(container.textContent).not.toContain("staff_overtime_budget");
      expect(container.textContent).not.toContain("private_reasoning");
      expect(container.textContent).not.toContain("reserved inventory for government contract");
    });

    it("verifies privileged /api/my-org/* endpoints do not pass org_id as client payload", async () => {
      const { fetchMock } = setupCoordinationFetchMock({
        sessionOrg: "org_alpha",
        proposals: [MOCK_PROPOSAL_PROPOSED],
      });

      render(
        <WorkspaceProvider>
          <OrganizationWorkspace />
        </WorkspaceProvider>
      );

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /Proposals/i })).toBeInTheDocument();
      });

      fireEvent.click(screen.getByRole("button", { name: /Proposals/i }));

      const evalBtn = await screen.findByRole("button", { name: "Evaluate with NGO Context" });
      await act(async () => {
        fireEvent.click(evalBtn);
      });

      // Check all calls to /api/my-org/
      const privilegedCalls = fetchMock.mock.calls.filter(([url]) =>
        url.toString().startsWith("/api/my-org/")
      );

      expect(privilegedCalls.length).toBeGreaterThan(0);
      privilegedCalls.forEach(([url, opts]) => {
        // Query param must not contain org_id
        expect(url.toString()).not.toContain("org_id=");
        if (opts?.body) {
          const parsed = JSON.parse(opts.body);
          // Body must not pass org_id
          expect(parsed.org_id).toBeUndefined();
        }
      });
    });
  });
});
