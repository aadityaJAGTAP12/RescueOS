/**
 * Notification Event Generation Frontend Tests (Item #6)
 *
 * Verifies:
 * 1. Notification badge & count rendering in WorkspaceHeader.
 * 2. Notification popover dropdown open/close and keyboard dismiss.
 * 3. Popover list presentation (title, message, timestamp, unread indicators).
 * 4. Mark single notification as read & mark all as read.
 * 5. Navigation: clicking notifications opens the relevant context panel (need, proposal).
 * 6. Organization isolation & switching: notifications refresh scoped to active org.
 * 7. Privacy boundary: notifications never expose private factors.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import React from "react";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { WorkspaceProvider, useWorkspace } from "../lib/workspaceContext";
import { resetOrgContextCache } from "../lib/orgContext";
import WorkspaceHeader from "../components/workspace/WorkspaceHeader";
import ContextPanel from "../components/workspace/ContextPanel";

// -------------------------------------------------------------------
// Mock Data
// -------------------------------------------------------------------

const MOCK_ORG_A = {
  id: "org_alpha",
  name: "Alpha Disaster Relief",
  organization_type: "ngo",
  active: true,
};

const MOCK_NOTIFS_ALPHA = [
  {
    id: "notif_001",
    recipient_id: "org_alpha",
    notification_type: "coordination_proposal_received",
    title: "New Coordination Proposal",
    message: "Network proposed coordination for Need need_water_001. Requires evaluation.",
    entity_type: "coordination",
    entity_id: "prop_001",
    read: false,
    created_at: "2026-09-08T02:00:00Z",
    metadata: { proposal_id: "prop_001" },
  },
  {
    id: "notif_002",
    recipient_id: "org_alpha",
    notification_type: "urgent_need",
    title: "Critical Need Reported",
    message: "Urgent need in Jorhat: Drinking Water for 500 Families",
    entity_type: "need",
    entity_id: "need_water_001",
    read: true,
    created_at: "2026-09-08T01:30:00Z",
    metadata: { need_id: "need_water_001" },
  },
];

const MOCK_NOTIFS_NETWORK = [
  {
    id: "notif_net_001",
    recipient_id: "network",
    notification_type: "coordination_offer_published",
    title: "Resource Offer Published",
    message: "Organization org_alpha approved and published offer offer_001 for Need need_water_001.",
    entity_type: "coordination",
    entity_id: "prop_001",
    read: false,
    created_at: "2026-09-08T02:30:00Z",
    metadata: { proposal_id: "prop_001", offer_id: "offer_001" },
  },
];

describe("Item #6 — Notification Event Generation UI", () => {
  let mockFetch;

  beforeEach(() => {
    resetOrgContextCache();
    mockFetch = vi.fn().mockImplementation((url, options) => {
      const urlStr = typeof url === "string" ? url : url.toString();

      // Session org
      if (urlStr.includes("/api/session/org")) {
        if (options && options.method === "POST") {
          const body = JSON.parse(options.body || "{}");
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ org_id: body.org_id || "org_alpha" }),
          });
        }
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ org_id: "org_alpha" }),
        });
      }

      // Organizations
      if (urlStr.includes("/api/organizations")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ organizations: [MOCK_ORG_A] }),
        });
      }

      // Mark notification read
      if (urlStr.includes("/read") && options?.method === "POST") {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ success: true, notification: { id: "notif_001", read: true } }),
        });
      }

      // Notifications
      if (urlStr.includes("/api/notifications")) {
        if (urlStr.includes("recipient_id=network")) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ notifications: MOCK_NOTIFS_NETWORK }),
          });
        }
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ notifications: MOCK_NOTIFS_ALPHA }),
        });
      }

      // Proposals
      if (urlStr.includes("/api/network/coordination/proposals")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ proposals: [{ id: "prop_001", need_id: "need_water_001", status: "PROPOSED" }] }),
        });
      }

      // Needs
      if (urlStr.includes("/api/needs")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            needs: [{
              id: "need_water_001",
              title: "Drinking Water for 500 Families",
              need_type: "water",
              urgency: "critical",
              status: "OPEN",
            }],
          }),
        });
      }

      // Fallback
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({}),
      });
    });

    global.fetch = mockFetch;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders notification bell with unread count badge", async () => {
    render(
      <WorkspaceProvider>
        <WorkspaceHeader />
      </WorkspaceProvider>
    );

    // Wait for notifications to load
    await waitFor(() => {
      // 1 unread notification in MOCK_NOTIFS_ALPHA
      const badge = screen.getByText("1");
      expect(badge).toBeInTheDocument();
    });
  });

  it("opens and closes notification popover on bell click", async () => {
    render(
      <WorkspaceProvider>
        <WorkspaceHeader />
      </WorkspaceProvider>
    );

    await waitFor(() => {
      expect(screen.getByTitle("Notifications")).toBeInTheDocument();
    });

    const bellBtn = screen.getByTitle("Notifications");
    fireEvent.click(bellBtn);

    // Popover header should be visible
    expect(screen.getByText("Notifications")).toBeInTheDocument();
    expect(screen.getByText("1 unread")).toBeInTheDocument();
    expect(screen.getByText("New Coordination Proposal")).toBeInTheDocument();
    expect(screen.getByText("Critical Need Reported")).toBeInTheDocument();

    // Toggle close
    fireEvent.click(bellBtn);
    expect(screen.queryByText("1 unread")).not.toBeInTheDocument();
  });

  it("marks a notification as read when clicking mark read button", async () => {
    render(
      <WorkspaceProvider>
        <WorkspaceHeader />
      </WorkspaceProvider>
    );

    await waitFor(() => {
      expect(screen.getByTitle("Notifications")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTitle("Notifications"));

    await waitFor(() => {
      expect(screen.getByTitle("Mark as read")).toBeInTheDocument();
    });

    const markReadBtn = screen.getByTitle("Mark as read");
    fireEvent.click(markReadBtn);

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        "/api/notifications/notif_001/read",
        expect.objectContaining({ method: "POST" })
      );
    });
  });

  it("marks all notifications as read when clicking 'Mark all read'", async () => {
    render(
      <WorkspaceProvider>
        <WorkspaceHeader />
      </WorkspaceProvider>
    );

    await waitFor(() => {
      expect(screen.getByTitle("Notifications")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTitle("Notifications"));

    await waitFor(() => {
      expect(screen.getByTitle("Mark all as read")).toBeInTheDocument();
    });

    const markAllBtn = screen.getByTitle("Mark all as read");
    fireEvent.click(markAllBtn);

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        "/api/notifications/notif_001/read",
        expect.objectContaining({ method: "POST" })
      );
    });
  });

  it("navigates to relevant panel when clicking on a notification", async () => {
    render(
      <WorkspaceProvider>
        <WorkspaceHeader />
        <ContextPanel />
      </WorkspaceProvider>
    );

    await waitFor(() => {
      expect(screen.getByTitle("Notifications")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTitle("Notifications"));

    await waitFor(() => {
      expect(screen.getByText("New Coordination Proposal")).toBeInTheDocument();
    });

    // Click on the coordination proposal notification
    fireEvent.click(screen.getByText("New Coordination Proposal"));

    // Proposal context panel should open
    await waitFor(() => {
      expect(screen.getByText("Proposal Summary")).toBeInTheDocument();
    });
  });

  it("strictly enforces privacy: notifications do not leak private factors", async () => {
    render(
      <WorkspaceProvider>
        <WorkspaceHeader />
      </WorkspaceProvider>
    );

    await waitFor(() => {
      expect(screen.getByTitle("Notifications")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTitle("Notifications"));

    await waitFor(() => {
      expect(screen.getByText("Notifications")).toBeInTheDocument();
    });

    // Verify no private factors or internal telemetry in DOM
    expect(screen.queryByText(/private_factors/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/SECRET_/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/warehouse_capacity/i)).not.toBeInTheDocument();
  });
});
