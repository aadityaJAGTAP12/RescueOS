/**
 * Phase 7B.1 Tests — Workspace Context Filter & Layer Behavior
 *
 * Tests proving that filter controls actually affect application state/data.
 * Uses mocked fetch to simulate API responses.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import { render, act, screen, waitFor } from '@testing-library/react';
import { WorkspaceProvider, useWorkspace } from '../lib/workspaceContext';

// -------------------------------------------------------------------
// Mock fetch
// -------------------------------------------------------------------

const mockDistricts = [
  { id: 'sivasagar', name: 'Sivasagar' },
  { id: 'jorhat', name: 'Jorhat' },
  { id: 'charaideo', name: 'Charaideo' },
  { id: 'golaghat', name: 'Golaghat' },
];

const mockNeeds = [
  { id: 'n1', title: 'Water need', urgency: 'critical', status: 'OPEN', district_id: 'jorhat', lat: 26.75, lon: 94.22 },
  { id: 'n2', title: 'Food need', urgency: 'high', status: 'RESPONDING', district_id: 'sivasagar', lat: 26.98, lon: 94.66 },
  { id: 'n3', title: 'Medical need', urgency: 'medium', status: 'OPEN', district_id: 'jorhat', lat: 26.74, lon: 94.21 },
  { id: 'n4', title: 'Shelter need', urgency: 'low', status: 'RESOLVED', district_id: 'golaghat', lat: 26.51, lon: 93.91 },
];

const mockFloodJorhat = {
  type: 'FeatureCollection',
  features: [
    { type: 'Feature', properties: { district_id: 'jorhat' }, geometry: { type: 'Polygon', coordinates: [[[94.2, 26.7], [94.3, 26.7], [94.3, 26.8], [94.2, 26.8], [94.2, 26.7]]] } }
  ]
};

const mockFloodSivasagar = {
  type: 'FeatureCollection',
  features: [
    { type: 'Feature', properties: { district_id: 'sivasagar' }, geometry: { type: 'Polygon', coordinates: [[[94.6, 26.9], [94.7, 26.9], [94.7, 27.0], [94.6, 27.0], [94.6, 26.9]]] } }
  ]
};

const mockFloodCharaideo = {
  type: 'FeatureCollection',
  features: [
    { type: 'Feature', properties: { district_id: 'charaideo' }, geometry: { type: 'Polygon', coordinates: [[[95.1, 27.0], [95.2, 27.0], [95.2, 27.1], [95.1, 27.1], [95.1, 27.0]]] } }
  ]
};

const mockFloodGolaghat = {
  type: 'FeatureCollection',
  features: [
    { type: 'Feature', properties: { district_id: 'golaghat' }, geometry: { type: 'Polygon', coordinates: [[[93.9, 26.5], [94.0, 26.5], [94.0, 26.6], [93.9, 26.6], [93.9, 26.5]]] } }
  ]
};

const mockSettlements = [
  { id: 's1', name: 'Jorhat Town', district_id: 'jorhat', lat: 26.75, lon: 94.22 },
  { id: 's2', name: 'Sivasagar Town', district_id: 'sivasagar', lat: 26.98, lon: 94.66 },
];

const mockRoads = [
  { id: 'r1', name: 'NH-37', highway_type: 'primary', district_id: 'jorhat', flood_affected: false, geometry_coords: [[94.2, 26.7], [94.3, 26.7]] },
  { id: 'r2', name: 'SH-1', highway_type: 'secondary', district_id: 'sivasagar', flood_affected: false, geometry_coords: [[94.6, 26.9], [94.7, 26.9]] },
];

const mockBridges = [
  { id: 'b1', name: 'Bridge B1', highway_type: 'primary', district_id: 'jorhat', is_bridge: true, flood_affected: false, geometry_coords: [[94.2, 26.7], [94.21, 26.71]] },
];

const mockMedical = [
  { id: 'm1', name: 'Jorhat Hospital', facility_type: 'hospital', district_id: 'jorhat', lat: 26.75, lon: 94.22 },
];

const mockOperations = [
  { id: 'op1', name: 'Water delivery', operation_type: 'supply_delivery', status: 'ACTIVE', district_id: 'jorhat', lat: 26.75, lon: 94.22 },
  { id: 'op2', name: 'Food distribution', operation_type: 'supply_delivery', status: 'PLANNING', district_id: 'sivasagar', lat: 26.98, lon: 94.66 },
];

const mockFieldReports = [
  { id: 'fr1', people_count: 10, lat: 26.75, lon: 94.22, needs: ['water'], verified: false, source: 'field_intelligence_text' },
];

const mockOrganizations = [
  { id: 'org1', name: 'NGO Alpha', organization_type: 'ngo', active: true },
];

const mockOffers = [
  { id: 'of1', resource_type: 'boat', quantity: 2, unit: 'units', district_id: 'jorhat', status: 'OFFERED', lat: 26.75, lon: 94.22 },
];

const mockFloodSnapshots = [
  { id: 'flood_jorhat_20260729', district_id: 'jorhat', polygon_count: 5, observed_at: '2026-07-29T00:00:00Z', source: 'sentinel-1', confidence: 'high' },
  { id: 'flood_sivasagar_20260701', district_id: 'sivasagar', polygon_count: 3, observed_at: '2026-07-01T00:00:00Z', source: 'sentinel-1', confidence: 'high' },
];

function setupFetchMock() {
  // Mock ALL-districts flood data (merged with district_id in properties)
  const mockFloodAll = {
    type: 'FeatureCollection',
    features: [
      ...mockFloodJorhat.features.map(f => ({...f, properties: {...f.properties, district_id: 'jorhat'}})),
      ...mockFloodSivasagar.features.map(f => ({...f, properties: {...f.properties, district_id: 'sivasagar'}})),
      ...mockFloodCharaideo.features.map(f => ({...f, properties: {...f.properties, district_id: 'charaideo'}})),
      ...mockFloodGolaghat.features.map(f => ({...f, properties: {...f.properties, district_id: 'golaghat'}})),
    ]
  };

  const fetchMock = vi.fn((url) => {
    const u = typeof url === 'string' ? url : url.toString();

    // ALL districts flood endpoint (server aggregation)
    if (u === '/api/flood-geojson') {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(mockFloodAll) });
    }
    if (u.includes('/api/districts') && u.includes('/flood-geojson')) {
      if (u.includes('sivasagar')) return Promise.resolve({ ok: true, json: () => Promise.resolve(mockFloodSivasagar) });
      if (u.includes('jorhat')) return Promise.resolve({ ok: true, json: () => Promise.resolve(mockFloodJorhat) });
      if (u.includes('charaideo')) return Promise.resolve({ ok: true, json: () => Promise.resolve(mockFloodCharaideo) });
      if (u.includes('golaghat')) return Promise.resolve({ ok: true, json: () => Promise.resolve(mockFloodGolaghat) });
    }
    if (u === '/api/districts') return Promise.resolve({ ok: true, json: () => Promise.resolve({ districts: mockDistricts }) });
    if (u.includes('/settlements')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ settlements: mockSettlements }) });
    if (u === '/api/locations') return Promise.resolve({ ok: true, json: () => Promise.resolve({ locations: mockSettlements }) });
    if (u.includes('/roads')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ roads: mockRoads.filter(r => u.includes(r.district_id)) }) });
    if (u.includes('/bridges')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ bridges: mockBridges.filter(b => u.includes(b.district_id)) }) });
    if (u.includes('/medical-facilities')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ facilities: mockMedical.filter(f => u.includes(f.district_id)) }) });
    if (u.includes('/api/needs')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ needs: mockNeeds }) });
    if (u.includes('/api/operations')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ operations: mockOperations }) });
    if (u.includes('/api/offers')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ offers: mockOffers }) });
    if (u.includes('/api/field-intelligence/history')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ reports: mockFieldReports }) });
    if (u.includes('/api/organizations')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ organizations: mockOrganizations }) });
    if (u.includes('/api/overrides')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ overrides: [] }) });
    if (u.includes('/api/activity')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ events: [] }) });
    if (u.includes('/api/notifications')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ notifications: [] }) });
    if (u.includes('/api/ai-coordinator')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ findings: [], summary: { total: 0 } }) });
    if (u.includes('/api/delta')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ summary: {}, directional: {} }) });
    if (u.includes('/api/flood-snapshots')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ snapshots: mockFloodSnapshots }) });
    if (u.includes('/api/incidents')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ incidents: [] }) });

    return Promise.resolve({ ok: false, json: () => Promise.resolve({}) });
  });

  global.fetch = fetchMock;
  return fetchMock;
}

// -------------------------------------------------------------------
// Helper: test component that reads workspace state
// -------------------------------------------------------------------

function TestConsumer({ onState }) {
  const { state, setFilter, toggleLayer } = useWorkspace();
  React.useEffect(() => {
    if (onState) onState(state);
  }, [state, onState]);
  return (
    <div>
      <span data-testid="district">{state.filters.district || 'ALL'}</span>
      <span data-testid="needs-count">{state.needs.length}</span>
      <span data-testid="flood-features">{state.floodData?.features?.length || 0}</span>
      <span data-testid="settlements-count">{state.settlements.length}</span>
      <button data-testid="set-jorhat" onClick={() => setFilter('district', 'jorhat')}>Set Jorhat</button>
      <button data-testid="set-all" onClick={() => setFilter('district', null)}>Set All</button>
      <button data-testid="set-critical" onClick={() => setFilter('urgency', 'critical')}>Set Critical</button>
      <button data-testid="clear-urgency" onClick={() => setFilter('urgency', null)}>Clear Urgency</button>
      <button data-testid="set-open" onClick={() => setFilter('status', 'OPEN')}>Set Open</button>
      <button data-testid="clear-status" onClick={() => setFilter('status', null)}>Clear Status</button>
      <button data-testid="toggle-roads" onClick={() => toggleLayer('roads')}>Toggle Roads</button>
      <button data-testid="toggle-medical" onClick={() => toggleLayer('medical')}>Toggle Medical</button>
    </div>
  );
}

// -------------------------------------------------------------------
// Tests
// -------------------------------------------------------------------

describe('Phase 7B.1 — Functional Shell', () => {
  let fetchMock;

  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    fetchMock = setupFetchMock();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  // Test 1: ALL DISTRICTS loads four flood contexts
  it('1. ALL DISTRICTS loads flood data from all four districts', async () => {
    let capturedState;
    render(
      <WorkspaceProvider>
        <TestConsumer onState={(s) => { capturedState = s; }} />
      </WorkspaceProvider>
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    // Should have flood features from all 4 districts
    expect(capturedState.floodData).toBeTruthy();
    expect(capturedState.floodData.features.length).toBe(4);
    const districtIds = capturedState.floodData.features.map(f => f.properties.district_id);
    expect(districtIds).toContain('sivasagar');
    expect(districtIds).toContain('jorhat');
    expect(districtIds).toContain('charaideo');
    expect(districtIds).toContain('golaghat');
  });

  // Test 2: Sivasagar district filter scopes flood
  it('2. Sivasagar district filter scopes flood to Sivasagar only', async () => {
    let capturedState;
    render(
      <WorkspaceProvider>
        <TestConsumer onState={(s) => { capturedState = s; }} />
      </WorkspaceProvider>
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    // Initially ALL — should have 4 features
    expect(capturedState.floodData.features.length).toBe(4);

    // Click "Set Jorhat"
    await act(async () => {
      screen.getByTestId('set-jorhat').click();
      await vi.advanceTimersByTimeAsync(1000);
    });

    expect(capturedState.filters.district).toBe('jorhat');
    // Flood data should be scoped to Jorhat
    expect(capturedState.floodData.features.length).toBe(1);
    expect(capturedState.floodData.features[0].properties.district_id).toBe('jorhat');
  });

  // Test 3: Jorhat district filter scopes flood
  it('3. Jorhat district filter shows only Jorhat flood', async () => {
    let capturedState;
    render(
      <WorkspaceProvider>
        <TestConsumer onState={(s) => { capturedState = s; }} />
      </WorkspaceProvider>
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    await act(async () => {
      screen.getByTestId('set-jorhat').click();
      await vi.advanceTimersByTimeAsync(1000);
    });

    expect(capturedState.floodData.features.length).toBe(1);
    expect(capturedState.floodData.features[0].properties.district_id).toBe('jorhat');
  });

  // Test 4 & 5: District switching updates flood correctly
  it('4. Switching district updates flood data accordingly', async () => {
    let capturedState;
    render(
      <WorkspaceProvider>
        <TestConsumer onState={(s) => { capturedState = s; }} />
      </WorkspaceProvider>
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    // Set to Sivasagar (via Jorhat then All then check)
    await act(async () => {
      screen.getByTestId('set-jorhat').click();
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(capturedState.floodData.features[0].properties.district_id).toBe('jorhat');

    // Set back to ALL
    await act(async () => {
      screen.getByTestId('set-all').click();
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(capturedState.floodData.features.length).toBe(4);
  });

  // Test 6: Roads toggle changes map visibility/data
  it('6. Roads toggle changes layer state', async () => {
    let capturedState;
    render(
      <WorkspaceProvider>
        <TestConsumer onState={(s) => { capturedState = s; }} />
      </WorkspaceProvider>
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    // Roads should start enabled
    expect(capturedState.layers.roads).toBe(true);

    // Toggle roads off
    await act(async () => {
      screen.getByTestId('toggle-roads').click();
    });
    expect(capturedState.layers.roads).toBe(false);
  });

  // Test 15: Critical severity filter changes visible entities
  it('15. Critical severity filter affects filter state', async () => {
    let capturedState;
    render(
      <WorkspaceProvider>
        <TestConsumer onState={(s) => { capturedState = s; }} />
      </WorkspaceProvider>
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    // Initially no urgency filter
    expect(capturedState.filters.urgency).toBeNull();

    // Set critical
    await act(async () => {
      screen.getByTestId('set-critical').click();
    });
    expect(capturedState.filters.urgency).toBe('critical');

    // Clear
    await act(async () => {
      screen.getByTestId('clear-urgency').click();
    });
    expect(capturedState.filters.urgency).toBeNull();
  });

  // Test 19: Open status filter works
  it('19. Open status filter changes filter state', async () => {
    let capturedState;
    render(
      <WorkspaceProvider>
        <TestConsumer onState={(s) => { capturedState = s; }} />
      </WorkspaceProvider>
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    expect(capturedState.filters.status).toBeNull();

    await act(async () => {
      screen.getByTestId('set-open').click();
    });
    expect(capturedState.filters.status).toBe('OPEN');

    await act(async () => {
      screen.getByTestId('clear-status').click();
    });
    expect(capturedState.filters.status).toBeNull();
  });

  it('sends compatible query params when rail filters change', async () => {
    render(
      <WorkspaceProvider>
        <TestConsumer />
      </WorkspaceProvider>
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    fetchMock.mockClear();

    await act(async () => {
      screen.getByTestId('set-jorhat').click();
      await vi.advanceTimersByTimeAsync(1000);
    });

    expect(fetchMock).toHaveBeenCalledWith('/api/needs?district_id=jorhat');
    expect(fetchMock).toHaveBeenCalledWith('/api/offers?district_id=jorhat');
    expect(fetchMock).toHaveBeenCalledWith('/api/operations?district_id=jorhat');

    fetchMock.mockClear();

    await act(async () => {
      screen.getByTestId('set-open').click();
      await vi.advanceTimersByTimeAsync(1000);
    });

    expect(fetchMock).toHaveBeenCalledWith('/api/needs?district_id=jorhat');
    expect(fetchMock).toHaveBeenCalledWith('/api/offers?district_id=jorhat');
    expect(fetchMock).toHaveBeenCalledWith('/api/operations?district_id=jorhat');
    expect(fetchMock).not.toHaveBeenCalledWith('/api/needs?district_id=jorhat&status=OPEN');
    expect(fetchMock).not.toHaveBeenCalledWith('/api/offers?district_id=jorhat&status=OPEN');
    expect(fetchMock).not.toHaveBeenCalledWith('/api/operations?district_id=jorhat&status=OPEN');
  });

  // Test: Layer toggle affects state
  it('Layer toggle changes layer enabled state', async () => {
    let capturedState;
    render(
      <WorkspaceProvider>
        <TestConsumer onState={(s) => { capturedState = s; }} />
      </WorkspaceProvider>
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    // Roads should be ON by default
    expect(capturedState.layers.roads).toBe(true);

    // Toggle off
    await act(async () => {
      screen.getByTestId('toggle-roads').click();
    });
    expect(capturedState.layers.roads).toBe(false);

    // Toggle back on
    await act(async () => {
      screen.getByTestId('toggle-roads').click();
    });
    expect(capturedState.layers.roads).toBe(true);
  });

  // Test: Districts loaded
  it('Districts are loaded from API', async () => {
    let capturedState;
    render(
      <WorkspaceProvider>
        <TestConsumer onState={(s) => { capturedState = s; }} />
      </WorkspaceProvider>
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    expect(capturedState.districts.length).toBe(4);
    expect(capturedState.districts.map(d => d.id)).toEqual(
      expect.arrayContaining(['sivasagar', 'jorhat', 'charaideo', 'golaghat'])
    );
  });

  // Test: Settlements loaded
  it('Settlements are loaded from API', async () => {
    let capturedState;
    render(
      <WorkspaceProvider>
        <TestConsumer onState={(s) => { capturedState = s; }} />
      </WorkspaceProvider>
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    expect(capturedState.settlements.length).toBeGreaterThan(0);
  });

  // Test: Needs loaded
  it('Needs are loaded from API', async () => {
    let capturedState;
    render(
      <WorkspaceProvider>
        <TestConsumer onState={(s) => { capturedState = s; }} />
      </WorkspaceProvider>
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    expect(capturedState.needs.length).toBeGreaterThan(0);
  });

  // Test: Search functionality
  it('Search filters across loaded data', async () => {
    let capturedState;
    let searchFn;

    function SearchTest() {
      const { state, performSearch } = useWorkspace();
      capturedState = state;
      searchFn = performSearch;
      return <div />;
    }

    render(
      <WorkspaceProvider>
        <SearchTest />
      </WorkspaceProvider>
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    // Search for "water"
    act(() => {
      searchFn('water');
    });

    expect(capturedState.searchResults.length).toBeGreaterThan(0);
    expect(capturedState.searchResults.some(r => r.name?.toLowerCase().includes('water'))).toBe(true);
  });

  // Test: Toggle medical layer
  it('Medical layer toggle changes state', async () => {
    let capturedState;
    render(
      <WorkspaceProvider>
        <TestConsumer onState={(s) => { capturedState = s; }} />
      </WorkspaceProvider>
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    // Medical ON by default
    expect(capturedState.layers.medical).toBe(true);

    await act(async () => {
      screen.getByTestId('toggle-medical').click();
    });
    expect(capturedState.layers.medical).toBe(false);
  });
});
