import { createContext, useContext, useReducer, useCallback, useEffect, useRef } from "react";

// -------------------------------------------------------------------
// Initial state
// -------------------------------------------------------------------

const initialLayers = {
  flood: true,
  roads: true,
  bridges: true,
  settlements: true,
  buildings: false,
  medical: true,
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
  needs: [],
  offers: [],
  operations: [],
  fieldReports: [],
  overrides: {},
  activity: [],
  notifications: [],

  // Loading states
  loading: {
    flood: false,
    districts: false,
    settlements: false,
    roads: false,
    bridges: false,
    needs: false,
    offers: false,
    operations: false,
    fieldReports: false,
    activity: false,
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

    case "SET_DISTRICTS":
      return { ...state, districts: action.payload, loading: { ...state.loading, districts: false } };

    case "SET_SETTLEMENTS":
      return { ...state, settlements: action.payload, loading: { ...state.loading, settlements: false } };

    case "SET_ROADS":
      return { ...state, roads: action.payload, loading: { ...state.loading, roads: false } };

    case "SET_BRIDGES":
      return { ...state, bridges: action.payload, loading: { ...state.loading, bridges: false } };

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
      if (!districtId) {
        dispatch({ type: "SET_ROADS", payload: [] });
        return;
      }
      const resp = await fetch(`/api/districts/${districtId}/roads`);
      if (resp.ok) {
        const data = await resp.json();
        dispatch({ type: "SET_ROADS", payload: data.roads || [] });
      }
    } catch (err) {
      console.error("Failed to fetch roads:", err);
      dispatch({ type: "SET_LOADING", payload: { key: "roads", value: false } });
    }
  }, []);

  const fetchBridges = useCallback(async (districtId) => {
    dispatch({ type: "SET_LOADING", payload: { key: "bridges", value: true } });
    try {
      if (!districtId) {
        dispatch({ type: "SET_BRIDGES", payload: [] });
        return;
      }
      const resp = await fetch(`/api/districts/${districtId}/bridges`);
      if (resp.ok) {
        const data = await resp.json();
        dispatch({ type: "SET_BRIDGES", payload: data.bridges || [] });
      }
    } catch (err) {
      console.error("Failed to fetch bridges:", err);
      dispatch({ type: "SET_LOADING", payload: { key: "bridges", value: false } });
    }
  }, []);

  const fetchNeeds = useCallback(async (filters = {}) => {
    dispatch({ type: "SET_LOADING", payload: { key: "needs", value: true } });
    try {
      const params = new URLSearchParams();
      if (filters.district_id) params.set("district_id", filters.district_id);
      if (filters.status) params.set("status", filters.status);
      if (filters.urgency) params.set("urgency", filters.urgency);
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
      if (filters.district_id) params.set("district_id", filters.district_id);
      if (filters.status) params.set("status", filters.status);
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
      if (filters.district_id) params.set("district_id", filters.district_id);
      if (filters.status) params.set("status", filters.status);
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

  // --- Refresh all operational data ---
  const refreshAll = useCallback(async () => {
    const districtId = state.filters.district;
    await Promise.allSettled([
      fetchFloodData(districtId),
      fetchRoads(districtId),
      fetchBridges(districtId),
      fetchNeeds(state.filters),
      fetchOffers(state.filters),
      fetchOperations(state.filters),
      fetchFieldReports(),
      fetchOverrides(),
      fetchActivity(),
      fetchNotifications(),
    ]);
  }, [
    state.filters,
    fetchFloodData,
    fetchRoads,
    fetchBridges,
    fetchNeeds,
    fetchOffers,
    fetchOperations,
    fetchFieldReports,
    fetchOverrides,
    fetchActivity,
    fetchNotifications,
  ]);

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
    fetchNeeds(state.filters);
    fetchOffers(state.filters);
    fetchOperations(state.filters);
  }, [state.filters, fetchFloodData, fetchSettlements, fetchRoads, fetchBridges, fetchNeeds, fetchOffers, fetchOperations]);

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
    refreshAll,
    fetchFloodData,
    fetchRoads,
    fetchBridges,
    fetchNeeds,
    fetchOffers,
    fetchOperations,
    fetchFieldReports,
    fetchOverrides,
    fetchActivity,
    fetchNotifications,
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
