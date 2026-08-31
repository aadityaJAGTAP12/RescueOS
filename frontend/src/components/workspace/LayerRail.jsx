import {
  Droplets, Route, Landmark, Building2, Hospital, MapPin,
  AlertTriangle, Package, Zap, FileText, Shield, Brain,
  Plus, ChevronRight, ChevronLeft,
} from "lucide-react";
import { useWorkspace } from "../../lib/workspaceContext";
import { cn } from "../../lib/utils";
import { useState } from "react";

const LAYER_GROUPS = [
  {
    label: "ENVIRONMENT",
    layers: [
      { id: "flood", label: "Flood", icon: Droplets, color: "#0891b2" },
      { id: "roads", label: "Roads", icon: Route, color: "#16a34a" },
      { id: "bridges", label: "Bridges", icon: Landmark, color: "#16a34a" },
      { id: "settlements", label: "Settlements", icon: MapPin, color: "#78716c" },
      { id: "buildings", label: "Buildings", icon: Building2, color: "#a8a29e" },
      { id: "medical", label: "Medical", icon: Hospital, color: "#0891b2" },
    ],
  },
  {
    label: "OPERATIONAL",
    layers: [
      { id: "needs", label: "Needs", icon: AlertTriangle, color: "#dc2626" },
      { id: "offers", label: "Offers", icon: Package, color: "#0d9488" },
      { id: "operations", label: "Operations", icon: Zap, color: "#2563eb" },
      { id: "incidents", label: "Incidents", icon: Shield, color: "#d97706" },
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

export default function LayerRail() {
  const { state, toggleLayer, openPanel } = useWorkspace();
  const [collapsed, setCollapsed] = useState(false);

  // Compute entity counts
  const counts = {
    roads: state.roads.length,
    bridges: state.bridges.length,
    needs: state.needs.length,
    offers: state.offers.length,
    operations: state.operations.length,
    fieldReports: state.fieldReports.length,
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
                  onToggle={toggleLayer}
                  count={counts[layer.id]}
                />
              ))}
            </div>
          </div>
        ))}
      </div>

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
