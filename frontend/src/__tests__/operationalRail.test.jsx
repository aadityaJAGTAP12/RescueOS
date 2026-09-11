import React from 'react';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, act, fireEvent } from '@testing-library/react';
import { WorkspaceProvider, useWorkspace } from '../lib/workspaceContext';
import LayerRail from '../components/workspace/LayerRail';
import ContextPanel from '../components/workspace/ContextPanel';

function setupFetchMock() {
  return vi.fn(async (url, options = {}) => {
    const u = typeof url === 'string' ? url : url.url || '';

    if (u.includes('/api/auth/session/org')) {
      return {
        ok: true,
        json: async () => ({ organization_id: 'org_test', role: 'NGO_COORDINATOR' }),
      };
    }

    if (u.includes('/api/districts')) {
      return {
        ok: true,
        json: async () => [
          { id: 'sivasagar', name: 'Sivasagar' },
          { id: 'jorhat', name: 'Jorhat' },
        ],
      };
    }

    if (u.includes('/api/settlements')) {
      return {
        ok: true,
        json: async () => [
          { id: 'set-1', name: 'Disangmukh', district_id: 'sivasagar', lat: 26.98, lon: 94.63 },
        ],
      };
    }

    if (u.includes('/api/needs')) {
      return {
        ok: true,
        json: async () => [
          { id: 'need-1', title: 'Water Needed', urgency: 'critical', status: 'OPEN', district_id: 'sivasagar', lat: 26.98, lon: 94.63 },
          { id: 'need-2', title: 'Food Packets', urgency: 'medium', status: 'RESPONDING', district_id: 'sivasagar', lat: 26.99, lon: 94.64 },
        ],
      };
    }

    if (u.includes('/api/operations')) {
      return {
        ok: true,
        json: async () => [
          { id: 'op-1', name: 'Boat Evac', operation_type: 'EVACUATION', status: 'ACTIVE', district_id: 'sivasagar', lat: 26.98, lon: 94.63 },
        ],
      };
    }

    if (u.includes('/api/offers')) {
      return {
        ok: true,
        json: async () => [
          { id: 'offer-1', resource_type: 'Potable Water', quantity: 500, unit: 'Liters', status: 'OFFERED', district_id: 'sivasagar', lat: 26.98, lon: 94.63 },
        ],
      };
    }

    if (u.includes('/api/organizations')) {
      return {
        ok: true,
        json: async () => [
          { id: 'org_redcross', name: 'Red Cross Assam', organization_type: 'NGO', active: true, published_capabilities: ['Water Purification', 'Medical Evac'] },
        ],
      };
    }

    if (u.includes('/api/field-reports') || u.includes('/api/field-intelligence/history')) {
      return {
        ok: true,
        json: async () => ({
          reports: [
            { id: 'rep-1', title: 'Water Rising Fast', people_count: 50, urgency: 'critical', status: 'OPEN', lat: 26.98, lon: 94.63, verified: true },
          ],
        }),
      };
    }

    if (u.includes('/api/overrides')) {
      return {
        ok: true,
        json: async () => ({
          overrides: [
            { active: true, target_id: 'road_nh37', override_status: 'blocked', reason: 'Flash flood', actor: 'Officer' },
          ],
        }),
      };
    }

    if (u.includes('/api/medical-facilities')) {
      return {
        ok: true,
        json: async () => [
          { id: 'med-1', name: 'Civil Hospital', facility_type: 'HOSPITAL', lat: 26.98, lon: 94.63 },
        ],
      };
    }

    if (u.includes('/api/roads')) {
      return {
        ok: true,
        json: async () => [],
      };
    }

    if (u.includes('/api/floods/')) {
      return {
        ok: true,
        json: async () => ({
          type: 'FeatureCollection',
          features: [
            {
              type: 'Feature',
              geometry: { type: 'Polygon', coordinates: [[[94.6, 26.9], [94.7, 26.9], [94.7, 27.0], [94.6, 27.0], [94.6, 26.9]]] },
              properties: { district_id: 'sivasagar' },
            },
          ],
        }),
      };
    }

    if (u.includes('/api/ai-coordinator/analysis') || u.includes('/api/ai/analysis')) {
      return {
        ok: true,
        json: async () => ({
          findings: [
            {
              id: 'find-1',
              severity: 'critical',
              type: 'coordination_gap',
              title: 'Unmet Critical Water Need',
              description: 'No responders allocated to Disangmukh',
              recommended_action: 'Deploy nearest water team',
              review_target: { panel_type: 'need', entity_id: 'need-1', map_center: [26.98, 94.63] },
            },
          ],
          summary: { total: 1, critical: 1, high: 0, medium: 0, low: 0 },
          generated_at: new Date().toISOString(),
        }),
      };
    }

    if (u.includes('/api/network/coordination/proposals')) {
      return {
        ok: true,
        json: async () => ({ proposals: [] }),
      };
    }

    if (u.includes('/api/notifications')) {
      return {
        ok: true,
        json: async () => ({ notifications: [], unread_count: 0 }),
      };
    }

    return {
      ok: true,
      json: async () => ({}),
    };
  });
}

function WorkspaceShellTest() {
  return (
    <div className="flex h-screen w-screen">
      <LayerRail />
      <ContextPanel />
    </div>
  );
}

describe('ReliefOS Operational Map Controls UI/UX Verification', () => {
  let fetchMock;

  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    fetchMock = setupFetchMock();
    globalThis.fetch = fetchMock;
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('1. Urgency filters toggle urgency state and auto-enable needs layer', async () => {
    render(
      <WorkspaceProvider>
        <WorkspaceShellTest />
      </WorkspaceProvider>
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    const criticalBtn = screen.getByTestId('urgency-critical');
    expect(criticalBtn).toBeDefined();

    // Click Critical urgency
    await act(async () => {
      fireEvent.click(criticalBtn);
      await vi.advanceTimersByTimeAsync(100);
    });

    expect(criticalBtn.getAttribute('aria-pressed')).toBe('true');
  });

  it('2. Status filters toggle status state and auto-enable needs layer', async () => {
    render(
      <WorkspaceProvider>
        <WorkspaceShellTest />
      </WorkspaceProvider>
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    const openBtn = screen.getByTestId('status-open');
    expect(openBtn).toBeDefined();

    // Click Open status
    await act(async () => {
      fireEvent.click(openBtn);
      await vi.advanceTimersByTimeAsync(100);
    });

    expect(openBtn.getAttribute('aria-pressed')).toBe('true');
  });

  it('3. Organizations toggle opens Organizations list context panel', async () => {
    render(
      <WorkspaceProvider>
        <WorkspaceShellTest />
      </WorkspaceProvider>
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    const orgsBtn = screen.getByTestId('layer-organizations');
    expect(orgsBtn).toBeDefined();

    await act(async () => {
      fireEvent.click(orgsBtn);
      await vi.advanceTimersByTimeAsync(200);
    });

    // Organizations panel should now be visible
    expect(screen.getByText('Red Cross Assam')).toBeDefined();
    expect(screen.getByText('Water Purification')).toBeDefined();
  });

  it('4. Reports toggle opens Field Reports list context panel', async () => {
    render(
      <WorkspaceProvider>
        <WorkspaceShellTest />
      </WorkspaceProvider>
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    const reportsBtn = screen.getByTestId('layer-fieldReports');
    expect(reportsBtn).toBeDefined();

    await act(async () => {
      fireEvent.click(reportsBtn);
      await vi.advanceTimersByTimeAsync(200);
    });

    expect(screen.getByText('Field Reports')).toBeDefined();
    expect(screen.getByText('Water Rising Fast')).toBeDefined();
  });

  it('5. Overrides toggle opens Active Overrides context panel', async () => {
    render(
      <WorkspaceProvider>
        <WorkspaceShellTest />
      </WorkspaceProvider>
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    const overridesBtn = screen.getByTestId('layer-overrides');
    expect(overridesBtn).toBeDefined();

    await act(async () => {
      fireEvent.click(overridesBtn);
      await vi.advanceTimersByTimeAsync(200);
    });

    expect(screen.getByText('Active Overrides')).toBeDefined();
    expect(screen.getByText('road_nh37')).toBeDefined();
  });

  it('6. AI Alerts toggle fetches analysis and opens AI Coordinator panel', async () => {
    render(
      <WorkspaceProvider>
        <WorkspaceShellTest />
      </WorkspaceProvider>
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    const aiAlertsBtn = screen.getByTestId('layer-aiAlerts');
    expect(aiAlertsBtn).toBeDefined();

    await act(async () => {
      fireEvent.click(aiAlertsBtn);
      await vi.advanceTimersByTimeAsync(500);
    });

    expect(screen.getByText('AI Coordinator')).toBeDefined();
    expect(screen.getByText('Unmet Critical Water Need')).toBeDefined();
  });
});
