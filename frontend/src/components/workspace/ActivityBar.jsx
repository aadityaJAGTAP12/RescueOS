import { useState } from "react";
import { formatDistanceToNow } from "date-fns";
import { useWorkspace } from "../../lib/workspaceContext";
import { cn } from "../../lib/utils";
import {
  AlertTriangle, Zap, Package, FileText, Shield, Brain,
  TrendingUp, TrendingDown, Minus, Layers,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Event severity + icon mapping
// ---------------------------------------------------------------------------

const EVENT_ICONS = {
  need_created: AlertTriangle,
  need_updated: AlertTriangle,
  need_resolved: AlertTriangle,
  need_reopened: AlertTriangle,
  need_accepted: AlertTriangle,
  match_confirmed: Zap,
  resource_offered: Package,
  resource_accepted: Package,
  operation_created: Zap,
  operation_updated: Zap,
  operation_activated: Zap,
  operation_resolved: Zap,
  operation_cancelled: Zap,
  status_changed: Shield,
  field_update: FileText,
  override_applied: Shield,
  ai_recommendation: Brain,
  coordination_gap: Brain,
  coordination_proposed: Brain,
  organization_evaluation_completed: Brain,
};

const EVENT_SEVERITY = {
  need_created: "urgent",
  need_updated: "information",
  need_resolved: "stable",
  need_reopened: "urgent",
  need_accepted: "information",
  match_confirmed: "stable",
  resource_offered: "stable",
  resource_accepted: "stable",
  operation_created: "information",
  operation_updated: "information",
  operation_activated: "stable",
  operation_resolved: "stable",
  operation_cancelled: "urgent",
  status_changed: "urgent",
  field_update: "information",
  override_applied: "urgent",
  ai_recommendation: "critical",
  coordination_gap: "critical",
  coordination_proposed: "information",
  organization_evaluation_completed: "information",
};

const SEVERITY_COLORS = {
  critical: { dot: "#dc2626", text: "#f87171", bg: "rgba(220,38,38,0.08)" },
  urgent: { dot: "#d97706", text: "#fbbf24", bg: "rgba(217,119,6,0.08)" },
  stable: { dot: "#16a34a", text: "#4ade80", bg: "rgba(22,163,74,0.08)" },
  information: { dot: "#2563eb", text: "#60a5fa", bg: "rgba(37,99,235,0.08)" },
};

const DIRECTION_ICONS = {
  up: TrendingUp,
  down: TrendingDown,
  stable: Minus,
};

const DIRECTION_COLORS = {
  up: "#f87171",
  down: "#4ade80",
  stable: "#6b7d93",
};

// ---------------------------------------------------------------------------
// Delta time selector
// ---------------------------------------------------------------------------

function DeltaTimeSelector({ hours, onChange }) {
  const options = [
    { label: "1H", value: 1 },
    { label: "6H", value: 6 },
    { label: "24H", value: 24 },
    { label: "7D", value: 168 },
  ];
  return (
    <div className="flex items-center gap-0.5">
      {options.map(opt => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className={cn(
            "px-1 py-0.5 rounded text-[8px] font-medium transition-colors",
            hours === opt.value
              ? "bg-[#2a3a4e] text-[#c8d6e5]"
              : "text-[#6b7d93] hover:text-[#c8d6e5]"
          )}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Directional indicator
// ---------------------------------------------------------------------------

function DirectionIndicator({ label, direction }) {
  const Icon = DIRECTION_ICONS[direction] || Minus;
  const color = DIRECTION_COLORS[direction] || "#6b7d93";
  return (
    <div className="flex items-center gap-1">
      <Icon className="w-2.5 h-2.5" style={{ color }} />
      <span className="text-[8px] text-[#6b7d93] uppercase">{label}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main ActivityBar
// ---------------------------------------------------------------------------

export default function ActivityBar() {
  const { state, openPanel, delta, fetchDelta } = useWorkspace();
  const events = state.activity || [];
  const [deltaHours, setDeltaHours] = useState(24);

  const handleTimeChange = (hours) => {
    setDeltaHours(hours);
    fetchDelta(hours);
  };

  // Use delta data if available, fallback to local computation
  const summary = delta?.summary || {};
  const directional = delta?.directional || {};
  const groupedReports = delta?.grouped_reports || [];

  // Compute local delta summary as fallback
  const recentEvents = events.slice(0, 20);
  const localSummary = {
    newNeeds: recentEvents.filter(e => e.event_type === "need_created").length,
    resolved: recentEvents.filter(e => e.event_type === "need_resolved").length,
    newReports: recentEvents.filter(e => e.event_type === "field_update").length,
    newOffers: recentEvents.filter(e => e.event_type === "resource_offered").length,
    opUpdates: recentEvents.filter(e => e.event_type?.startsWith("operation_")).length,
  };

  const displaySummary = {
    newNeeds: summary.new_needs ?? localSummary.newNeeds,
    resolved: summary.resolved_needs ?? localSummary.resolved,
    newReports: summary.new_reports ?? localSummary.newReports,
    newOffers: summary.new_offers ?? localSummary.newOffers,
    opUpdates: summary.new_operations ?? localSummary.opUpdates,
    escalated: summary.escalated_needs ?? 0,
  };

  const criticalNeeds = state.needs.filter(
    n => n.urgency === "critical" && n.status === "OPEN"
  );

  const handleEventClick = (event) => {
    if (event.entity_type === "need") {
      const need = state.needs.find(n => n.id === event.entity_id);
      if (need) openPanel("need", need.id, need);
    } else if (event.entity_type === "operation") {
      const op = state.operations.find(o => o.id === event.entity_id);
      if (op) openPanel("operation", op.id, op);
    } else if (event.entity_type === "resource_offer") {
      const offer = state.offers.find(o => o.id === event.entity_id);
      if (offer) openPanel("offer", offer.id, offer);
    }
  };

  const handleGroupedReportClick = (groupedEvent) => {
    // Open the first report in the context panel
    if (groupedEvent.reports && groupedEvent.reports.length > 0) {
      const firstReport = groupedEvent.reports[0];
      const fullReport = state.fieldReports.find(r => r.id === firstReport.id);
      if (fullReport) {
        openPanel("report", fullReport.id, fullReport);
      }
    }
  };

  return (
    <div className="h-12 bg-[#0f1419] border-t border-[#2a3a4e] flex items-center shrink-0 overflow-hidden">
      {/* Delta Summary / What Changed */}
      <div className="flex items-center gap-2 px-2 border-r border-[#2a3a4e] shrink-0 bg-[#161d26] min-w-[260px]">
        {/* Time selector */}
        <DeltaTimeSelector hours={deltaHours} onChange={handleTimeChange} />

        <div className="w-px h-4 bg-[#2a3a4e]" />

        {/* Critical indicator */}
        {criticalNeeds.length > 0 && (
          <div className="flex items-center gap-1">
            <div className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
            <span className="text-[9px] font-semibold text-red-400">
              {criticalNeeds.length}
            </span>
          </div>
        )}

        {/* Delta counts */}
        <div className="flex items-center gap-1.5">
          {displaySummary.newNeeds > 0 && (
            <span className="text-[9px] font-mono font-semibold text-red-400">
              +{displaySummary.newNeeds}
            </span>
          )}
          {displaySummary.escalated > 0 && (
            <span className="text-[9px] font-mono font-semibold text-amber-400">
              ↑{displaySummary.escalated}
            </span>
          )}
          {displaySummary.resolved > 0 && (
            <span className="text-[9px] font-mono font-semibold text-green-400">
              -{displaySummary.resolved}
            </span>
          )}
          {displaySummary.newOffers > 0 && (
            <span className="text-[9px] font-mono text-teal-400">
              +{displaySummary.newOffers} offers
            </span>
          )}
          {displaySummary.opUpdates > 0 && (
            <span className="text-[9px] font-mono text-blue-400">
              {displaySummary.opUpdates} ops
            </span>
          )}
        </div>

        {/* Directional indicators */}
        <div className="flex items-center gap-1.5">
          <DirectionIndicator label="GAP" direction={directional.resource_gap || "stable"} />
          <DirectionIndicator label="RESP" direction={directional.response || "stable"} />
        </div>

        {/* Grouped reports indicator */}
        {groupedReports.length > 0 && (
          <div className="flex items-center gap-1">
            <Layers className="w-2.5 h-2.5 text-indigo-400" />
            <span className="text-[9px] text-indigo-400">
              {groupedReports.length} groups
            </span>
          </div>
        )}
      </div>

      {/* Activity stream */}
      <div className="flex-1 flex items-center overflow-x-auto scrollbar-hide">
        {events.length === 0 && groupedReports.length === 0 ? (
          <div className="px-4 text-[11px] text-[#4a5568]">
            No recent activity
          </div>
        ) : (
          <div className="flex items-center gap-2 px-3">
            {/* Grouped reports first (deduplicated) */}
            {groupedReports.slice(0, 5).map((grouped) => (
              <button
                key={grouped.event_id}
                onClick={() => handleGroupedReportClick(grouped)}
                className="flex items-center gap-1.5 shrink-0 hover:bg-[#1a2332] px-1.5 py-0.5 rounded transition-colors group"
                style={{ backgroundColor: "rgba(79,70,229,0.08)" }}
              >
                <Layers className="w-3 h-3 shrink-0 text-indigo-400" />
                <span className="text-[10px] text-[#6b7d93] group-hover:text-[#c8d6e5] transition-colors whitespace-nowrap">
                  {grouped.report_count}x {grouped.title?.substring(0, 30) || 'reports'}
                </span>
                <span className="text-[8px] text-indigo-400/60">
                  {grouped.verified_count}/{grouped.report_count} verified
                </span>
              </button>
            ))}

            {/* Regular events */}
            {recentEvents.slice(0, 15).map((event) => {
              const Icon = EVENT_ICONS[event.event_type] || Shield;
              const severity = EVENT_SEVERITY[event.event_type] || "information";
              const sevColor = SEVERITY_COLORS[severity];
              return (
                <button
                  key={event.id}
                  onClick={() => handleEventClick(event)}
                  className="flex items-center gap-1.5 shrink-0 hover:bg-[#1a2332] px-1.5 py-0.5 rounded transition-colors group"
                  style={{ backgroundColor: sevColor.bg }}
                >
                  <Icon
                    className="w-3 h-3 shrink-0"
                    style={{ color: sevColor.text }}
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

      {/* Status indicators */}
      <div className="flex items-center gap-2 px-3 border-l border-[#2a3a4e] shrink-0">
        <span className="text-[9px] text-[#4a5568]">
          {state.needs.length} needs · {state.operations.length} ops
        </span>
        <div className="flex items-center gap-1">
          <div className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
          <span className="text-[9px] text-green-400">Live</span>
        </div>
      </div>
    </div>
  );
}
