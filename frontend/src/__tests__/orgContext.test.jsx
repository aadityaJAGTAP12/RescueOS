/**
 * Organization identity context tests — frontend seam (lib/orgContext.js)
 *
 * Proves the frontend resolves the org from the server session (not a
 * hardcoded constant) and switches context through POST /api/session/org.
 * IDENTITY ONLY — NOT AUTHENTICATION: the server may resolve any org the
 * client asks for; there is no credential anywhere in this flow.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { render, act, screen, waitFor } from '@testing-library/react';
import {
  WorkspaceProvider,
  useWorkspace,
} from '../lib/workspaceContext';
import {
  getCurrentOrgId,
  selectOrg,
  resetOrgContextCache,
} from '../lib/orgContext';

const ORG_A = { id: 'org_alpha', name: 'Alpha NGO', organization_type: 'ngo', active: true };
const ORG_B = { id: 'org_beta', name: 'Beta NGO', organization_type: 'ngo', active: true };

function setupFetchMock({ sessionOrg = 'org_demo', organizations = [ORG_A, ORG_B] } = {}) {
  const fetchMock = vi.fn((url, options = {}) => {
    const u = typeof url === 'string' ? url : url.toString();
    if (u === '/api/session/org') {
      if (options && options.method === 'POST') {
        const body = JSON.parse(options.body || '{}');
        sessionOrg = body.org_id; // server accepts and remembers the selection
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ org_id: sessionOrg, name: sessionOrg }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ org_id: sessionOrg, registered: true, organizations }),
      });
    }
    if (u === '/api/organizations' && options && options.method === 'POST') {
      const body = JSON.parse(options.body || '{}');
      const org = { id: `org_${Math.random().toString(36).slice(2, 8)}`, ...body, active: true };
      organizations = [...organizations, org];
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ organization: org }),
      });
    }
    // Generic operational endpoints (workspace refresh)
    if (u.startsWith('/api/needs')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ needs: [] }) });
    if (u.startsWith('/api/offers')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ offers: [] }) });
    if (u.startsWith('/api/operations')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ operations: [] }) });
    if (u.startsWith('/api/districts')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ districts: [] }) });
    if (u.startsWith('/api/locations')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ locations: [] }) });
    if (u.startsWith('/api/settlements') || u.includes('/settlements')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ settlements: [] }) });
    if (u.includes('/flood-geojson')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ type: 'FeatureCollection', features: [] }) });
    if (u.includes('/roads')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ roads: [] }) });
    if (u.includes('/bridges')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ bridges: [] }) });
    if (u.includes('/medical-facilities')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ facilities: [] }) });
    if (u.includes('/field-intelligence/history')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ reports: [] }) });
    if (u.includes('/overrides')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ overrides: [] }) });
    if (u.includes('/activity')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ events: [] }) });
    if (u.includes('/notifications')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ notifications: [] }) });
    if (u.includes('/ai-coordinator')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ findings: [], summary: { total: 0 } }) });
    if (u.includes('/delta')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ summary: {}, directional: {} }) });
    if (u.includes('/flood-snapshots')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ snapshots: [] }) });
    if (u.includes('/incidents')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ incidents: [] }) });
    if (u.includes('/api/organizations')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ organizations }) });
    return Promise.resolve({ ok: false, json: () => Promise.resolve({}) });
  });
  global.fetch = fetchMock;
  return fetchMock;
}

function OrgConsumer({ onState }) {
  const { state, switchOrganization } = useWorkspace();
  React.useEffect(() => { if (onState) onState(state); }, [state, onState]);
  return (
    <div>
      <span data-testid="org-id">{state.orgId || 'none'}</span>
      <button
        data-testid="switch-beta"
        onClick={() => switchOrganization({ orgId: 'org_beta' })}
      >
        Switch to Beta
      </button>
      <button
        data-testid="create-org"
        onClick={() => switchOrganization({ create: { name: 'Gamma NGO' } })}
      >
        Create Gamma
      </button>
    </div>
  );
}

describe('org identity context (frontend seam)', () => {
  let fetchMock;

  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    // Delete the preference cookie (jsdom persists cookies across tests).
    document.cookie = 'reliefos_org_id=; max-age=0; path=/';
    resetOrgContextCache();
    fetchMock = setupFetchMock();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('resolves the org from the server session (not a hardcoded id)', async () => {
    let captured;
    render(
      <WorkspaceProvider>
        <OrgConsumer onState={(s) => { captured = s; }} />
      </WorkspaceProvider>
    );

    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });

    expect(fetchMock).toHaveBeenCalledWith('/api/session/org');
    expect(captured.orgId).toBe('org_demo');
  });

  it('selectOrg goes through POST /api/session/org and updates the cookie mirror', async () => {
    await act(async () => {
      const result = await selectOrg({ orgId: 'org_alpha' });
      expect(result.org_id).toBe('org_alpha');
    });
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/session/org',
      expect.objectContaining({ method: 'POST' })
    );
    expect(document.cookie).toContain('reliefos_org_id=org_alpha');
  });

  it('selectOrg can create a new organization and select it', async () => {
    await act(async () => {
      const result = await selectOrg({ create: { name: 'Gamma NGO' } });
      expect(result.org_id).toBeTruthy();
      expect(result.org_id).not.toBe('org_alpha');
    });
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/organizations',
      expect.objectContaining({ method: 'POST' })
    );
  });

  it('switchOrganization updates workspace org state and clears stale org data', async () => {
    let captured;
    render(
      <WorkspaceProvider>
        <OrgConsumer onState={(s) => { captured = s; }} />
      </WorkspaceProvider>
    );

    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
    expect(captured.orgId).toBe('org_demo');

    await act(async () => {
      screen.getByTestId('switch-beta').click();
      await vi.advanceTimersByTimeAsync(2000);
    });

    expect(captured.orgId).toBe('org_beta');
    expect(document.cookie).toContain('reliefos_org_id=org_beta');
  });

  it('create-and-switch flow resolves to the new org id', async () => {
    let captured;
    render(
      <WorkspaceProvider>
        <OrgConsumer onState={(s) => { captured = s; }} />
      </WorkspaceProvider>
    );

    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });

    await act(async () => {
      screen.getByTestId('create-org').click();
      await vi.advanceTimersByTimeAsync(2000);
    });

    expect(captured.orgId).toBeTruthy();
    expect(captured.orgId).not.toBe('org_demo');
  });

  it('getCurrentOrgId falls back to default when the session endpoint fails', async () => {
    global.fetch = vi.fn(() => Promise.resolve({ ok: false, status: 500 }));
    resetOrgContextCache();
    await expect(getCurrentOrgId({ allowFallback: false })).rejects.toThrow();
    resetOrgContextCache();
    await expect(getCurrentOrgId({})).resolves.toBe('org_demo');
  });

  it('prefers the cookie mirror over a fresh server fetch', async () => {
    document.cookie = 'reliefos_org_id=org_alpha; path=/';
    resetOrgContextCache();
    await expect(getCurrentOrgId({})).resolves.toBe('org_alpha');
    expect(fetchMock).not.toHaveBeenCalledWith('/api/session/org');
  });

  it('WorkspaceProvider surfaces the org id for display', async () => {
    let captured;
    function Display() {
      const { state } = useWorkspace();
      captured = state.orgId;
      return <div data-testid="display">{state.orgId || 'none'}</div>;
    }
    render(
      <WorkspaceProvider>
        <Display />
      </WorkspaceProvider>
    );
    await waitFor(() => {
      expect(screen.getByTestId('display').textContent).toBe('org_demo');
    });
    expect(captured).toBe('org_demo');
  });
});
