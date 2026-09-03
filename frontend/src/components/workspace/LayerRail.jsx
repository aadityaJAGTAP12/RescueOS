import {
  Droplets, Route, Landmark, Building2, Hospital, MapPin,
  AlertTriangle, Package, Zap, FileText, Shield, Brain,
  Plus, ChevronRight, ChevronLeft, Users, Clock, EyeOff, Eye,
} from "lucide-react";
import { useWorkspace } from "../../lib/workspaceContext";
import { cn } from "../../lib/utils";
import { useState, useCallback } from "react";

const LAYER_GROUPS = [
  {
    label: "HAZARD",
    layers: [
      { id: "flood", label: "Flood", icon: Droplets, color: "#0891b2" },
      { id: "floodHistory", label: "Flood History", icon: Clock, color: "#0e7490" },
    ],
  },
  {
    label: "INFRASTRUCTURE",
    layers: [
      { id: "roads", label: "Roads", icon: Route, color: "#16a34a" },
      { id: "bridges", label: "Bridges", icon: Landmark, color: "#16a34a" },
      { id: "settlements", label: "Settlements", icon: MapPin, color: "#78716c" },
      { id: "buildings", label: "Buildings", icon: Building2, color: "#a8a29e" },
      { id: "medical", label: "Medical", icon: Hospital, color: "#0891b2" },
    ],
  },
  {
    label: "RESPONSE",
    layers: [
      { id: "organizations", label: "Organizations", icon: Users, color: "#2563eb" },
      { id: "needs", label: "Needs", icon: AlertTriangle, color: "#dc2626" },
      { id: "incidents", label: "Incidents", icon: Shield, color: "#d97706" },
      { id: "operations", label: "Operations", icon: Zap, color: "#2563eb" },
      { id: "offers", label: "Offers", icon: Package, color: "#0d9488" },
    ],
  },
  {
    label: "INTELLIGENCE",
    layers: [
      { id: "fieldReports", label: "Reports", icon: FileText, color: "#4f46e5" },
      { id: "overrides", label: "Overrides", icon: Shield, color: "#f59e0b" },
      { id: "aiAlerts", label: "AI Alerts", icon: Brain, color: "#7c3aed" },
    ],
  },
];

function LayerToggle({ layer, active, onToggle, count }) {
  const Icon = layer.icon;
  return (
    <button
      onClick={() => onToggle(layer.id)}
      className={cn(
        "w-full flex items-center gap-2 px-2.5 py-1.5 rounded text-left transition-all duration-150 group",
        active
          ? "bg-[#1a2332] border border-[#2a3a4e]"
          : "hover:bg-[#1a2332]/50"
      )}
      title={layer.label}
    >
      <div
        className={cn(
          "w-5 h-5 rounded flex items-center justify-center shrink-0 transition-colors",
          active ? "bg-opacity-20" : "bg-transparent"
        )}
        style={{
          backgroundColor: active ? `${layer.color}20` : "transparent",
        }}
      >
        <Icon
          className="w-3 h-3"
          style={{ color: active ? layer.color : "#6b7d93" }}
        />
      </div>
      <span
        className={cn(
          "text-[11px] font-medium truncate transition-colors",
          active ? "text-[#c8d6e5]" : "text-[#6b7d93]"
        )}
      >
        {layer.label}
      </span>
      {count !== undefined && count > 0 && (
        <span className="ml-auto text-[9px] font-mono text-[#6b7d93] tabular-nums">
          {count}
        </span>
      )}
    </button>
  );
}

// -------------------------------------------------------------------
// Flood History snapshot selector (shown when floodHistory layer is active)
// -------------------------------------------------------------------

function FloodHistorySelector() {
  const { state, selectFloodSnapshot } = useWorkspace();
  const snapshots = state.floodSnapshots || [];
  const selected = state.selectedFloodSnapshot;

  if (!state.layers.floodHistory || snapshots.length === 0) return null;

  return (
    <div className="px-2 py-1.5 space-y-1 border-b border-[#2a3a4e]">
      <div className="text-[9px] font-semibold text-[#4a5568] uppercase tracking-wider px-1 mb-1">
        Available Snapshots
      </div>
      {snapshots.map((snap) => (
        <button
          key={snap.id}
          onClick={() => selectFloodSnapshot(snap)}
          className={cn(
            "w-full flex items-center gap-2 px-2 py-1.5 rounded text-left transition-all text-[10px]",
            selected?.id === snap.id
              ? "bg-[#0e7490]/15 border border-[#0e7490]/30 text-[#c8d6e5]"
              : "hover:bg-[#1a2332]/50 text-[#6b7d93] border border-transparent"
          )}
        >
          <div className="w-2 h-2 rounded-full" style={{ backgroundColor: selected?.id === snap.id ? "#0e7490" : "#4a5568" }} />
          <div className="flex-1 min-w-0">
            <div className="font-medium truncate">{snap.district_id}</div>
            <div className="text-[9px] opacity-70">
              {snap.observed_at ? new Date(snap.observed_at).toLocaleDateString() : ""} · {snap.polygon_count} polygons
            </div>
          </div>
        </button>
      ))}
    </div>
  );
}

export default function LayerRail() {
  const { state, toggleLayer, openPanel, setFilter, fetchAiAnalysis } = useWorkspace();
  const [collapsed, setCollapsed] = useState(false);

  // Handle AI Alerts toggle: if enabling, open the AI panel
  const handleLayerToggle = useCallback((layerId) => {
    if (layerId === 'aiAlerts' && !state.layers.aiAlerts) {
      // Turn on and open AI panel
      toggleLayer('aiAlerts');
      openPanel('aiAnalysis');
    } else {
      toggleLayer(layerId);
    }
  }, [state.layers.aiAlerts, toggleLayer, openPanel]);

  // Compute entity counts (respect district filter)
  const districtFilter = state.filters.district;
  const counts = {
    roads: districtFilter ? state.roads.filter(r => r.district_id === districtFilter).length : state.roads.length,
    bridges: districtFilter ? state.bridges.filter(b => b.district_id === districtFilter).length : state.bridges.length,
    settlements: districtFilter ? state.settlements.filter(s => s.district_id === districtFilter).length : state.settlements.length,
    buildings: state.buildingsMeta?.total_available ?? state.buildings.length,
    medical: districtFilter ? state.medicalFacilities.filter(f => f.district_id === districtFilter).length : state.medicalFacilities.length,
    organizations: state.organizations.length,
    needs: districtFilter ? state.needs.filter(n => n.district_id === districtFilter).length : state.needs.length,
    offers: districtFilter ? state.offers.filter(o => o.district_id === districtFilter).length : state.offers.length,
    operations: districtFilter ? state.operations.filter(o => o.district_id === districtFilter).length : state.operations.length,
    incidents: state.incidents.length,
    fieldReports: state.fieldReports.length,
    floodHistory: state.floodSnapshots.length,
  };

  if (collapsed) {
    return (
      <div className="w-10 bg-[#0f1419] border-r border-[#2a3a4e] flex flex-col items-center py-2 gap-1 shrink-0">
        <button
          onClick={() => setCollapsed(false)}
          className="w-7 h-7 rounded flex items-center justify-center hover:bg-[#1a2332] transition-colors mb-1"
        >
          <ChevronRight className="w-3.5 h-3.5 text-[#6b7d93]" />
        </button>
        {LAYER_GROUPS.map((group) =>
          group.layers.map((layer) => {
            const Icon = layer.icon;
            const active = state.layers[layer.id];
            return (
              <button
                key={layer.id}
                onClick={() => toggleLayer(layer.id)}
                className={cn(
                  "w-7 h-7 rounded flex items-center justify-center transition-colors",
                  active ? "bg-[#1a2332]" : "hover:bg-[#1a2332]/50"
                )}
                title={layer.label}
              >
                <Icon
                  className="w-3.5 h-3.5"
                  style={{ color: active ? layer.color : "#6b7d93" }}
                />
              </button>
            );
          })
        )}
      </div>
    );
  }

  return (
    <div className="w-52 bg-[#0f1419] border-r border-[#2a3a4e] flex flex-col shrink-0 overflow-y-auto">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-[#2a3a4e]">
        <span className="text-[10px] font-semibold text-[#6b7d93] uppercase tracking-wider">
          Layers
        </span>
        <button
          onClick={() => setCollapsed(true)}
          className="w-5 h-5 rounded flex items-center justify-center hover:bg-[#1a2332] transition-colors"
        >
          <ChevronLeft className="w-3 h-3 text-[#6b7d93]" />
        </button>
      </div>

      {/* District Filter */}
      <div className="p-2 border-b border-[#2a3a4e] space-y-2">
        <div className="text-[9px] font-semibold text-[#4a5568] uppercase tracking-wider px-2 mb-1">
          District
        </div>
        <select
          value={state.filters.district || ""}
          onChange={(e) => setFilter("district", e.target.value || null)}
          className="w-full px-2 py-1.5 rounded border border-[#2a3a4e] bg-[#0f1419] text-[11px] text-[#c8d6e5] outline-none appearance-none cursor-pointer"
        >
          <option value="">All Districts</option>
          {state.districts.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </select>
      </div>

      {/* Filters */}
      <div className="px-2 py-2 border-b border-[#2a3a4e] space-y-2">
        <div className="text-[9px] font-semibold text-[#4a5568] uppercase tracking-wider px-1">
          Urgency
        </div>
        <div className="flex flex-wrap gap-1">
          {['critical', 'high', 'medium', 'low'].map(u => (
            <button
              key={u}
              onClick={() => setFilter('urgency', state.filters.urgency === u ? null : u)}
              className={cn(
                'px-1.5 py-0.5 rounded text-[9px] font-medium border transition-colors',
                state.filters.urgency === u
                  ? u === 'critical' ? 'bg-red-500/20 text-red-400 border-red-500/30'
                    : u === 'high' ? 'bg-amber-500/20 text-amber-400 border-amber-500/30'
                    : u === 'medium' ? 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30'
                    : 'bg-green-500/20 text-green-400 border-green-500/30'
                  : 'text-[#6b7d93] border-[#2a3a4e] hover:border-[#3a5a7e]'
              )}
            >
              {u}
            </button>
          ))}
        </div>
        <div className="text-[9px] font-semibold text-[#4a5568] uppercase tracking-wider px-1">
          Status
        </div>
        <div className="flex flex-wrap gap-1">
          {['OPEN', 'RESPONDING', 'RESOLVED'].map(s => (
            <button
              key={s}
              onClick={() => setFilter('status', state.filters.status === s ? null : s)}
              className={cn(
                'px-1.5 py-0.5 rounded text-[9px] font-medium border transition-colors',
                state.filters.status === s
                  ? s === 'OPEN' ? 'bg-red-500/20 text-red-400 border-red-500/30'
                    : s === 'RESPONDING' ? 'bg-blue-500/20 text-blue-400 border-blue-500/30'
                    : 'bg-green-500/20 text-green-400 border-green-500/30'
                  : 'text-[#6b7d93] border-[#2a3a4e] hover:border-[#3a5a7e]'
              )}
            >
              {s.toLowerCase()}
            </button>
          ))}
        </div>
      </div>

      {/* Layer groups */}
      <div className="flex-1 overflow-y-auto p-2 space-y-3">
        {LAYER_GROUPS.map((group) => (
          <div key={group.label}>
            <div className="text-[9px] font-semibold text-[#4a5568] uppercase tracking-wider px-2 mb-1">
              {group.label}
            </div>
            <div className="space-y-0.5">
              {group.layers.map((layer) => (
                <LayerToggle
                  key={layer.id}
                  layer={layer}
                  active={state.layers[layer.id]}
                  onToggle={handleLayerToggle}
                  count={counts[layer.id]}
                />
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Flood History snapshot selector */}
      <FloodHistorySelector />

      {/* Quick actions */}
      <div className="p-2 border-t border-[#2a3a4e] space-y-1">
        <div className="text-[9px] font-semibold text-[#4a5568] uppercase tracking-wider px-2 mb-1">
          ACTIONS
        </div>
        <button
          onClick={() => openPanel("createNeed")}
          className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded text-left hover:bg-[#1a2332] transition-colors"
        >
          <div className="w-5 h-5 rounded flex items-center justify-center bg-red-500/10">
            <Plus className="w-3 h-3 text-red-400" />
          </div>
          <span className="text-[11px] font-medium text-[#c8d6e5]">Create Need</span>
        </button>
        <button
          onClick={() => openPanel("createReport")}
          className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded text-left hover:bg-[#1a2332] transition-colors"
        >
          <div className="w-5 h-5 rounded flex items-center justify-center bg-indigo-500/10">
            <Plus className="w-3 h-3 text-indigo-400" />
          </div>
          <span className="text-[11px] font-medium text-[#c8d6e5]">Report Issue</span>
        </button>
        <button
          onClick={() => openPanel("createOffer")}
          className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded text-left hover:bg-[#1a2332] transition-colors"
        >
          <div className="w-5 h-5 rounded flex items-center justify-center bg-teal-500/10">
            <Plus className="w-3 h-3 text-teal-400" />
          </div>
          <span className="text-[11px] font-medium text-[#c8d6e5]">Offer Resource</span>
        </button>
      </div>
    </div>
  );
}
