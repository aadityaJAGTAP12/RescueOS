import { formatDistanceToNow } from "date-fns";
import { useWorkspace } from "../../lib/workspaceContext";
import { cn } from "../../lib/utils";
import {
  AlertTriangle, Zap, Package, FileText, Shield, Brain, Bell,
} from "lucide-react";

const EVENT_ICONS = {
  need_created: AlertTriangle,
  need_updated: AlertTriangle,
  need_resolved: AlertTriangle,
  resource_offered: Package,
  resource_accepted: Package,
  operation_created: Zap,
  operation_updated: Zap,
  status_changed: Shield,
  field_update: FileText,
  ai_recommendation: Brain,
  coordination_gap: Brain,
};

const EVENT_COLORS = {
  need_created: "#dc2626",
  need_updated: "#d97706",
  need_resolved: "#16a34a",
  resource_offered: "#0d9488",
  resource_accepted: "#0d9488",
  operation_created: "#2563eb",
  operation_updated: "#2563eb",
  status_changed: "#f59e0b",
  field_update: "#4f46e5",
  ai_recommendation: "#7c3aed",
  coordination_gap: "#7c3aed",
};

export default function ActivityBar() {
  const { state, openPanel } = useWorkspace();
  const events = state.activity || [];
  const criticalNeeds = state.needs.filter(
    (n) => n.urgency === "critical" && n.status === "OPEN"
  );

  const handleEventClick = (event) => {
    if (event.entity_type === "need") {
      const need = state.needs.find((n) => n.id === event.entity_id);
      if (need) openPanel("need", need.id, need);
    } else if (event.entity_type === "operation") {
      const op = state.operations.find((o) => o.id === event.entity_id);
      if (op) openPanel("operation", op.id, op);
    } else if (event.entity_type === "resource_offer") {
      const offer = state.offers.find((o) => o.id === event.entity_id);
      if (offer) openPanel("offer", offer.id, offer);
    }
  };

  return (
    <div className="h-10 bg-[#0f1419] border-t border-[#2a3a4e] flex items-center shrink-0 overflow-hidden">
      {/* Status indicators */}
      <div className="flex items-center gap-3 px-3 border-r border-[#2a3a4e] shrink-0">
        {criticalNeeds.length > 0 && (
          <div className="flex items-center gap-1.5">
            <div className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
            <span className="text-[10px] font-semibold text-red-400">
              {criticalNeeds.length} critical
            </span>
          </div>
        )}
        <div className="flex items-center gap-1.5">
          <span className="text-[10px] text-[#6b7d93]">
            {state.needs.length} needs
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-[10px] text-[#6b7d93]">
            {state.operations.length} ops
          </span>
        </div>
      </div>

      {/* Activity stream */}
      <div className="flex-1 flex items-center overflow-x-auto scrollbar-hide">
        {events.length === 0 ? (
          <div className="px-4 text-[11px] text-[#4a5568]">
            No recent activity
          </div>
        ) : (
          <div className="flex items-center gap-4 px-3">
            {events.slice(0, 15).map((event) => {
              const Icon = EVENT_ICONS[event.event_type] || Shield;
              const color = EVENT_COLORS[event.event_type] || "#6b7d93";
              return (
                <button
                  key={event.id}
                  onClick={() => handleEventClick(event)}
                  className="flex items-center gap-1.5 shrink-0 hover:bg-[#1a2332] px-1.5 py-0.5 rounded transition-colors group"
                >
                  <Icon
                    className="w-3 h-3 shrink-0"
                    style={{ color }}
                  />
                  <span className="text-[10px] text-[#6b7d93] group-hover:text-[#c8d6e5] transition-colors whitespace-nowrap">
                    {event.detail || event.event_type}
                  </span>
                  {event.created_at && (
                    <span className="text-[9px] text-[#4a5568] whitespace-nowrap">
                      {formatDistanceToNow(new Date(event.created_at), {
                        addSuffix: true,
                      })}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* Refresh indicator */}
      <div className="px-3 border-l border-[#2a3a4e] shrink-0">
        <div className="text-[9px] text-[#4a5568]">Live</div>
      </div>
    </div>
  );
}
