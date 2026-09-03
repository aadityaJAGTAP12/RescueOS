import { useEffect, useMemo, useCallback, useRef } from "react";
import {
  MapContainer, TileLayer, GeoJSON, Marker, Popup, useMap,
} from "react-leaflet";
import L from "leaflet";
import { useWorkspace } from "../../lib/workspaceContext";
import { cn } from "../../lib/utils";
import { MAP_STYLES } from "../../lib/mapStyles";

// -------------------------------------------------------------------
// Marker icon factories
// -------------------------------------------------------------------

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

function NeedMarker({ need, onClick }) {
  const urgencyColor = {
    critical: "#dc2626",
    high: "#d97706",
    medium: "#eab308",
    low: "#16a34a",
  };
  const color = urgencyColor[need.urgency] || "#78716c";
  const size = need.urgency === "critical" ? 28 : need.urgency === "high" ? 24 : 20;

  return (
    <Marker
      position={[need.lat, need.lon]}
      icon={createCircleIcon(color, size)}
      eventHandlers={{ click: () => onClick("need", need.id, need) }}
    >
      <Popup>
        <div className="p-2 min-w-[180px]">
          <div className="text-[13px] font-semibold text-stone-800 mb-1">{need.title}</div>
          <div className="text-[11px] text-stone-500">
            <span className="font-medium" style={{ color }}>{need.urgency}</span> · {need.need_type}
          </div>
          <div className="text-[10px] text-stone-400 mt-1">Status: {need.status}</div>
          {need.location_name && (
            <div className="text-[10px] text-stone-400">📍 {need.location_name}</div>
          )}
        </div>
      </Popup>
    </Marker>
  );
}

// -------------------------------------------------------------------
// Operation marker
// -------------------------------------------------------------------

function OperationMarker({ operation, onClick }) {
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
      position={[operation.lat, operation.lon]}
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
        </div>
      </Popup>
    </Marker>
  );
}

// -------------------------------------------------------------------
// Offer marker
// -------------------------------------------------------------------

function OfferMarker({ offer, onClick }) {
  return (
    <Marker
      position={[offer.lat, offer.lon]}
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
    fetchFieldReports,
    fetchBuildings,
  } = useWorkspace();

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

  // Filter needs by district
  const visibleNeeds = useMemo(() => {
    let filtered = state.needs;
    if (state.filters.district) {
      filtered = filtered.filter((n) => n.district_id === state.filters.district);
    }
    if (state.filters.urgency) {
      filtered = filtered.filter((n) => n.urgency === state.filters.urgency);
    }
    if (state.filters.status) {
      filtered = filtered.filter((n) => n.status === state.filters.status);
    }
    return filtered;
  }, [state.needs, state.filters]);

  // Filter operations by district
  const visibleOperations = useMemo(() => {
    let filtered = state.operations;
    if (state.filters.district) {
      filtered = filtered.filter((o) => o.district_id === state.filters.district);
    }
    // Status filter for operations maps OPEN→PLANNING, RESPONDING→ACTIVE, RESOLVED→COMPLETED
    if (state.filters.status) {
      const statusMap = { OPEN: 'PLANNING', RESPONDING: 'ACTIVE', RESOLVED: 'COMPLETED' };
      const targetStatus = statusMap[state.filters.status] || state.filters.status;
      filtered = filtered.filter((o) => o.status === targetStatus);
    }
    return filtered;
  }, [state.operations, state.filters]);

  // Filter offers by district
  const visibleOffers = useMemo(() => {
    let filtered = state.offers;
    if (state.filters.district) {
      filtered = filtered.filter((o) => o.district_id === state.filters.district);
    }
    return filtered.filter((o) => o.lat && o.lon);
  }, [state.offers, state.filters]);

  // Filter field reports by district (approximate geographic filter using settlements as reference)
  const visibleReports = useMemo(() => {
    let reports = state.fieldReports.filter((r) => r.lat && r.lon);
    if (state.filters.district) {
      // Filter reports that have coordinates near the selected district's settlements
      const districtSettlements = state.settlements.filter(
        (s) => s.district_id === state.filters.district
      );
      if (districtSettlements.length > 0) {
        // Compute district bounding box from settlements
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
    return reports;
  }, [state.fieldReports, state.settlements, state.filters.district]);



  return (
    <div className="flex-1 relative">
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
        <MapMoveHandler onMoveEnd={handleMapMoveEnd} />

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
          visibleNeeds
            .filter((n) => n.lat && n.lon)
            .map((need) => (
              <NeedMarker key={need.id} need={need} onClick={handleObjectClick} />
            ))}

        {/* Operations layer */}
        {state.layers.operations &&
          visibleOperations
            .filter((o) => o.lat && o.lon)
            .map((op) => (
              <OperationMarker key={op.id} operation={op} onClick={handleObjectClick} />
            ))}

        {/* Offers layer */}
        {state.layers.offers &&
          visibleOffers.map((offer) => (
            <OfferMarker key={offer.id} offer={offer} onClick={handleObjectClick} />
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
        {state.layers.organizations && state.organizations.map((org) => (
          <Marker
            key={org.id}
            position={[26.98, 94.66]} // organizations may not have coordinates — show at district center
            icon={createCircleIcon("#2563eb", 16)}
            eventHandlers={{ click: () => handleObjectClick("organization", org.id, org) }}
          >
            <Popup>
              <div className="p-2 min-w-[180px]">
                <div className="text-[13px] font-semibold text-stone-800 mb-1">{org.name}</div>
                <div className="text-[11px] text-stone-500">{org.organization_type}</div>
                {org.description && (
                  <div className="text-[10px] text-stone-400 mt-1">{org.description}</div>
                )}
              </div>
            </Popup>
          </Marker>
        ))}

        {/* Field reports layer */}
        {state.layers.fieldReports &&
          visibleReports.map((report) => (
            <FieldReportMarker
              key={report.id || report.report_id}
              report={report}
              onClick={handleObjectClick}
            />
          ))}
      </MapContainer>

      {/* Map overlay: filter bar */}
      <div className="absolute top-2 left-1/2 -translate-x-1/2 z-[1000] flex items-center gap-1.5 px-2 py-1 bg-[#0f1419]/90 backdrop-blur-sm rounded border border-[#2a3a4e]">
        <FilterChip
          label="All Urgency"
          active={!state.filters.urgency}
          onClick={() => setFilter("urgency", null)}
        />
        {["critical", "high", "medium", "low"].map((u) => (
          <FilterChip
            key={u}
            label={u}
            active={state.filters.urgency === u}
            onClick={() => setFilter("urgency", u)}
            color={
              u === "critical"
                ? "#dc2626"
                : u === "high"
                ? "#d97706"
                : u === "medium"
                ? "#eab308"
                : "#16a34a"
            }
          />
        ))}
      </div>

      {/* Map overlay: data status */}
      <div className="absolute bottom-2 left-2 z-[1000] flex items-center gap-2 px-2 py-1 bg-[#0f1419]/90 backdrop-blur-sm rounded border border-[#2a3a4e]">
        <div className="text-[10px] text-[#6b7d93]">
          {visibleSettlements.length} settlements · {visibleNeeds.length} needs · {visibleOperations.length} ops · {visibleOffers.length} offers
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
