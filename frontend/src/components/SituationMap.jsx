import { useEffect, useState, useMemo } from "react";
import {
  MapContainer,
  TileLayer,
  GeoJSON,
  Marker,
  Popup,
  useMap,
} from "react-leaflet";
import L from "leaflet";
import { Users, AlertTriangle, Stethoscope, X, ShieldAlert } from "lucide-react";
import { getMarkerColor, cn } from "../lib/utils";
import { MAP_STYLES, getRouteStyleKey } from "../lib/mapStyles";

/* ------------------------------------------------------------------
   Custom marker icons
   ------------------------------------------------------------------ */

function createPriorityIcon(color) {
  return L.divIcon({
    className: "",
    iconSize: [28, 28],
    iconAnchor: [14, 14],
    popupAnchor: [0, -16],
    html: `<div class="marker-priority" style="background:${color}"></div>`,
  });
}

function createFieldReportIcon() {
  return L.divIcon({
    className: "",
    iconSize: [26, 26],
    iconAnchor: [13, 13],
    popupAnchor: [0, -14],
    html: `<div class="marker-field-report" style="background:#4f46e5">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/>
        <circle cx="9" cy="7" r="4"/>
      </svg>
    </div>`,
  });
}

function createFacilityIcon(hasOverride) {
  const bgColor = hasOverride ? "#f59e0b" : "#0891b2";
  const borderColor = hasOverride ? "#d97706" : "#0e7490";
  return L.divIcon({
    className: "",
    iconSize: [30, 30],
    iconAnchor: [15, 15],
    popupAnchor: [0, -17],
    html: `<div style="width:30px;height:30px;border-radius:50%;background:${bgColor};border:3px solid white;box-shadow:0 2px 6px rgba(0,0,0,0.3);display:flex;align-items:center;justify-content:center;">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M8 2h8l4 10H4L8 2z"/>
        <path d="M12 12v4"/>
        <path d="M8 20h8"/>
        <path d="M12 16h.01"/>
      </svg>
    </div>`,
  });
}

/* ------------------------------------------------------------------
   Layer control
   ------------------------------------------------------------------ */

const LAYER_CONFIG = [
  { id: "flood", label: "Flood Polygons", defaultVisible: true },
  { id: "priority", label: "Priority Marker", defaultVisible: true },
  { id: "fieldReports", label: "Field Reports", defaultVisible: true },
  { id: "facilities", label: "Medical Facilities", defaultVisible: true },
  { id: "route", label: "Route", defaultVisible: true },
];

function LayerControl({ visibleLayers, onToggle }) {
  return (
    <div className="absolute top-3 right-3 z-[1000] bg-white/95 backdrop-blur-sm rounded-lg border border-stone-200 shadow-sm p-2.5 min-w-[160px]">
      <div className="text-[10px] font-semibold text-stone-400 uppercase tracking-wider mb-1.5 px-1">
        Layers
      </div>
      {LAYER_CONFIG.map((layer) => (
        <label
          key={layer.id}
          className="flex items-center gap-2 px-1 py-1 rounded hover:bg-stone-50 cursor-pointer transition-colors"
        >
          <input
            type="checkbox"
            checked={visibleLayers[layer.id]}
            onChange={() => onToggle(layer.id)}
            className="w-3.5 h-3.5 rounded border-stone-300 text-stone-900 focus:ring-stone-400"
          />
          <span className="text-[12px] text-stone-700 font-medium">{layer.label}</span>
        </label>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------
   Fly-to handler
   ------------------------------------------------------------------ */

function FlyTo({ center, zoom }) {
  const map = useMap();
  useEffect(() => {
    if (center) {
      map.flyTo(center, zoom || map.getZoom(), { duration: 1.2 });
    }
  }, [center, zoom, map]);
  return null;
}

/* ------------------------------------------------------------------
   Field report popup
   ------------------------------------------------------------------ */

function FieldReportPopup({ report }) {
  return (
    <div className="p-3 min-w-[200px]">
      <div className="flex items-center gap-2 mb-2">
        <div className="flex items-center justify-center w-6 h-6 rounded bg-indigo-100">
          <Users className="w-3.5 h-3.5 text-indigo-600" />
        </div>
        <span className="text-[13px] font-semibold text-stone-800">
          {report.people_count} people reported
        </span>
      </div>
      <div className="text-[11px] text-stone-500 space-y-0.5 mb-2">
        <div>Adults: {report.adults} · Children: {report.children} · Elderly: {report.elderly}</div>
      </div>
      {report.needs && report.needs.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-2">
          {report.needs.map((need) => (
            <span key={need} className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-amber-50 text-amber-700 border border-amber-200/60">
              {need.replace(/_/g, " ")}
            </span>
          ))}
        </div>
      )}
      {!report.verified && (
        <div className="flex items-center gap-1 text-[10px] font-semibold text-amber-600 uppercase tracking-wider">
          <AlertTriangle className="w-3 h-3" />
          Unverified Report
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------
   Override modal
   ------------------------------------------------------------------ */

function OverrideModal({ facility, onClose, onApply }) {
  const [status, setStatus] = useState("submerged");
  const [reason, setReason] = useState("");
  const [applying, setApplying] = useState(false);

  const handleApply = async () => {
    setApplying(true);
    try {
      await fetch("/api/override", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target_type: "facility",
          target_id: facility.name,
          new_status: status,
          reason: reason,
        }),
      });
      onApply();
      onClose();
    } catch (err) {
      console.error("Override failed:", err);
    } finally {
      setApplying(false);
    }
  };

  const STATUS_OPTIONS = [
    { value: "submerged", label: "Submerged", color: "bg-red-50 text-red-700 border-red-200" },
    { value: "damaged", label: "Damaged", color: "bg-amber-50 text-amber-700 border-amber-200" },
    { value: "operational", label: "Operational", color: "bg-green-50 text-green-700 border-green-200" },
  ];

  return (
    <div className="fixed inset-0 z-[2000] flex items-center justify-center bg-black/40 backdrop-blur-sm" onClick={onClose}>
      <div
        className="bg-white rounded-2xl shadow-2xl border border-stone-200 w-full max-w-md mx-4 overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-stone-100">
          <div className="flex items-center gap-2">
            <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-amber-50">
              <ShieldAlert className="w-4 h-4 text-amber-600" />
            </div>
            <div>
              <h3 className="text-[14px] font-semibold text-stone-900">Override Facility Status</h3>
              <p className="text-[11px] text-stone-500">{facility.name}</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1 rounded hover:bg-stone-100 transition-colors">
            <X className="w-4 h-4 text-stone-400" />
          </button>
        </div>

        {/* Body */}
        <div className="px-5 py-4 space-y-4">
          {/* Current system status */}
          <div className="bg-stone-50 rounded-lg px-3 py-2">
            <div className="text-[10px] font-medium text-stone-400 uppercase tracking-wider mb-0.5">
              System Status (Overpass)
            </div>
            <div className="text-[13px] font-semibold text-stone-600">
              {facility.systemStatus || "operational"}
            </div>
          </div>

          {/* New status selection */}
          <div>
            <label className="block text-[12px] font-semibold text-stone-500 uppercase tracking-wider mb-2">
              Override To
            </label>
            <div className="grid grid-cols-3 gap-2">
              {STATUS_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => setStatus(opt.value)}
                  className={cn(
                    "px-3 py-2 rounded-lg text-[12px] font-semibold border-2 transition-all duration-200",
                    status === opt.value
                      ? `${opt.color} border-current shadow-sm`
                      : "bg-white text-stone-500 border-stone-200 hover:border-stone-300"
                  )}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {/* Reason */}
          <div>
            <label className="block text-[12px] font-semibold text-stone-500 uppercase tracking-wider mb-2">
              Reason for Override
            </label>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="e.g. Coordinator visited site, confirmed facility is underwater..."
              className="w-full h-20 px-3 py-2 rounded-lg border border-stone-200 bg-stone-50/50 text-[13px] text-stone-700 placeholder:text-stone-400 resize-none focus:outline-none focus:ring-2 focus:ring-stone-300"
            />
          </div>
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-stone-100 flex items-center justify-between">
          <p className="text-[10px] text-stone-400 max-w-[200px]">
            Override is tracked alongside system data. Original status is never lost.
          </p>
          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="px-3 py-1.5 rounded-lg text-[12px] font-medium text-stone-600 hover:bg-stone-50 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleApply}
              disabled={!reason.trim() || applying}
              className={cn(
                "px-4 py-1.5 rounded-lg text-[12px] font-semibold transition-all duration-200",
                reason.trim() && !applying
                  ? "bg-amber-600 text-white hover:bg-amber-700 shadow-sm"
                  : "bg-stone-100 text-stone-400 cursor-not-allowed"
              )}
            >
              {applying ? "Applying..." : "Apply Override"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------
   Main SituationMap component
   ------------------------------------------------------------------ */

export default function SituationMap({ assessment, loading, route }) {
  const [floodGeoJSON, setFloodGeoJSON] = useState(null);
  const [visibleLayers, setVisibleLayers] = useState(() => {
    const initial = {};
    LAYER_CONFIG.forEach((l) => (initial[l.id] = l.defaultVisible));
    return initial;
  });
  const [overrideModal, setOverrideModal] = useState(null);
  const [overrides, setOverrides] = useState({});

  useEffect(() => {
    fetch("/api/flood-geojson")
      .then((r) => r.json())
      .then(setFloodGeoJSON)
      .catch(console.error);
    // Load existing overrides
    fetchOverrides();
  }, []);

  const fetchOverrides = async () => {
    try {
      const resp = await fetch("/api/overrides");
      const data = await resp.json();
      const map = {};
      (data.overrides || []).forEach((o) => {
        if (o.active) map[o.target_id] = o;
      });
      setOverrides(map);
    } catch {
      // ignore
    }
  };

  const toggleLayer = (id) => {
    setVisibleLayers((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const center = useMemo(() => {
    if (assessment?.coordinates?.lat && assessment?.coordinates?.lon) {
      return [assessment.coordinates.lat, assessment.coordinates.lon];
    }
    return [26.98, 94.66];
  }, [assessment]);

  const priorityColor = getMarkerColor(assessment?.priority?.category);
  const fieldReports = assessment?.evidence?.field_reports?.reports || [];
  const facilityName = assessment?.evidence?.accessibility?.medical_facility_name;
  const facilityDistance = assessment?.evidence?.accessibility?.medical_distance_km;
  const facilityOverride = facilityName ? overrides[facilityName] : null;
  const facilityHasOverride = !!facilityOverride;

  const floodStyle = useMemo(
    () => ({
      fillColor: "#0891b2",
      fillOpacity: 0.18,
      color: "#0891b2",
      weight: 1.5,
      opacity: 0.5,
    }),
    []
  );

  // Facility marker position — offset slightly from the priority marker
  const facilityPos = useMemo(() => {
    if (!assessment?.coordinates?.lat || !facilityDistance || facilityDistance < 0) return null;
    // Approximate position: slightly north-east of the assessed location
    return [
      assessment.coordinates.lat + 0.005,
      assessment.coordinates.lon + 0.008,
    ];
  }, [assessment, facilityDistance]);

  return (
    <div className="relative rounded-xl overflow-hidden border border-stone-200 bg-white shadow-sm">
      <div style={{ height: "480px", width: "100%" }}>
        <MapContainer
          center={center}
          zoom={11}
          style={{ height: "100%", width: "100%" }}
          scrollWheelZoom={true}
          zoomControl={false}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
          />

          <FlyTo center={center} zoom={11} />

          {visibleLayers.flood && floodGeoJSON && (
            <GeoJSON key="flood" data={floodGeoJSON} style={() => floodStyle} />
          )}

          {visibleLayers.route && route?.geometry && (() => {
              const routeKey = getRouteStyleKey(route);
              const routeStyle = MAP_STYLES.route[routeKey] || MAP_STYLES.route.normal;
              const casingDash = routeStyle.dash ? routeStyle.dash.join(', ') : null;
              const casingWeight = routeStyle.width + MAP_STYLES.routeCasing.extraWidth;
              const blockedSegmentHtml = route.blocked_segments?.length
                ? route.blocked_segments.map(s =>
                    `<div style="margin-top:3px;padding:3px 5px;background:#fef2f2;border:1px solid #fecaca;border-radius:4px;">
                      <div style="font-size:10px;font-weight:600;color:#991b1b;">${s.road_name || s.road_id}</div>
                      <div style="font-size:9px;color:#b91c1c;">${s.override_reason || 'Blocked'}</div>
                      <div style="font-size:9px;color:#dc2626;">Reported by: ${s.override_actor || 'Unknown'}</div>
                    </div>`
                  ).join('')
                : '';
              return [
                /* Casing layer — dark underline for contrast against basemap */
                <GeoJSON
                  key="route-casing"
                  data={{
                    type: "FeatureCollection",
                    features: [{ type: "Feature", geometry: { type: "LineString", coordinates: route.geometry } }],
                  }}
                  style={{
                    color: MAP_STYLES.routeCasing.color,
                    weight: casingWeight,
                    opacity: 0.9,
                    dashArray: casingDash,
                  }}
                />,
                /* Main route layer */
                <GeoJSON
                  key="route"
                  data={{
                    type: "FeatureCollection",
                    features: [
                      {
                        type: "Feature",
                        properties: {
                          distance: route.distance_km,
                          duration: route.duration_minutes,
                          source: route.source,
                          crossesFlood: route.crosses_flood_zone,
                          crossesBlocked: route.crosses_overridden_road,
                          routeValid: route.route_valid,
                          requiresReroute: route.requires_reroute,
                          routeValidReason: route.route_valid_reason,
                          blockedSegments: route.blocked_segments,
                          floodWarning: route.flood_warning,
                        },
                        geometry: {
                          type: "LineString",
                          coordinates: route.geometry,
                        },
                      },
                    ],
                  }}
                  style={{
                    color: routeStyle.color,
                    weight: routeStyle.width,
                    opacity: 0.85,
                    dashArray: routeStyle.dash ? routeStyle.dash.join(', ') : null,
                  }}
                  onEachFeature={(feature, layer) => {
                    const props = feature.properties;
                    const safetySection = !props.routeValid
                      ? `<div style="margin-top:6px;padding:6px 8px;background:#fef2f2;border:1px solid #fecaca;border-radius:6px;">
                          <div style="font-size:11px;font-weight:700;color:#991b1b;margin-bottom:3px;">⛔ ROUTE UNSAFE</div>
                          <div style="font-size:10px;color:#b91c1c;">${props.routeValidReason || 'Route crosses blocked segments'}</div>
                          ${props.blockedSegments?.length ? '<div style="font-size:9px;color:#dc2626;margin-top:3px;font-weight:600;">Blocked:</div>' + blockedSegmentHtml : ''}
                        </div>`
                      : props.crossesBlocked
                      ? `<div style="margin-top:6px;padding:6px 8px;background:#fef2f2;border:1px solid #fecaca;border-radius:6px;">
                          <div style="font-size:11px;font-weight:700;color:#991b1b;margin-bottom:3px;">⛔ CONFIRMED HAZARD</div>
                          <div style="font-size:10px;color:#b91c1c;">${props.routeValidReason || 'Route crosses an overridden-blocked road'}</div>
                          ${blockedSegmentHtml}
                        </div>`
                      : props.crossesFlood
                      ? `<div style="font-size:10px;color:#d97706;margin-top:4px;font-weight:600;">⚠ ${props.floodWarning || 'Route crosses flood zone'}</div>`
                      : '';
                    layer.bindPopup(
                      `<div style="padding: 8px; min-width: 180px;">
                        <div style="font-size: 12px; font-weight: 600; color: #1e293b; margin-bottom: 4px;">
                          Route Information
                        </div>
                        <div style="font-size: 11px; color: #64748b; margin-bottom: 2px;">
                          Distance: ${props.distance?.toFixed(1)} km
                        </div>
                        <div style="font-size: 11px; color: #64748b; margin-bottom: 2px;">
                          Duration: ~${Math.round(props.duration)} minutes
                        </div>
                        <div style="font-size: 10px; color: #94a3b8; margin-top: 4px;">
                          ${props.source}
                        </div>
                        ${safetySection}
                      </div>`
                    );
                  }}
                />,
              ];
            })()}

          {visibleLayers.priority && assessment?.coordinates?.lat && (
            <Marker
              position={[assessment.coordinates.lat, assessment.coordinates.lon]}
              icon={createPriorityIcon(priorityColor)}
            >
              <Popup>
                <div className="p-2">
                  <div className="text-[13px] font-semibold text-stone-800 mb-1">
                    {assessment.location?.replace(/_/g, " ")}
                  </div>
                  <div className="text-[12px] font-bold" style={{ color: priorityColor }}>
                    {assessment.priority?.category}
                  </div>
                </div>
              </Popup>
            </Marker>
          )}

          {visibleLayers.facilities && facilityPos && (
            <Marker
              position={facilityPos}
              icon={createFacilityIcon(facilityHasOverride)}
              eventHandlers={{
                click: () => {
                  setOverrideModal({
                    name: facilityName,
                    systemStatus: "operational",
                  });
                },
              }}
            >
              <Popup>
                <div className="p-2 min-w-[180px]">
                  <div className="flex items-center gap-1.5 mb-1">
                    <Stethoscope className="w-3.5 h-3.5 text-cyan-600" />
                    <span className="text-[12px] font-semibold text-stone-800">{facilityName}</span>
                  </div>
                  <div className="text-[11px] text-stone-500 mb-1">
                    {facilityDistance?.toFixed(1)} km away
                  </div>
                  {facilityHasOverride && (
                    <div className="mt-1 px-2 py-1 rounded bg-amber-50 border border-amber-200/60">
                      <div className="text-[10px] font-semibold text-amber-700 uppercase">
                        Overridden: {facilityOverride.override_status}
                      </div>
                      <div className="text-[10px] text-amber-600">
                        {facilityOverride.reason}
                      </div>
                    </div>
                  )}
                  <div className="mt-2 text-[10px] text-stone-400">
                    Click marker to apply override
                  </div>
                </div>
              </Popup>
            </Marker>
          )}

          {visibleLayers.fieldReports &&
            fieldReports.map((report) => (
              <Marker
                key={report.report_id}
                position={[report.lat, report.lon]}
                icon={createFieldReportIcon()}
              >
                <Popup>
                  <FieldReportPopup report={report} />
                </Popup>
              </Marker>
            ))}
        </MapContainer>

        <LayerControl visibleLayers={visibleLayers} onToggle={toggleLayer} />
      </div>

      {/* Route info panel */}
      {route && (() => {
        const routeKey = getRouteStyleKey(route);
        const routeColor = MAP_STYLES.route[routeKey]?.color || MAP_STYLES.route.normal.color;
        const isUnsafe = route.route_valid === false || route.crosses_overridden_road;
        return (
          <div className="absolute bottom-3 left-3 z-[1000] bg-white/95 backdrop-blur-sm rounded-lg border border-stone-200 shadow-sm p-3 max-w-[300px]">
            {/* Status indicator */}
            <div className="flex items-center gap-2 mb-2">
              <div className="w-2 h-2 rounded-full" style={{ backgroundColor: routeColor }} />
              <span className="text-[11px] font-semibold text-stone-700">
                {route.crosses_overridden_road
                  ? "⛔ Route Crosses Blocked Road"
                  : route.crosses_flood_zone
                    ? "⚠ Route Crosses Flood Zone"
                    : route.status === "success"
                      ? "Real Road Route"
                      : "Straight-line Approximation"}
              </span>
            </div>

            {/* Metrics */}
            <div className="space-y-1">
              <div className="flex justify-between text-[11px]">
                <span className="text-stone-500">Distance:</span>
                <span className="font-medium text-stone-700">{route.distance_km?.toFixed(1)} km</span>
              </div>
              <div className="flex justify-between text-[11px]">
                <span className="text-stone-500">Duration:</span>
                <span className="font-medium text-stone-700">~{Math.round(route.duration_minutes)} min</span>
              </div>
              <div className="text-[10px] text-stone-400 mt-1">
                {route.distance_method}
              </div>

              {/* Route validity warning — shown immediately when unsafe, not behind a click */}
              {isUnsafe && (
                <div className="mt-2 px-2 py-1.5 rounded bg-red-50 border border-red-200/60">
                  <div className="text-[10px] font-bold text-red-700">
                    ⛔ ROUTE NOT SAFE TO EXECUTE
                  </div>
                  <div className="text-[10px] text-red-600 mt-0.5">
                    {route.route_valid_reason || "Route crosses blocked segments."}
                  </div>
                  {route.blocked_segments?.length > 0 && (
                    <div className="mt-1.5 space-y-1">
                      {route.blocked_segments.map((seg, i) => (
                        <div key={i} className="px-1.5 py-1 rounded bg-white/60 border border-red-100">
                          <div className="text-[9px] font-bold text-red-800">
                            {seg.road_name || seg.road_id}
                          </div>
                          <div className="text-[9px] text-red-600">
                            {seg.override_reason || "Blocked"}
                          </div>
                          <div className="text-[9px] text-red-500">
                            Reported by: {seg.override_actor || "Unknown"}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Flood zone warning — only when no override blockage (avoids stacking) */}
              {!route.crosses_overridden_road && route.crosses_flood_zone && (
                <div className="mt-2 px-2 py-1.5 rounded bg-amber-50 border border-amber-200/60">
                  <div className="text-[10px] font-semibold text-amber-700">
                    ⚠ Route crosses {route.intersecting_polygons?.length || 0} flood zone(s)
                  </div>
                  <div className="text-[10px] text-amber-600 mt-0.5">
                    Automatic avoidance not available. Coordinator should consider an alternative route.
                  </div>
                </div>
              )}
            </div>
          </div>
        );
      })()}

      {/* Override modal */}
      {overrideModal && (
        <OverrideModal
          facility={overrideModal}
          onClose={() => setOverrideModal(null)}
          onApply={fetchOverrides}
        />
      )}
    </div>
  );
}
