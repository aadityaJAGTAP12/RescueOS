import { useEffect, useMemo, useCallback, useRef } from "react";
import {
  MapContainer, TileLayer, GeoJSON, Marker, Popup, useMap,
} from "react-leaflet";
import L from "leaflet";
import { Crosshair } from "lucide-react";
import { useWorkspace } from "../../lib/workspaceContext";
import { cn } from "../../lib/utils";
import { MAP_STYLES } from "../../lib/mapStyles";

// -------------------------------------------------------------------
// Marker icon factories
// -------------------------------------------------------------------

function createPinpointIcon() {
  return L.divIcon({
    className: "",
    iconSize: [36, 36],
    iconAnchor: [18, 18],
    popupAnchor: [0, -20],
    html: `<div style="position:relative;width:36px;height:36px;display:flex;align-items:center;justify-content:center;">
      <div style="position:absolute;width:36px;height:36px;border-radius:50%;background:rgba(239,68,68,0.35);border:1.5px solid #ef4444;animation:ping 1.5s cubic-bezier(0,0,0.2,1) infinite;"></div>
      <div style="width:16px;height:16px;border-radius:50%;background:#ef4444;border:2.5px solid white;box-shadow:0 0 12px rgba(239,68,68,0.9);display:flex;align-items:center;justify-content:center;">
        <div style="width:4px;height:4px;border-radius:50%;background:white;"></div>
      </div>
    </div>`,
  });
}

function createCircleIcon(color, size = 24) {
  return L.divIcon({
    className: "",
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    popupAnchor: [0, -size / 2 - 2],
    html: `<div style="width:${size}px;height:${size}px;border-radius:50%;background:${color};border:2px solid white;box-shadow:0 2px 6px rgba(0,0,0,0.4);"></div>`,
  });
}

function createDiamondIcon(color, size = 24) {
  return L.divIcon({
    className: "",
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    popupAnchor: [0, -size / 2 - 2],
    html: `<div style="width:${size}px;height:${size}px;background:${color};border:2px solid white;box-shadow:0 2px 6px rgba(0,0,0,0.4);transform:rotate(45deg);border-radius:3px;"></div>`,
  });
}

function createTriangleIcon(color, size = 20) {
  return L.divIcon({
    className: "",
    iconSize: [size, size],
    iconAnchor: [size / 2, size],
    popupAnchor: [0, -size],
    html: `<div style="width:0;height:0;border-left:${size/2}px solid transparent;border-right:${size/2}px solid transparent;border-bottom:${size}px solid ${color};filter:drop-shadow(0 2px 4px rgba(0,0,0,0.4));"></div>`,
  });
}

function createSquareIcon(color, size = 18) {
  return L.divIcon({
    className: "",
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    popupAnchor: [0, -size / 2 - 2],
    html: `<div style="width:${size}px;height:${size}px;background:${color};border:2px solid white;box-shadow:0 2px 6px rgba(0,0,0,0.4);border-radius:3px;"></div>`,
  });
}

function createStarIcon(color, size = 20) {
  return L.divIcon({
    className: "",
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    popupAnchor: [0, -size / 2 - 2],
    html: `<div style="width:${size}px;height:${size}px;display:flex;align-items:center;justify-content:center;font-size:${size-4}px;color:${color};text-shadow:0 1px 3px rgba(0,0,0,0.5);">★</div>`,
  });
}

function createFacilityIcon(hasOverride) {
  const bg = hasOverride ? "#f59e0b" : "#0891b2";
  return L.divIcon({
    className: "",
    iconSize: [26, 26],
    iconAnchor: [13, 13],
    popupAnchor: [0, -15],
    html: `<div style="width:26px;height:26px;border-radius:50%;background:${bg};border:2px solid white;box-shadow:0 2px 6px rgba(0,0,0,0.4);display:flex;align-items:center;justify-content:center;">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5"><path d="M8 2h8l4 10H4L8 2z"/><path d="M12 12v4"/><path d="M8 20h8"/><path d="M12 16h.01"/></svg>
    </div>`,
  });
}

function createAiAlertIcon(severity = "medium") {
  const colors = {
    critical: "#dc2626",
    high: "#f97316",
    medium: "#eab308",
    low: "#22c55e",
  };
  const color = colors[severity] || colors.medium;
  return L.divIcon({
    className: "",
    iconSize: [28, 28],
    iconAnchor: [14, 14],
    popupAnchor: [0, -16],
    html: `<div style="width:28px;height:28px;border-radius:50%;background:${color};border:2px solid white;box-shadow:0 0 10px ${color}aa, 0 2px 6px rgba(0,0,0,0.4);display:flex;align-items:center;justify-content:center;color:white;font-size:13px;font-weight:bold;">!</div>`,
  });
}

// -------------------------------------------------------------------
// Fly-to handler
// -------------------------------------------------------------------

function FlyTo({ center, zoom }) {
  const map = useMap();
  useEffect(() => {
    if (center) {
      map.flyTo(center, zoom || map.getZoom(), { duration: 1.0 });
    }
  }, [center, zoom, map]);
  return null;
}

// -------------------------------------------------------------------
// Map moveend handler for viewport-aware loading
// -------------------------------------------------------------------

function MapMoveHandler({ onMoveEnd }) {
  const map = useMap();
  useEffect(() => {
    const handler = () => {
      if (onMoveEnd) onMoveEnd(map);
    };
    map.on("moveend", handler);
    return () => map.off("moveend", handler);
  }, [map, onMoveEnd]);
  return null;
}

// -------------------------------------------------------------------
// Right-click handler for report creation
// -------------------------------------------------------------------

function RightClickHandler({ onReportAt }) {
  const map = useMap();
  useEffect(() => {
    const handler = (e) => {
      onReportAt(e.latlng.lat, e.latlng.lng);
    };
    map.on("contextmenu", handler);
    return () => map.off("contextmenu", handler);
  }, [map, onReportAt]);
  return null;
}

// -------------------------------------------------------------------
// Pinpoint map click handler
// -------------------------------------------------------------------

function MapClickHandler({ onMapClick, isPinpointing }) {
  const map = useMap();
  useEffect(() => {
    if (!map) return;
    const handler = (e) => {
      if (isPinpointing && e.latlng) {
        onMapClick(e.latlng.lat, e.latlng.lng);
      }
    };
    map.on("click", handler);
    return () => map.off("click", handler);
  }, [map, isPinpointing, onMapClick]);
  return null;
}

// -------------------------------------------------------------------
// Flood detail popup
// -------------------------------------------------------------------

function FloodPopup({ snapshot }) {
  return (
    <div className="p-3 min-w-[200px]">
      <div className="text-[13px] font-semibold text-stone-800 mb-1">
        Flood Snapshot
      </div>
      <div className="text-[11px] text-stone-500 space-y-0.5">
        <div>District: {snapshot.district_id}</div>
        <div>Polygons: {snapshot.polygon_count}</div>
        <div>Observed: {snapshot.observed_at}</div>
        <div>Source: {snapshot.source}</div>
        <div>Confidence: {snapshot.confidence}</div>
      </div>
    </div>
  );
}

// -------------------------------------------------------------------
// Need marker
// -------------------------------------------------------------------

function createNeedMarkerIcon(urgency) {
  const u = String(urgency || "medium").toLowerCase();
  const urgencyColors = {
    critical: "#ef4444",
    high: "#f97316",
    medium: "#eab308",
    low: "#22c55e",
  };
  const color = urgencyColors[u] || "#78716c";
  const size = u === "critical" ? 28 : u === "high" ? 24 : 20;
  const isCritical = u === "critical";

  return L.divIcon({
    className: "",
    iconSize: [size + 16, size + 16],
    iconAnchor: [(size + 16) / 2, (size + 16) / 2],
    popupAnchor: [0, -(size + 16) / 2 - 2],
    html: `<div style="position:relative;width:${size + 16}px;height:${size + 16}px;display:flex;align-items:center;justify-content:center;">
      ${isCritical ? `<div style="position:absolute;width:${size + 16}px;height:${size + 16}px;border-radius:50%;background:rgba(239,68,68,0.35);border:1.5px solid #ef4444;animation:ping 1.5s cubic-bezier(0,0,0.2,1) infinite;"></div>` : ""}
      <div style="width:${size}px;height:${size}px;border-radius:50%;background:${color};border:2px solid white;box-shadow:0 0 10px ${color}99, 0 2px 6px rgba(0,0,0,0.5);display:flex;align-items:center;justify-content:center;color:white;font-size:${size > 22 ? 11 : 9}px;font-weight:bold;">
        ${isCritical ? "!" : ""}
      </div>
    </div>`,
  });
}

function NeedMarker({ need, position, onClick }) {
  const pos = position || need._pos || (need.lat && need.lon ? [need.lat, need.lon] : null);
  if (!pos || !pos[0] || !pos[1]) return null;

  const urgencyColors = {
    critical: "#ef4444",
    high: "#f97316",
    medium: "#eab308",
    low: "#22c55e",
  };
  const u = String(need.urgency || "medium").toLowerCase();
  const color = urgencyColors[u] || "#78716c";

  return (
    <Marker
      position={pos}
      icon={createNeedMarkerIcon(need.urgency)}
      eventHandlers={{ click: () => onClick("need", need.id, need) }}
    >
      <Popup>
        <div className="p-2 min-w-[180px]">
          <div className="text-[13px] font-semibold text-stone-800 mb-1">{need.title}</div>
          <div className="text-[11px] text-stone-500">
            <span className="font-medium uppercase" style={{ color }}>{need.urgency}</span> · {need.need_type}
          </div>
          <div className="text-[10px] text-stone-400 mt-1">Status: {need.status}</div>
          {need.location_name && (
            <div className="text-[10px] text-stone-400">📍 {need.location_name}</div>
          )}
          {need.district_id && (
            <div className="text-[10px] text-stone-400 capitalize">District: {need.district_id}</div>
          )}
        </div>
      </Popup>
    </Marker>
  );
}

// -------------------------------------------------------------------
// Operation marker
// -------------------------------------------------------------------

function OperationMarker({ operation, position, onClick }) {
  const pos = position || operation._pos || (operation.lat && operation.lon ? [operation.lat, operation.lon] : null);
  if (!pos || !pos[0] || !pos[1]) return null;

  const statusColor = {
    PLANNING: "#2563eb",
    ACTIVE: "#16a34a",
    PAUSED: "#d97706",
    COMPLETED: "#6b7280",
    CANCELLED: "#9ca3af",
  };
  const color = statusColor[operation.status] || "#6b7280";

  return (
    <Marker
      position={pos}
      icon={createDiamondIcon(color, 24)}
      eventHandlers={{ click: () => onClick("operation", operation.id, operation) }}
    >
      <Popup>
        <div className="p-2 min-w-[180px]">
          <div className="text-[13px] font-semibold text-stone-800 mb-1">{operation.name}</div>
          <div className="text-[11px] text-stone-500">{operation.operation_type} · {operation.status}</div>
          {operation.location_name && (
            <div className="text-[10px] text-stone-400 mt-1">📍 {operation.location_name}</div>
          )}
          {operation.district_id && (
            <div className="text-[10px] text-stone-400 capitalize">District: {operation.district_id}</div>
          )}
        </div>
      </Popup>
    </Marker>
  );
}

// -------------------------------------------------------------------
// Offer marker
// -------------------------------------------------------------------

function OfferMarker({ offer, position, onClick }) {
  const pos = position || offer._pos || (offer.lat && offer.lon ? [offer.lat, offer.lon] : null);
  if (!pos || !pos[0] || !pos[1]) return null;

  return (
    <Marker
      position={pos}
      icon={createTriangleIcon("#0d9488", 20)}
      eventHandlers={{ click: () => onClick("offer", offer.id, offer) }}
    >
      <Popup>
        <div className="p-2 min-w-[180px]">
          <div className="text-[13px] font-semibold text-stone-800 mb-1">{offer.resource_type}</div>
          <div className="text-[11px] text-stone-500">
            {offer.quantity} {offer.unit} · {offer.status}
          </div>
          {offer.location_name && (
            <div className="text-[10px] text-stone-400 mt-1">📍 {offer.location_name}</div>
          )}
          {offer.district_id && (
            <div className="text-[10px] text-stone-400 capitalize">District: {offer.district_id}</div>
          )}
        </div>
      </Popup>
    </Marker>
  );
}

// -------------------------------------------------------------------
// Field report marker
// -------------------------------------------------------------------

function FieldReportMarker({ report, onClick }) {
  const verified = report.verified || report.source === "field_intelligence_text";
  const color = verified ? "#16a34a" : "#4f46e5";
  const label = report.note || report.raw_text || `${report.people_count} people`;

  return (
    <Marker
      position={[report.lat, report.lon]}
      icon={createSquareIcon(color, 18)}
      eventHandlers={{ click: () => onClick("report", report.id, report) }}
    >
      <Popup>
        <div className="p-2 min-w-[180px]">
          <div className="text-[13px] font-semibold text-stone-800 mb-1">
            {report.people_count} people reported
          </div>
          <div className="text-[11px] text-stone-500">
            {report.needs?.join(", ") || "No specific needs"}
          </div>
          {!verified && (
            <div className="text-[10px] text-amber-600 font-semibold mt-1">⚠ Unverified</div>
          )}
        </div>
      </Popup>
    </Marker>
  );
}

// -------------------------------------------------------------------
// Medical facility marker
// -------------------------------------------------------------------

function FacilityMarker({ facility, override, onClick }) {
  return (
    <Marker
      position={[facility.lat, facility.lon]}
      icon={createFacilityIcon(!!override)}
      eventHandlers={{ click: () => onClick("facility", facility.id, facility) }}
    >
      <Popup>
        <div className="p-2 min-w-[180px]">
          <div className="text-[13px] font-semibold text-stone-800 mb-1">{facility.name}</div>
          <div className="text-[11px] text-stone-500">{facility.facility_type}</div>
          {override && (
            <div className="mt-1 px-2 py-1 rounded bg-amber-50 border border-amber-200/60">
              <div className="text-[10px] font-semibold text-amber-700">
                Override: {override.override_status}
              </div>
              <div className="text-[10px] text-amber-600">{override.reason}</div>
            </div>
          )}
        </div>
      </Popup>
    </Marker>
  );
}

// -------------------------------------------------------------------
// Settlement marker
// -------------------------------------------------------------------

function SettlementMarker({ settlement, onClick }) {
  return (
    <Marker
      position={[settlement.lat, settlement.lon]}
      icon={createCircleIcon("#78716c", 10)}
      eventHandlers={{ click: () => onClick("settlement", settlement.id, settlement) }}
    >
      <Popup>
        <div className="p-2 min-w-[150px]">
          <div className="text-[12px] font-semibold text-stone-800">{settlement.name}</div>
          <div className="text-[10px] text-stone-400">{settlement.district_id}</div>
        </div>
      </Popup>
    </Marker>
  );
}

// -------------------------------------------------------------------
// AI Alert finding marker
// -------------------------------------------------------------------

function AIAlertMarker({ finding, onClick }) {
  const colors = {
    critical: "#dc2626",
    high: "#f97316",
    medium: "#eab308",
    low: "#22c55e",
  };
  const color = colors[finding.severity] || colors.medium;

  let lat = finding.lat || finding.review_target?.map_center?.[0];
  let lon = finding.lon || finding.review_target?.map_center?.[1];

  if (!lat || !lon) {
    const districtCoords = {
      sivasagar: [26.98, 94.63],
      jorhat: [26.75, 94.22],
      golaghat: [26.52, 93.97],
      charaideo: [27.02, 94.85],
    };
    const center = districtCoords[finding.district_id] || [26.98, 94.63];
    lat = center[0];
    lon = center[1];
  }

  return (
    <Marker
      position={[lat, lon]}
      icon={createAiAlertIcon(finding.severity)}
      eventHandlers={{
        click: () => {
          if (onClick) {
            onClick("aiAnalysis", finding.id, finding);
          }
        },
      }}
    >
      <Popup>
        <div className="p-2 min-w-[200px]">
          <div className="flex items-center gap-1.5 mb-1">
            <span
              className="px-1.5 py-0.5 rounded text-[9px] font-bold uppercase"
              style={{ color, backgroundColor: `${color}15`, border: `1px solid ${color}40` }}
            >
              {finding.severity}
            </span>
            <span className="text-[10px] text-stone-500 capitalize">{finding.type}</span>
          </div>
          <div className="text-[13px] font-semibold text-stone-800 mb-1">{finding.title}</div>
          <div className="text-[11px] text-stone-600 leading-snug">{finding.description}</div>
          {finding.recommended_action && (
            <div className="text-[10px] text-stone-500 mt-1.5 pt-1 border-t border-stone-200">
              <span className="font-semibold">Action:</span> {finding.recommended_action}
            </div>
          )}
        </div>
      </Popup>
    </Marker>
  );
}

// -------------------------------------------------------------------
// Road GeoJSON layer with status coloring
// -------------------------------------------------------------------

function RoadLayer({ roads, overrides, visible, onRoadClick }) {
  if (!visible || !roads || roads.length === 0) return null;

  const features = roads
    .filter((r) => r.geometry_coords && r.geometry_coords.length >= 2)
    .map((road) => {
      // Use backend-provided operational_status if available, otherwise compute locally
      let status = road.operational_status;
      if (!status) {
        const override = overrides[road.name] || overrides[road.id];
        const isBlocked = override?.override_status === "blocked" || override?.override_status === "submerged";
        status = isBlocked ? "blocked" : road.flood_affected ? "uncertain" : "open";
      }

      const styleSet = road.is_bridge ? MAP_STYLES.bridge : MAP_STYLES.road;
      const styleKey = (status === "blocked" || status === "submerged" || status === "damaged")
        ? "blocked"
        : status === "uncertain"
        ? "uncertain"
        : "open";
      const resolved = styleSet[styleKey] || styleSet.open;

      return {
        type: "Feature",
        properties: {
          id: road.id,
          name: road.name || "Unnamed road",
          highway_type: road.highway_type,
          is_bridge: road.is_bridge,
          status,
          color: resolved.color,
        },
        geometry: {
          type: "LineString",
          coordinates: road.geometry_coords,
        },
      };
    });

  if (features.length === 0) return null;

  return (
    <GeoJSON
      key={`roads-${features.length}`}
      data={{ type: "FeatureCollection", features }}
      style={(feature) => {
        const styleSet = feature.properties.is_bridge ? MAP_STYLES.bridge : MAP_STYLES.road;
        const styleKey = (feature.properties.status === "blocked" || feature.properties.status === "submerged" || feature.properties.status === "damaged")
          ? "blocked"
          : feature.properties.status === "uncertain"
          ? "uncertain"
          : "open";
        const resolved = styleSet[styleKey] || styleSet.open;
        return {
          color: resolved.color,
          weight: resolved.width,
          opacity: 0.7,
          dashArray: resolved.dash ? resolved.dash.join(', ') : null,
        };
      }}
      onEachFeature={(feature, layer) => {
        const p = feature.properties;
        layer.bindPopup(
          `<div style="padding:8px;min-width:150px;">
            <div style="font-size:12px;font-weight:600;color:#1e293b;margin-bottom:4px;">${p.name}</div>
            <div style="font-size:11px;color:#64748b;">Type: ${p.highway_type}</div>
            <div style="font-size:11px;color:#64748b;">Status: <span style="color:${p.color};font-weight:600;">${p.status.toUpperCase()}</span></div>
            ${p.is_bridge ? '<div style="font-size:10px;color:#94a3b8;margin-top:2px;">🌉 Bridge</div>' : ""}
          </div>`
        );
        layer.on("click", () => {
          if (onRoadClick) onRoadClick(p);
        });
      }}
    />
  );
}

// -------------------------------------------------------------------
// Main MapCanvas component
// -------------------------------------------------------------------

export default function MapCanvas() {
  const {
    state,
    openPanel,
    setFilter,
    toggleLayer,
    setMapCenter,
    fetchFieldReports,
    fetchBuildings,
    setPinpointCoords,
    cancelPinpoint,
  } = useWorkspace();

  // Pinpoint click handler
  const handlePinpointClick = useCallback((lat, lng) => {
    const latFormatted = parseFloat(lat.toFixed(6));
    const lonFormatted = parseFloat(lng.toFixed(6));
    setPinpointCoords({ lat: latFormatted, lon: lonFormatted });
  }, [setPinpointCoords]);

  // Handle ESC key to cancel pinpoint
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === "Escape" && state.pinpointMode?.active) {
        cancelPinpoint();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [state.pinpointMode?.active, cancelPinpoint]);

  // Viewport-aware building loading
  const handleMapMoveEnd = useCallback((map) => {
    if (!state.layers.buildings) return;
    if (!map) return;
    const bounds = map.getBounds();
    const zoom = map.getZoom();
    // For buildings, use the selected district; if ALL, use the first district
    const districtId = state.filters.district || (state.districts.length > 0 ? state.districts[0].id : null);
    if (!districtId) return;
    // Only load buildings at zoom >= 13 to avoid massive loads
    if (zoom < 13) {
      return;
    }
    const bbox = {
      west: bounds.getWest(),
      south: bounds.getSouth(),
      east: bounds.getEast(),
      north: bounds.getNorth(),
    };
    fetchBuildings(districtId, bbox, zoom);
  }, [state.layers.buildings, state.filters.district, state.districts, fetchBuildings]);

  // Load buildings when layer is toggled on (only at zoom >= 13)
  useEffect(() => {
    if (state.layers.buildings && state.districts.length > 0 && state.mapZoom >= 13) {
      handleMapMoveEnd();
    }
  }, [state.layers.buildings, state.districts.length]);

  // Handle map object click → open context panel
  const handleObjectClick = useCallback(
    (type, entityId, data) => {
      openPanel(type, entityId, data);
    },
    [openPanel]
  );

  // Handle right-click for report creation
  const handleReportAt = useCallback(
    (lat, lng) => {
      openPanel("createReport", null, { lat, lon: lng });
    },
    [openPanel]
  );

  const center = useMemo(() => state.mapCenter, [state.mapCenter]);
  const zoom = state.mapZoom;

  // Filter settlements by district
  const visibleSettlements = useMemo(() => {
    if (!state.filters.district) return state.settlements;
    return state.settlements.filter(
      (s) => s.district_id === state.filters.district
    );
  }, [state.settlements, state.filters.district]);

  // District centroids for geographic coordinate resolution
  const DISTRICT_CENTERS = {
    sivasagar: [26.98, 94.63],
    jorhat: [26.75, 94.22],
    golaghat: [26.52, 93.97],
    charaideo: [27.02, 94.85],
  };

  const getEntityCoordinates = useCallback((entity, idx = 0) => {
    if (entity.lat && entity.lon && !isNaN(entity.lat) && !isNaN(entity.lon)) {
      return [entity.lat, entity.lon];
    }
    if (entity.location_name) {
      const locLower = String(entity.location_name).toLowerCase();
      const sMatch = state.settlements.find(
        (s) => s.name?.toLowerCase() === locLower || s.id?.toLowerCase() === locLower
      );
      if (sMatch && sMatch.lat && sMatch.lon) {
        return [sMatch.lat, sMatch.lon];
      }
    }
    const districtKey = String(entity.district_id || "jorhat").toLowerCase();
    const base = DISTRICT_CENTERS[districtKey] || [26.85, 94.35];
    const idStr = String(entity.id || idx);
    let hash = 0;
    for (let i = 0; i < idStr.length; i++) {
      hash = (hash << 5) - hash + idStr.charCodeAt(i);
      hash |= 0;
    }
    const angle = ((Math.abs(hash) % 360) * Math.PI) / 180;
    const distance = 0.012 + ((Math.abs(hash >> 3) % 4) * 0.008);
    return [base[0] + Math.sin(angle) * distance, base[1] + Math.cos(angle) * distance];
  }, [state.settlements]);

  // Compute counts for active filters and HUD chips
  const urgencyCounts = useMemo(() => {
    const counts = { critical: 0, high: 0, medium: 0, low: 0, total: 0 };
    state.needs.forEach((n) => {
      if (state.filters.district && n.district_id !== state.filters.district) return;
      const u = String(n.urgency || "").toLowerCase();
      if (counts[u] !== undefined) counts[u]++;
      counts.total++;
    });
    return counts;
  }, [state.needs, state.filters.district]);

  const statusCounts = useMemo(() => {
    const counts = { OPEN: 0, RESPONDING: 0, RESOLVED: 0, total: 0 };
    state.needs.forEach((n) => {
      if (state.filters.district && n.district_id !== state.filters.district) return;
      const s = String(n.status || "").toUpperCase();
      if (counts[s] !== undefined) counts[s]++;
      counts.total++;
    });
    return counts;
  }, [state.needs, state.filters.district]);

  // Filter needs by district, urgency, and status
  const visibleNeeds = useMemo(() => {
    let filtered = state.needs;
    if (state.filters.district) {
      filtered = filtered.filter((n) => n.district_id === state.filters.district);
    }
    if (state.filters.urgency) {
      filtered = filtered.filter(
        (n) => String(n.urgency).toLowerCase() === String(state.filters.urgency).toLowerCase()
      );
    }
    if (state.filters.status) {
      filtered = filtered.filter(
        (n) => String(n.status).toUpperCase() === String(state.filters.status).toUpperCase()
      );
    }
    return filtered.map((n, idx) => ({
      ...n,
      _pos: getEntityCoordinates(n, idx),
    }));
  }, [state.needs, state.filters, getEntityCoordinates]);

  // Filter operations by district and status
  const visibleOperations = useMemo(() => {
    let filtered = state.operations;
    if (state.filters.district) {
      filtered = filtered.filter((o) => o.district_id === state.filters.district);
    }
    if (state.filters.status) {
      const statusMap = { OPEN: "PLANNING", RESPONDING: "ACTIVE", RESOLVED: "COMPLETED" };
      const targetStatus = statusMap[state.filters.status] || state.filters.status;
      filtered = filtered.filter(
        (o) => String(o.status).toUpperCase() === String(targetStatus).toUpperCase()
      );
    }
    return filtered.map((o, idx) => ({
      ...o,
      _pos: getEntityCoordinates(o, idx),
    }));
  }, [state.operations, state.filters, getEntityCoordinates]);

  // Filter offers by district and status
  const visibleOffers = useMemo(() => {
    let filtered = state.offers;
    if (state.filters.district) {
      filtered = filtered.filter((o) => o.district_id === state.filters.district);
    }
    if (state.filters.status) {
      const statusMap = {
        OPEN: ["OFFERED", "AVAILABLE"],
        RESPONDING: ["ACCEPTED", "ALLOCATED", "COMMITTED"],
        RESOLVED: ["DEPLETED", "CLOSED", "FULFILLED"],
      };
      const allowed = statusMap[state.filters.status] || [state.filters.status];
      filtered = filtered.filter((o) => allowed.includes(String(o.status).toUpperCase()));
    }
    return filtered.map((o, idx) => ({
      ...o,
      _pos: getEntityCoordinates(o, idx),
    }));
  }, [state.offers, state.filters, getEntityCoordinates]);

  // Filter field reports by district, urgency, and status
  const visibleReports = useMemo(() => {
    let reports = state.fieldReports.filter((r) => r.lat && r.lon);
    if (state.filters.district) {
      const districtSettlements = state.settlements.filter(
        (s) => s.district_id === state.filters.district
      );
      if (districtSettlements.length > 0) {
        const lats = districtSettlements.map((s) => s.lat);
        const lons = districtSettlements.map((s) => s.lon);
        const minLat = Math.min(...lats) - 0.15;
        const maxLat = Math.max(...lats) + 0.15;
        const minLon = Math.min(...lons) - 0.15;
        const maxLon = Math.max(...lons) + 0.15;
        reports = reports.filter(
          (r) => r.lat >= minLat && r.lat <= maxLat && r.lon >= minLon && r.lon <= maxLon
        );
      }
    }
    if (state.filters.urgency) {
      reports = reports.filter(
        (r) => !r.urgency || String(r.urgency).toLowerCase() === String(state.filters.urgency).toLowerCase()
      );
    }
    if (state.filters.status) {
      reports = reports.filter(
        (r) => !r.status || String(r.status).toUpperCase() === String(state.filters.status).toUpperCase()
      );
    }
    return reports;
  }, [state.fieldReports, state.settlements, state.filters]);

  return (
    <div className={cn("flex-1 relative", state.pinpointMode?.active && "cursor-crosshair")}>
      <MapContainer
        center={center}
        zoom={zoom}
        style={{ height: "100%", width: "100%" }}
        scrollWheelZoom={true}
        zoomControl={false}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>'
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        />

        <FlyTo center={center} zoom={zoom} />
        <RightClickHandler onReportAt={handleReportAt} />
        <MapClickHandler onMapClick={handlePinpointClick} isPinpointing={Boolean(state.pinpointMode?.active)} />
        <MapMoveHandler onMoveEnd={handleMapMoveEnd} />

        {/* Pinpoint Preview Marker */}
        {state.pinpointMode?.coords && (
          <Marker
            position={[state.pinpointMode.coords.lat, state.pinpointMode.coords.lon]}
            icon={createPinpointIcon()}
          >
            <Popup>
              <div className="p-2 min-w-[150px]">
                <div className="text-[12px] font-semibold text-red-600 flex items-center gap-1">
                  📍 Pinpointed Coordinates
                </div>
                <div className="text-[11px] font-mono text-stone-700 mt-1">
                  Lat: {state.pinpointMode.coords.lat}
                </div>
                <div className="text-[11px] font-mono text-stone-700">
                  Lon: {state.pinpointMode.coords.lon}
                </div>
              </div>
            </Popup>
          </Marker>
        )}

        {/* Flood layer (current / default) */}
        {state.layers.flood && !state.layers.floodHistory && state.floodData && state.floodData.features && state.floodData.features.length > 0 && (
          <GeoJSON
            key={`flood-${state.filters.district || 'all'}`}
            data={state.floodData}
            style={(feature) => {
              // Color by district for visual distinction in ALL view
              const districtColors = {
                sivasagar: { fill: '#0891b2', stroke: '#0891b2' },
                jorhat: { fill: '#0284c7', stroke: '#0284c7' },
                charaideo: { fill: '#6366f1', stroke: '#6366f1' },
                golaghat: { fill: '#0d9488', stroke: '#0d9488' },
              };
              const did = feature?.properties?.district_id;
              const colors = did && districtColors[did] ? districtColors[did] : { fill: '#0891b2', stroke: '#0891b2' };
              return {
                fillColor: colors.fill,
                fillOpacity: 0.15,
                color: colors.stroke,
                weight: 1.5,
                opacity: 0.5,
              };
            }}
          />
        )}

        {/* Flood History layer (selected snapshot) */}
        {state.layers.floodHistory && state.selectedFloodData && (
          <GeoJSON
            key={`flood-history-${state.selectedFloodSnapshot?.id}`}
            data={state.selectedFloodData}
            style={() => ({ ...floodStyle, fillColor: "#0e7490", color: "#0e7490" })}
          />
        )}

        {/* Roads layer */}
        <RoadLayer
          roads={state.roads.filter((road) => state.layers.bridges || !road.is_bridge)}
          overrides={state.overrides}
          visible={state.layers.roads || state.layers.bridges}
          onRoadClick={(roadProps) => handleObjectClick("road", roadProps.id, roadProps)}
        />

        {/* Settlements layer */}
        {state.layers.settlements &&
          visibleSettlements.map((s) => (
            <SettlementMarker
              key={s.id}
              settlement={s}
              onClick={handleObjectClick}
            />
          ))}

        {/* Buildings layer (viewport-bounded point markers) */}
        {state.layers.buildings && state.buildings.length > 0 &&
          state.buildings.slice(0, 2000).map((b) => (
            <Marker
              key={b.id}
              position={[b.geometry.coordinates[1], b.geometry.coordinates[0]]}
              icon={createSquareIcon(b.properties?.in_flood_zone ? "#dc2626" : "#a8a29e", 6)}
              eventHandlers={{ click: () => handleObjectClick("building", b.id, { id: b.id, ...b.properties }) }}
            />
          ))}

        {/* Needs layer */}
        {state.layers.needs &&
          visibleNeeds.map((need) => (
            <NeedMarker key={need.id} need={need} position={need._pos} onClick={handleObjectClick} />
          ))}

        {/* Operations layer */}
        {state.layers.operations &&
          visibleOperations.map((op) => (
            <OperationMarker key={op.id} operation={op} position={op._pos} onClick={handleObjectClick} />
          ))}

        {/* Offers layer */}
        {state.layers.offers &&
          visibleOffers.map((offer) => (
            <OfferMarker key={offer.id} offer={offer} position={offer._pos} onClick={handleObjectClick} />
          ))}

        {/* Medical facilities layer */}
        {state.layers.medical && state.medicalFacilities.map((facility) => (
          <FacilityMarker
            key={facility.id}
            facility={facility}
            override={state.overrides[facility.id]}
            onClick={handleObjectClick}
          />
        ))}

        {/* Organizations layer */}
        {state.layers.organizations &&
          state.organizations.map((org, idx) => {
            const districtCenters = [
              [26.98, 94.63], // Sivasagar
              [26.75, 94.22], // Jorhat
              [26.52, 93.97], // Golaghat
              [27.02, 94.85], // Charaideo
            ];
            const base = districtCenters[idx % districtCenters.length];
            const offset = (Math.floor(idx / districtCenters.length)) * 0.03;
            const pos = [base[0] + offset, base[1] + offset];

            return (
              <Marker
                key={org.id}
                position={pos}
                icon={createCircleIcon("#2563eb", 20)}
                eventHandlers={{ click: () => handleObjectClick("organization", org.id, org) }}
              >
                <Popup>
                  <div className="p-2 min-w-[180px]">
                    <div className="text-[13px] font-semibold text-stone-800 mb-0.5">{org.name}</div>
                    <div className="text-[11px] text-blue-600 font-medium capitalize">{org.organization_type || "NGO"}</div>
                    {org.description && (
                      <div className="text-[10px] text-stone-500 mt-1 line-clamp-2">{org.description}</div>
                    )}
                    {org.published_capabilities && org.published_capabilities.length > 0 && (
                      <div className="text-[9px] text-stone-400 mt-1">
                        Capabilities: {org.published_capabilities.join(", ")}
                      </div>
                    )}
                  </div>
                </Popup>
              </Marker>
            );
          })}

        {/* Field reports layer */}
        {state.layers.fieldReports &&
          visibleReports.map((report) => (
            <FieldReportMarker
              key={report.id || report.report_id}
              report={report}
              onClick={handleObjectClick}
            />
          ))}

        {/* AI Alerts layer */}
        {state.layers.aiAlerts &&
          (state.aiAnalysis?.findings || []).map((finding, idx) => (
            <AIAlertMarker
              key={finding.id || idx}
              finding={finding}
              onClick={handleObjectClick}
            />
          ))}
      </MapContainer>

      {/* Map overlay: Osiris / World Monitor Operational Lens Filter Bar */}
      <div className="absolute top-2 left-1/2 -translate-x-1/2 z-[1000] flex flex-col items-center gap-1.5 max-w-[95vw]">
        <div className="flex items-center gap-1.5 px-3 py-1.5 bg-[#0b0f17]/95 backdrop-blur-md rounded-lg border border-[#2a3a4e] shadow-xl">
          <div className="text-[10px] font-bold text-[#64748b] uppercase tracking-wider mr-1 flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
            LENS:
          </div>

          {/* Urgency Filters */}
          <FilterChip
            label={`All Urgency (${urgencyCounts.total})`}
            active={!state.filters.urgency}
            onClick={() => setFilter("urgency", null)}
          />
          {[
            { id: "critical", label: `Critical (${urgencyCounts.critical})`, color: "#ef4444" },
            { id: "high", label: `High (${urgencyCounts.high})`, color: "#f97316" },
            { id: "medium", label: `Medium (${urgencyCounts.medium})`, color: "#eab308" },
            { id: "low", label: `Low (${urgencyCounts.low})`, color: "#22c55e" },
          ].map(({ id, label, color }) => (
            <FilterChip
              key={id}
              label={label}
              active={String(state.filters.urgency).toLowerCase() === id}
              onClick={() => {
                const next = String(state.filters.urgency).toLowerCase() === id ? null : id;
                setFilter("urgency", next);
                if (next && !state.layers.needs) toggleLayer("needs");
              }}
              color={color}
            />
          ))}

          <div className="w-[1px] h-4 bg-[#2a3a4e] mx-1" />

          {/* Status Filters */}
          <FilterChip
            label="All Status"
            active={!state.filters.status}
            onClick={() => setFilter("status", null)}
          />
          {[
            { id: "OPEN", label: `Open (${statusCounts.OPEN})`, color: "#ef4444" },
            { id: "RESPONDING", label: `Responding (${statusCounts.RESPONDING})`, color: "#3b82f6" },
            { id: "RESOLVED", label: `Resolved (${statusCounts.RESOLVED})`, color: "#22c55e" },
          ].map(({ id, label, color }) => (
            <FilterChip
              key={id}
              label={label}
              active={state.filters.status === id}
              onClick={() => {
                const next = state.filters.status === id ? null : id;
                setFilter("status", next);
                if (next && !state.layers.needs) toggleLayer("needs");
                if (next && !state.layers.operations) toggleLayer("operations");
              }}
              color={color}
            />
          ))}
        </div>

        {/* Active Operational Filter Indicator */}
        {(state.filters.urgency || state.filters.status) && (
          <div className="flex items-center gap-2 px-2.5 py-1 bg-[#1e293b]/95 backdrop-blur-sm rounded-full border border-sky-500/40 text-[10px] text-sky-300 shadow-lg animate-in fade-in slide-in-from-top-1 duration-200">
            <span className="font-semibold uppercase tracking-wide flex items-center gap-1">
              ⚡ ACTIVE VIEW: {state.filters.urgency ? `${state.filters.urgency} urgency` : ""} {state.filters.urgency && state.filters.status ? "·" : ""} {state.filters.status ? `${state.filters.status} status` : ""}
            </span>
            <span className="text-stone-400">({visibleNeeds.length} needs, {visibleOperations.length} ops visible)</span>
            <button
              onClick={() => {
                setFilter("urgency", null);
                setFilter("status", null);
              }}
              className="ml-1 px-1.5 py-0.5 rounded bg-sky-950/80 hover:bg-sky-900 text-sky-200 hover:text-white border border-sky-500/30 text-[9px] font-bold transition-colors"
            >
              Reset Lens ✕
            </button>
          </div>
        )}
      </div>

      {/* Pinpoint Mode HUD Banner (Osiris / World Monitor style) */}
      {state.pinpointMode?.active && (
        <div className="absolute top-12 left-1/2 -translate-x-1/2 z-[1001] flex items-center gap-3 px-3.5 py-2 bg-[#090d16]/95 backdrop-blur-md rounded-lg border border-red-500/60 shadow-2xl shadow-red-950/60 animate-bounce">
          <div className="flex items-center gap-2">
            <div className="w-2.5 h-2.5 rounded-full bg-red-500 animate-ping" />
            <Crosshair className="w-4 h-4 text-red-400 animate-spin" style={{ animationDuration: '6s' }} />
            <span className="text-[12px] font-semibold text-red-400 tracking-wider uppercase">
              PINPOINT MODE ACTIVE
            </span>
          </div>
          <span className="text-[11px] text-stone-300">
            Click anywhere on the map to set exact coordinates for <span className="font-semibold text-white capitalize">{state.pinpointMode.formType || "location"}</span>
          </span>
          <button
            onClick={cancelPinpoint}
            className="px-2 py-0.5 rounded text-[10px] font-medium bg-[#1e293b] text-stone-300 hover:text-white border border-stone-700 hover:border-stone-500 transition-colors"
          >
            Cancel (ESC)
          </button>
        </div>
      )}

      {/* Map overlay: data status */}
      <div className="absolute bottom-2 left-2 z-[1000] flex items-center gap-2 px-2 py-1 bg-[#0f1419]/90 backdrop-blur-sm rounded border border-[#2a3a4e]">
        <div className="text-[10px] text-[#6b7d93]">
          {visibleSettlements.length} settlements · {visibleNeeds.length} needs · {visibleOperations.length} ops · {visibleOffers.length} offers
          {state.layers.fieldReports && <span> · {visibleReports.length} reports</span>}
          {state.layers.organizations && <span> · {state.organizations.length} orgs</span>}
          {state.layers.aiAlerts && state.aiAnalysis?.findings && <span> · {state.aiAnalysis.findings.length} AI alerts</span>}
          {state.filters.status && <span className="text-amber-400"> · Status: {state.filters.status}</span>}
          {state.buildingsMeta && state.buildingsMeta.truncated && (
            <span className="text-[#4a5568]"> · {state.buildingsMeta.total_available} buildings (showing {state.buildingsMeta.returned})</span>
          )}
          {state.buildingsMeta && !state.buildingsMeta.truncated && (
            <span> · {state.buildingsMeta.total_available} buildings</span>
          )}
        </div>
      </div>
    </div>
  );
}

// -------------------------------------------------------------------
// Filter chip component
// -------------------------------------------------------------------

function FilterChip({ label, active, onClick, color }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "px-2 py-0.5 rounded text-[10px] font-medium transition-colors",
        active
          ? "bg-[#1a2332] text-[#c8d6e5] border border-[#2a3a4e]"
          : "text-[#6b7d93] hover:text-[#c8d6e5]"
      )}
      style={active && color ? { borderColor: color, color } : undefined}
    >
      {label}
    </button>
  );
}
