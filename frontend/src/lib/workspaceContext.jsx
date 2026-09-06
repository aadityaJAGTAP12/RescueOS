import { createContext, useContext, useReducer, useCallback, useEffect, useRef } from "react";

// -------------------------------------------------------------------
// Initial state
// -------------------------------------------------------------------

const initialLayers = {
  flood: true,
  floodHistory: false,
  roads: true,
  bridges: true,
  settlements: true,
  buildings: false,
  medical: true,
  organizations: false,
  needs: true,
  offers: false,
  operations: true,
  incidents: false,
  fieldReports: true,
  overrides: true,
  aiAlerts: false,
};

const initialFilters = {
  district: null,
  urgency: null,
  status: null,
};

const initialState = {
  // Map
  mapCenter: [26.98, 94.66],
  mapZoom: 11,

  // Layers
  layers: initialLayers,

  // Filters
  filters: initialFilters,

  // Context panel
  panelOpen: false,
  panelType: null,
  panelEntityId: null,
  panelData: null,

  // Data
  floodData: null,
  districts: [],
  settlements: [],
  roads: [],
  bridges: [],
  medicalFacilities: [],
  buildings: [],
  buildingsMeta: null,
  organizations: [],
  needs: [],
  offers: [],
  operations: [],
  fieldReports: [],
  overrides: {},
  activity: [],
  notifications: [],
  incidents: [],
  floodSnapshots: [],
  selectedFloodSnapshot: null,
  selectedFloodData: null,

  // AI Coordinator
  aiAnalysis: null,
  aiLoading: false,

  // Delta / What Changed
  delta: null,
  deltaLoading: false,

  // Selected entity (for map/panel sync)
  selectedEntity: null,

  // Search
  searchQuery: "",
  searchResults: [],

  // Loading states
  loading: {
    flood: false,
    districts: false,
    settlements: false,
    roads: false,
    bridges: false,
    medicalFacilities: false,
    buildings: false,
    organizations: false,
    needs: false,
    offers: false,
    operations: false,
    fieldReports: false,
    activity: false,
    floodSnapshots: false,
  },
};

// -------------------------------------------------------------------
// Reducer
// -------------------------------------------------------------------

function workspaceReducer(state, action) {
  switch (action.type) {
    case "SET_MAP_CENTER":
      return { ...state, mapCenter: action.payload };

    case "SET_MAP_ZOOM":
      return { ...state, mapZoom: action.payload };

    case "TOGGLE_LAYER":
      return {
        ...state,
        layers: { ...state.layers, [action.payload]: !state.layers[action.payload] },
      };

    case "SET_FILTER":
      return {
        ...state,
        filters: { ...state.filters, [action.payload.key]: action.payload.value },
      };

    case "OPEN_PANEL":
      return {
        ...state,
        panelOpen: true,
        panelType: action.payload.type,
        panelEntityId: action.payload.entityId || null,
        panelData: action.payload.data || null,
      };

    case "CLOSE_PANEL":
      return {
        ...state,
        panelOpen: false,
        panelType: null,
        panelEntityId: null,
        panelData: null,
      };

    case "SET_PANEL_DATA":
      return { ...state, panelData: action.payload };

    case "SET_FLOOD_DATA":
      return { ...state, floodData: action.payload, loading: { ...state.loading, flood: false } };

    case "SET_BUILDINGS":
      return { ...state, buildings: action.payload.features || [], buildingsMeta: action.payload.meta || null, loading: { ...state.loading, buildings: false } };

    case "SET_ORGANIZATIONS":
      return { ...state, organizations: action.payload, loading: { ...state.loading, organizations: false } };

    case "SET_INCIDENTS":
      return { ...state, incidents: action.payload };

    case "SET_FLOOD_SNAPSHOTS":
      return { ...state, floodSnapshots: action.payload, loading: { ...state.loading, floodSnapshots: false } };

    case "SET_SELECTED_FLOOD_SNAPSHOT":
      return { ...state, selectedFloodSnapshot: action.payload.snapshot, selectedFloodData: action.payload.data };

    case "SET_DISTRICTS":
      return { ...state, districts: action.payload, loading: { ...state.loading, districts: false } };

    case "SET_SETTLEMENTS":
      return { ...state, settlements: action.payload, loading: { ...state.loading, settlements: false } };

    case "SET_ROADS":
      return { ...state, roads: action.payload, loading: { ...state.loading, roads: false } };

    case "SET_BRIDGES":
      return { ...state, bridges: action.payload, loading: { ...state.loading, bridges: false } };

    case "SET_MEDICAL_FACILITIES":
      return { ...state, medicalFacilities: action.payload, loading: { ...state.loading, medicalFacilities: false } };

    case "SET_NEEDS":
      return { ...state, needs: action.payload, loading: { ...state.loading, needs: false } };

    case "SET_OFFERS":
      return { ...state, offers: action.payload, loading: { ...state.loading, offers: false } };

    case "SET_OPERATIONS":
      return { ...state, operations: action.payload, loading: { ...state.loading, operations: false } };

    case "SET_FIELD_REPORTS":
      return { ...state, fieldReports: action.payload, loading: { ...state.loading, fieldReports: false } };

    case "SET_OVERRIDES":
      return { ...state, overrides: action.payload };

    case "SET_ACTIVITY":
      return { ...state, activity: action.payload, loading: { ...state.loading, activity: false } };

    case "SET_NOTIFICATIONS":
      return { ...state, notifications: action.payload };

    case "SET_AI_ANALYSIS":
      return { ...state, aiAnalysis: action.payload, aiLoading: false };

    case "SET_AI_LOADING":
      return { ...state, aiLoading: action.payload };

    case "SET_DELTA":
      return { ...state, delta: action.payload, deltaLoading: false };

    case "SET_DELTA_LOADING":
      return { ...state, deltaLoading: action.payload };

    case "SET_SELECTED_ENTITY":
      return { ...state, selectedEntity: action.payload };

    case "SET_SEARCH_QUERY":
      return { ...state, searchQuery: action.payload };

    case "SET_SEARCH_RESULTS":
      return { ...state, searchResults: action.payload };

    case "SET_LOADING":
      return {
        ...state,
        loading: { ...state.loading, [action.payload.key]: action.payload.value },
      };

    default:
      return state;
  }
}

// -------------------------------------------------------------------
// Context
// -------------------------------------------------------------------

const WorkspaceContext = createContext(null);

export function WorkspaceProvider({ children }) {
  const [state, dispatch] = useReducer(workspaceReducer, initialState);
  const refreshRef = useRef(null);

  // --- Data fetching functions ---

  const fetchFloodData = useCallback(async (districtId) => {
    dispatch({ type: "SET_LOADING", payload: { key: "flood", value: true } });
    try {
      // Server endpoints: single district or ALL (server aggregates + tags district_id)
      const url = districtId
        ? `/api/districts/${districtId}/flood-geojson`
        : "/api/flood-geojson";
      const resp = await fetch(url);
      if (resp.ok) {
        const data = await resp.json();
        dispatch({ type: "SET_FLOOD_DATA", payload: data });
      }
    } catch (err) {
      console.error("Failed to fetch flood data:", err);
      dispatch({ type: "SET_LOADING", payload: { key: "flood", value: false } });
    }
  }, []);

  const fetchDistricts = useCallback(async () => {
    dispatch({ type: "SET_LOADING", payload: { key: "districts", value: true } });
    try {
      const resp = await fetch("/api/districts");
      if (resp.ok) {
        const data = await resp.json();
        dispatch({ type: "SET_DISTRICTS", payload: data.districts || [] });
      }
    } catch (err) {
      console.error("Failed to fetch districts:", err);
      dispatch({ type: "SET_LOADING", payload: { key: "districts", value: false } });
    }
  }, []);

  const fetchSettlements = useCallback(async (districtId) => {
    dispatch({ type: "SET_LOADING", payload: { key: "settlements", value: true } });
    try {
      const url = districtId
        ? `/api/districts/${districtId}/settlements`
        : "/api/locations";
      const resp = await fetch(url);
      if (resp.ok) {
        const data = await resp.json();
        const items = data.settlements || data.locations || [];
        dispatch({ type: "SET_SETTLEMENTS", payload: items });
      }
    } catch (err) {
      console.error("Failed to fetch settlements:", err);
      dispatch({ type: "SET_LOADING", payload: { key: "settlements", value: false } });
    }
  }, []);

  const fetchRoads = useCallback(async (districtId) => {
    dispatch({ type: "SET_LOADING", payload: { key: "roads", value: true } });
    try {
      const districts = districtId ? [districtId] : state.districts.map((d) => d.id);
      const responses = await Promise.all(districts.map((id) => fetch(`/api/districts/${id}/roads`)));
      const data = await Promise.all(responses.filter((resp) => resp.ok).map((resp) => resp.json()));
      dispatch({ type: "SET_ROADS", payload: data.flatMap((item) => item.roads || []) });
    } catch (err) {
      console.error("Failed to fetch roads:", err);
      dispatch({ type: "SET_LOADING", payload: { key: "roads", value: false } });
    }
  }, [state.districts]);

  const fetchBridges = useCallback(async (districtId) => {
    dispatch({ type: "SET_LOADING", payload: { key: "bridges", value: true } });
    try {
      const districts = districtId ? [districtId] : state.districts.map((d) => d.id);
      const responses = await Promise.all(districts.map((id) => fetch(`/api/districts/${id}/bridges`)));
      const data = await Promise.all(responses.filter((resp) => resp.ok).map((resp) => resp.json()));
      dispatch({ type: "SET_BRIDGES", payload: data.flatMap((item) => item.bridges || []) });
    } catch (err) {
      console.error("Failed to fetch bridges:", err);
      dispatch({ type: "SET_LOADING", payload: { key: "bridges", value: false } });
    }
  }, [state.districts]);

  const fetchMedicalFacilities = useCallback(async (districtId) => {
    dispatch({ type: "SET_LOADING", payload: { key: "medicalFacilities", value: true } });
    try {
      const districts = districtId ? [districtId] : state.districts.map((d) => d.id);
      const responses = await Promise.all(districts.map((id) => fetch(`/api/districts/${id}/medical-facilities`)));
      const data = await Promise.all(responses.filter((resp) => resp.ok).map((resp) => resp.json()));
      dispatch({ type: "SET_MEDICAL_FACILITIES", payload: data.flatMap((item) => item.facilities || []) });
    } catch (err) {
      console.error("Failed to fetch medical facilities:", err);
      dispatch({ type: "SET_LOADING", payload: { key: "medicalFacilities", value: false } });
    }
  }, [state.districts]);

  const fetchBuildings = useCallback(async (districtId, bbox, zoom) => {
    dispatch({ type: "SET_LOADING", payload: { key: "buildings", value: true } });
    try {
      // Buildings require a specific district; use selected district or null (handled by caller)
      if (!districtId) {
        dispatch({ type: "SET_LOADING", payload: { key: "buildings", value: false } });
        return;
      }
      let url = `/api/districts/${districtId}/buildings`;
      const params = new URLSearchParams();
      if (bbox) {
        params.set("west", bbox.west);
        params.set("south", bbox.south);
        params.set("east", bbox.east);
        params.set("north", bbox.north);
      }
      if (zoom != null) params.set("zoom", zoom);
      const qs = params.toString();
      if (qs) url += `?${qs}`;
      const resp = await fetch(url);
      if (resp.ok) {
        const data = await resp.json();
        dispatch({ type: "SET_BUILDINGS", payload: data });
      } else {
        dispatch({ type: "SET_LOADING", payload: { key: "buildings", value: false } });
      }
    } catch (err) {
      console.error("Failed to fetch buildings:", err);
      dispatch({ type: "SET_LOADING", payload: { key: "buildings", value: false } });
    }
  }, []);

  const fetchOrganizations = useCallback(async () => {
    dispatch({ type: "SET_LOADING", payload: { key: "organizations", value: true } });
    try {
      const resp = await fetch("/api/organizations");
      if (resp.ok) {
        const data = await resp.json();
        dispatch({ type: "SET_ORGANIZATIONS", payload: data.organizations || [] });
      } else {
        dispatch({ type: "SET_LOADING", payload: { key: "organizations", value: false } });
      }
    } catch (err) {
      console.error("Failed to fetch organizations:", err);
      dispatch({ type: "SET_LOADING", payload: { key: "organizations", value: false } });
    }
  }, []);

  const fetchIncidents = useCallback(async () => {
    try {
      const resp = await fetch("/api/incidents");
      if (resp.ok) {
        const data = await resp.json();
        dispatch({ type: "SET_INCIDENTS", payload: data.incidents || [] });
      }
    } catch (err) {
      console.error("Failed to fetch incidents:", err);
    }
  }, []);

  const fetchFloodSnapshots = useCallback(async (districtId) => {
    dispatch({ type: "SET_LOADING", payload: { key: "floodSnapshots", value: true } });
    try {
      const url = districtId
        ? `/api/flood-snapshots?district=${districtId}`
        : "/api/flood-snapshots";
      const resp = await fetch(url);
      if (resp.ok) {
        const data = await resp.json();
        dispatch({ type: "SET_FLOOD_SNAPSHOTS", payload: data.snapshots || [] });
      } else {
        dispatch({ type: "SET_LOADING", payload: { key: "floodSnapshots", value: false } });
      }
    } catch (err) {
      console.error("Failed to fetch flood snapshots:", err);
      dispatch({ type: "SET_LOADING", payload: { key: "floodSnapshots", value: false } });
    }
  }, []);

  const selectFloodSnapshot = useCallback(async (snapshot) => {
    dispatch({ type: "SET_SELECTED_FLOOD_SNAPSHOT", payload: { snapshot, data: null } });
    if (snapshot && snapshot.id) {
      try {
        const resp = await fetch(`/api/flood-snapshots/${snapshot.id}/geojson`);
        if (resp.ok) {
          const data = await resp.json();
          dispatch({ type: "SET_SELECTED_FLOOD_SNAPSHOT", payload: { snapshot, data } });
        }
      } catch (err) {
        console.error("Failed to fetch flood snapshot geojson:", err);
      }
    }
  }, []);

  const fetchNeeds = useCallback(async (filters = {}) => {
    dispatch({ type: "SET_LOADING", payload: { key: "needs", value: true } });
    try {
      const params = new URLSearchParams();
      const districtId = filters.district_id || filters.district;
      if (districtId) params.set("district_id", districtId);
      const resp = await fetch(`/api/needs?${params}`);
      if (resp.ok) {
        const data = await resp.json();
        dispatch({ type: "SET_NEEDS", payload: data.needs || [] });
      }
    } catch (err) {
      console.error("Failed to fetch needs:", err);
      dispatch({ type: "SET_LOADING", payload: { key: "needs", value: false } });
    }
  }, []);

  const fetchOffers = useCallback(async (filters = {}) => {
    dispatch({ type: "SET_LOADING", payload: { key: "offers", value: true } });
    try {
      const params = new URLSearchParams();
      const districtId = filters.district_id || filters.district;
      if (districtId) params.set("district_id", districtId);
      const resp = await fetch(`/api/offers?${params}`);
      if (resp.ok) {
        const data = await resp.json();
        dispatch({ type: "SET_OFFERS", payload: data.offers || [] });
      }
    } catch (err) {
      console.error("Failed to fetch offers:", err);
      dispatch({ type: "SET_LOADING", payload: { key: "offers", value: false } });
    }
  }, []);

  const fetchOperations = useCallback(async (filters = {}) => {
    dispatch({ type: "SET_LOADING", payload: { key: "operations", value: true } });
    try {
      const params = new URLSearchParams();
      const districtId = filters.district_id || filters.district;
      if (districtId) params.set("district_id", districtId);
      const resp = await fetch(`/api/operations?${params}`);
      if (resp.ok) {
        const data = await resp.json();
        dispatch({ type: "SET_OPERATIONS", payload: data.operations || [] });
      }
    } catch (err) {
      console.error("Failed to fetch operations:", err);
      dispatch({ type: "SET_LOADING", payload: { key: "operations", value: false } });
    }
  }, []);

  const fetchFieldReports = useCallback(async () => {
    dispatch({ type: "SET_LOADING", payload: { key: "fieldReports", value: true } });
    try {
      const resp = await fetch("/api/field-intelligence/history");
      if (resp.ok) {
        const data = await resp.json();
        dispatch({ type: "SET_FIELD_REPORTS", payload: data.reports || [] });
      }
    } catch (err) {
      console.error("Failed to fetch field reports:", err);
      dispatch({ type: "SET_LOADING", payload: { key: "fieldReports", value: false } });
    }
  }, []);

  const fetchOverrides = useCallback(async () => {
    try {
      const resp = await fetch("/api/overrides");
      if (resp.ok) {
        const data = await resp.json();
        const map = {};
        (data.overrides || []).forEach((o) => {
          if (o.active) map[o.target_id] = o;
        });
        dispatch({ type: "SET_OVERRIDES", payload: map });
      }
    } catch (err) {
      console.error("Failed to fetch overrides:", err);
    }
  }, []);

  const fetchActivity = useCallback(async () => {
    dispatch({ type: "SET_LOADING", payload: { key: "activity", value: true } });
    try {
      const resp = await fetch("/api/activity?limit=30");
      if (resp.ok) {
        const data = await resp.json();
        dispatch({ type: "SET_ACTIVITY", payload: data.events || [] });
      }
    } catch (err) {
      console.error("Failed to fetch activity:", err);
      dispatch({ type: "SET_LOADING", payload: { key: "activity", value: false } });
    }
  }, []);

  const fetchNotifications = useCallback(async () => {
    try {
      const resp = await fetch("/api/notifications");
      if (resp.ok) {
        const data = await resp.json();
        dispatch({ type: "SET_NOTIFICATIONS", payload: data.notifications || [] });
      }
    } catch (err) {
      console.error("Failed to fetch notifications:", err);
    }
  }, []);

  const fetchDelta = useCallback(async (hours = 24) => {
    dispatch({ type: "SET_DELTA_LOADING", payload: true });
    try {
      const resp = await fetch(`/api/delta?hours=${hours}`);
      if (resp.ok) {
        const data = await resp.json();
        dispatch({ type: "SET_DELTA", payload: data });
      } else {
        dispatch({ type: "SET_DELTA_LOADING", payload: false });
      }
    } catch (err) {
      console.error("Failed to fetch delta:", err);
      dispatch({ type: "SET_DELTA_LOADING", payload: false });
    }
  }, []);

  const fetchAiAnalysis = useCallback(async () => {
    dispatch({ type: "SET_AI_LOADING", payload: true });
    try {
      const resp = await fetch("/api/ai-coordinator/analysis");
      if (resp.ok) {
        const data = await resp.json();
        dispatch({ type: "SET_AI_ANALYSIS", payload: data });
      } else {
        dispatch({ type: "SET_AI_LOADING", payload: false });
      }
    } catch (err) {
      console.error("Failed to fetch AI analysis:", err);
      dispatch({ type: "SET_AI_LOADING", payload: false });
    }
  }, []);

  // --- Refresh all operational data ---
  // NOTE: Must be defined AFTER all fetch functions (was causing TDZ crash)
  const refreshAll = useCallback(async () => {
    const districtId = state.filters.district;
    await Promise.allSettled([
      fetchFloodData(districtId),
      fetchRoads(districtId),
      fetchBridges(districtId),
      fetchMedicalFacilities(districtId),
      fetchNeeds(state.filters),
      fetchOffers(state.filters),
      fetchOperations(state.filters),
      fetchFieldReports(),
      fetchOverrides(),
      fetchActivity(),
      fetchNotifications(),
      fetchAiAnalysis(),
      fetchDelta(),
      fetchOrganizations(),
      fetchIncidents(),
      fetchFloodSnapshots(districtId),
    ]);
  }, [
    state.filters,
    fetchFloodData,
    fetchRoads,
    fetchBridges,
    fetchMedicalFacilities,
    fetchNeeds,
    fetchOffers,
    fetchOperations,
    fetchFieldReports,
    fetchOverrides,
    fetchActivity,
    fetchNotifications,
    fetchAiAnalysis,
    fetchOrganizations,
    fetchIncidents,
    fetchFloodSnapshots,
  ]);

  const setSelectedEntity = useCallback((entity) => {
    dispatch({ type: "SET_SELECTED_ENTITY", payload: entity });
  }, []);

  const performSearch = useCallback((query) => {
    dispatch({ type: "SET_SEARCH_QUERY", payload: query });
    if (!query || query.length < 2) {
      dispatch({ type: "SET_SEARCH_RESULTS", payload: [] });
      return;
    }
    const q = query.toLowerCase();
    const results = [];

    // Search districts
    state.districts.forEach((d) => {
      if (d.name && d.name.toLowerCase().includes(q)) {
        results.push({ type: "district", id: d.id, name: d.name, icon: "MapPin" });
      }
    });

    // Search settlements
    state.settlements.forEach((s) => {
      if (s.name && s.name.toLowerCase().includes(q)) {
        results.push({ type: "settlement", id: s.id, name: s.name, icon: "MapPin", lat: s.lat, lon: s.lon });
      }
    });

    // Search needs
    state.needs.forEach((n) => {
      if ((n.title && n.title.toLowerCase().includes(q)) || (n.description && n.description.toLowerCase().includes(q))) {
        results.push({ type: "need", id: n.id, name: n.title, icon: "AlertTriangle", lat: n.lat, lon: n.lon, data: n });
      }
    });

    // Search operations
    state.operations.forEach((o) => {
      if (o.name && o.name.toLowerCase().includes(q)) {
        results.push({ type: "operation", id: o.id, name: o.name, icon: "Zap", lat: o.lat, lon: o.lon, data: o });
      }
    });

    // Search roads
    state.roads.forEach((r) => {
      if (r.name && r.name.toLowerCase().includes(q)) {
        results.push({ type: "road", id: r.id, name: r.name, icon: "Route" });
      }
    });

    // Search bridges
    state.bridges.forEach((b) => {
      if (b.name && b.name.toLowerCase().includes(q)) {
        results.push({ type: "bridge", id: b.id, name: b.name, icon: "Landmark" });
      }
    });

    // Search medical facilities
    state.medicalFacilities.forEach((f) => {
      if (f.name && f.name.toLowerCase().includes(q)) {
        results.push({ type: "facility", id: f.id, name: f.name, icon: "Stethoscope", lat: f.lat, lon: f.lon, data: f });
      }
    });

    // Search organizations
    state.organizations.forEach((o) => {
      if (o.name && o.name.toLowerCase().includes(q)) {
        results.push({ type: "organization", id: o.id, name: o.name, icon: "Globe", data: o });
      }
    });

    dispatch({ type: "SET_SEARCH_RESULTS", payload: results.slice(0, 20) });
  }, [state.districts, state.settlements, state.needs, state.operations, state.roads, state.bridges, state.medicalFacilities, state.organizations]);



  // --- Initial data load ---
  useEffect(() => {
    fetchDistricts();
    fetchSettlements();
    refreshAll();

    // Poll operational data every 30 seconds
    refreshRef.current = setInterval(() => {
      fetchNeeds(state.filters);
      fetchOffers(state.filters);
      fetchOperations(state.filters);
      fetchActivity();
      fetchNotifications();
      fetchAiAnalysis();
      fetchDelta();
      fetchIncidents();
      fetchOrganizations();
    }, 30000);

    return () => {
      if (refreshRef.current) clearInterval(refreshRef.current);
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // --- Refetch when filters change ---
  useEffect(() => {
    const districtId = state.filters.district;
    fetchFloodData(districtId);
    fetchSettlements(districtId);
    fetchRoads(districtId);
    fetchBridges(districtId);
    fetchMedicalFacilities(districtId);
    fetchNeeds(state.filters);
    fetchOffers(state.filters);
    fetchOperations(state.filters);
    fetchFloodSnapshots(districtId);
  }, [state.filters, state.districts, fetchFloodData, fetchSettlements, fetchRoads, fetchBridges, fetchMedicalFacilities, fetchNeeds, fetchOffers, fetchOperations, fetchFloodSnapshots]);

  // --- Action helpers ---
  const toggleLayer = useCallback((layerId) => {
    dispatch({ type: "TOGGLE_LAYER", payload: layerId });
  }, []);

  const setFilter = useCallback((key, value) => {
    dispatch({ type: "SET_FILTER", payload: { key, value } });
  }, []);

  const openPanel = useCallback((type, entityId = null, data = null) => {
    dispatch({ type: "OPEN_PANEL", payload: { type, entityId, data } });
  }, []);

  const closePanel = useCallback(() => {
    dispatch({ type: "CLOSE_PANEL" });
  }, []);

  const setMapCenter = useCallback((center) => {
    dispatch({ type: "SET_MAP_CENTER", payload: center });
  }, []);

  const value = {
    state,
    dispatch,
    toggleLayer,
    setFilter,
    openPanel,
    closePanel,
    setMapCenter,
    setSelectedEntity,
    performSearch,
    refreshAll,
    fetchFloodData,
    fetchRoads,
    fetchBridges,
    fetchMedicalFacilities,
    fetchBuildings,
    fetchNeeds,
    fetchOffers,
    fetchOperations,
    fetchFieldReports,
    fetchOverrides,
    fetchActivity,
    fetchNotifications,
    fetchAiAnalysis,
    fetchDelta,
    fetchOrganizations,
    fetchIncidents,
    fetchFloodSnapshots,
    selectFloodSnapshot,
  };

  return (
    <WorkspaceContext.Provider value={value}>
      {children}
    </WorkspaceContext.Provider>
  );
}

export function useWorkspace() {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error("useWorkspace must be used within WorkspaceProvider");
  return ctx;
}
