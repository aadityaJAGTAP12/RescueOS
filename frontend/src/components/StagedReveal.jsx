import { useState, useEffect, useRef, useMemo } from "react";
import {
  ChevronDown,
  ChevronRight,
  Clock,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Wrench,
  Zap,
  ArrowDown,
  Eye,
  EyeOff,
} from "lucide-react";
import { cn } from "../lib/utils";

/* ------------------------------------------------------------------
   Agent icon/color mapping — human-readable labels for agent names
   ------------------------------------------------------------------ */

const AGENT_META = {
  query_parser_agent: {
    label: "Query Parser",
    description: "Extracts structured intent from free-text query",
    icon: "🔍",
    color: "bg-blue-50 text-blue-700 border-blue-200/60",
    activeColor: "bg-blue-100 text-blue-800 border-blue-300",
    dotColor: "bg-blue-500",
  },
  location_resolver: {
    label: "Location Resolver",
    description: "Resolves location names to known coordinates",
    icon: "📍",
    color: "bg-indigo-50 text-indigo-700 border-indigo-200/60",
    activeColor: "bg-indigo-100 text-indigo-800 border-indigo-300",
    dotColor: "bg-indigo-500",
  },
  flood_assessment_agent: {
    label: "Flood Assessment",
    description: "Checks flood polygon containment and extent",
    icon: "🌊",
    color: "bg-cyan-50 text-cyan-700 border-cyan-200/60",
    activeColor: "bg-cyan-100 text-cyan-800 border-cyan-300",
    dotColor: "bg-cyan-500",
  },
  exposure_agent: {
    label: "Building Exposure",
    description: "Counts buildings in flood zones",
    icon: "🏘️",
    color: "bg-amber-50 text-amber-700 border-amber-200/60",
    activeColor: "bg-amber-100 text-amber-800 border-amber-300",
    dotColor: "bg-amber-500",
  },
  accessibility_agent: {
    label: "Medical Accessibility",
    description: "Finds nearest medical facility and distance",
    icon: "🏥",
    color: "bg-violet-50 text-violet-700 border-violet-200/60",
    activeColor: "bg-violet-100 text-violet-800 border-violet-300",
    dotColor: "bg-violet-500",
  },
  allocation_agent: {
    label: "Priority Scoring",
    description: "Computes PDC score using deterministic formula",
    icon: "📊",
    color: "bg-rose-50 text-rose-700 border-rose-200/60",
    activeColor: "bg-rose-100 text-rose-800 border-rose-300",
    dotColor: "bg-rose-500",
  },
  coordinator_agent: {
    label: "Coordinator",
    description: "Synthesizes findings into recommendation",
    icon: "🎯",
    color: "bg-stone-100 text-stone-700 border-stone-200",
    activeColor: "bg-stone-200 text-stone-800 border-stone-300",
    dotColor: "bg-stone-600",
  },
};

const DEFAULT_META = {
  label: "Agent",
  description: "",
  icon: "⚙️",
  color: "bg-stone-50 text-stone-600 border-stone-200",
  activeColor: "bg-stone-100 text-stone-700 border-stone-300",
  dotColor: "bg-stone-500",
};

/* ------------------------------------------------------------------
   Flow connector between panels
   ------------------------------------------------------------------ */

function FlowConnector({ active, complete }) {
  return (
    <div className="flex justify-center py-1">
      <div className="flex flex-col items-center">
        <div
          className={cn(
            "w-px h-4 transition-colors duration-500",
            complete
              ? "bg-stone-400"
              : active
              ? "bg-stone-300"
              : "bg-stone-200"
          )}
        />
        <ArrowDown
          className={cn(
            "w-3 h-3 transition-colors duration-500 -mt-0.5",
            complete
              ? "text-stone-400"
              : active
              ? "text-stone-300"
              : "text-stone-200"
          )}
        />
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------
   Expandable raw output section
   ------------------------------------------------------------------ */

function RawOutputSection({ rawOutput, agentName }) {
  const [expanded, setExpanded] = useState(false);

  if (!rawOutput) return null;

  const formatted = typeof rawOutput === "string"
    ? rawOutput
    : JSON.stringify(rawOutput, null, 2);

  return (
    <div className="mt-2">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1.5 text-[11px] text-stone-400 hover:text-stone-600 transition-colors"
      >
        {expanded ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
        <span className="font-medium">{expanded ? "Hide" : "View"} full detail</span>
      </button>
      {expanded && (
        <div className="mt-2 rounded-lg bg-stone-50 border border-stone-100 p-3 slide-up">
          <pre className="text-[11px] text-stone-600 font-mono whitespace-pre-wrap break-words leading-relaxed max-h-48 overflow-y-auto">
            {formatted}
          </pre>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------
   Tools called badges
   ------------------------------------------------------------------ */

function ToolBadges({ tools }) {
  if (!tools || tools.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-1 mt-1.5">
      {tools.map((tool) => (
        <span
          key={tool}
          className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-mono font-medium bg-stone-100 text-stone-500 border border-stone-200/60"
        >
          <Wrench className="w-2.5 h-2.5" />
          {tool}
        </span>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------
   Single agent panel
   ------------------------------------------------------------------ */

function AgentPanel({ entry, state, index, showConnector }) {
  const meta = AGENT_META[entry.agent_name] || DEFAULT_META;
  const isComplete = state === "complete";
  const isActive = state === "active";
  const isWaiting = state === "waiting";
  const isError = state === "error";

  return (
    <div className="fade-in">
      {showConnector && (
        <FlowConnector active={isActive || isComplete} complete={isComplete} />
      )}
      <div
        className={cn(
          "rounded-xl border bg-white shadow-sm transition-all duration-500 overflow-hidden",
          isComplete && !isError && "border-stone-200",
          isActive && "border-stone-300 shadow-md",
          isWaiting && "border-stone-100 opacity-60",
          isError && "border-red-200 bg-red-50/30"
        )}
      >
        {/* Panel header */}
        <div className="flex items-center gap-3 px-4 py-3">
          {/* Status indicator */}
          <div className="relative shrink-0">
            <div
              className={cn(
                "w-8 h-8 rounded-lg flex items-center justify-center text-sm transition-all duration-300",
                isComplete && !isError && "bg-green-50",
                isActive && "bg-stone-100",
                isWaiting && "bg-stone-50",
                isError && "bg-red-50"
              )}
            >
              {isComplete && !isError && (
                <CheckCircle2 className="w-4 h-4 text-green-600" />
              )}
              {isActive && (
                <Loader2 className="w-4 h-4 text-stone-500 animate-spin" />
              )}
              {isWaiting && (
                <Clock className="w-4 h-4 text-stone-300" />
              )}
              {isError && (
                <AlertCircle className="w-4 h-4 text-red-500" />
              )}
            </div>
            {/* Pulse animation for active state */}
            {isActive && (
              <div className="absolute inset-0 rounded-lg animate-ping bg-stone-200 opacity-30" />
            )}
          </div>

          {/* Agent info */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm">{meta.icon}</span>
              <span className="text-[13px] font-semibold text-stone-800">
                {meta.label}
              </span>
              {entry.location_context && (
                <span className="text-[10px] text-stone-400 font-mono">
                  ({entry.location_context.replace(/_/g, " ")})
                </span>
              )}
            </div>
            <p className="text-[11px] text-stone-400 mt-0.5 truncate">
              {entry.query_portion_handled}
            </p>
          </div>

          {/* Duration */}
          <div className="shrink-0 text-right">
            {isComplete && entry.duration_ms !== undefined && (
              <span className="text-[11px] font-mono text-stone-400 tabular-nums">
                {entry.duration_ms >= 1000
                  ? `${(entry.duration_ms / 1000).toFixed(1)}s`
                  : `${Math.round(entry.duration_ms)}ms`}
              </span>
            )}
            {isActive && (
              <span className="text-[11px] text-stone-400 animate-pulse">
                Working...
              </span>
            )}
            {isWaiting && (
              <span className="text-[11px] text-stone-300">Queued</span>
            )}
          </div>
        </div>

        {/* Output summary — only shown when complete */}
        {isComplete && (
          <div className="px-4 pb-3 slide-up">
            {/* Tools */}
            <ToolBadges tools={entry.tools_called} />

            {/* Output */}
            <div className="mt-2 bg-stone-50 rounded-lg border border-stone-100 p-2.5">
              <p className="text-[12px] text-stone-600 leading-relaxed">
                {entry.output_summary}
              </p>
            </div>

            {/* Expandable raw output */}
            <RawOutputSection rawOutput={entry.raw_output} agentName={entry.agent_name} />
          </div>
        )}

        {/* Error state */}
        {isError && (
          <div className="px-4 pb-3">
            <div className="bg-red-50 rounded-lg border border-red-100 p-2.5">
              <p className="text-[12px] text-red-600 leading-relaxed">
                {entry.output_summary || "Agent encountered an error"}
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------
   Coordinator summary panel — appears last, shows synthesis
   ------------------------------------------------------------------ */

function CoordinatorPanel({ trace, assessment, state }) {
  const isComplete = state === "complete";
  const isActive = state === "active";
  const isWaiting = state === "waiting";

  // Build synthesis text from specialist findings
  const synthesisText = useMemo(() => {
    if (!assessment) return null;
    const { priority, evidence } = assessment;
    if (!priority) return null;

    const parts = [];
    if (evidence?.flood) {
      const f = evidence.flood;
      parts.push(
        f.flooded
          ? `flood assessment (polygon: ${f.nearest_flood_polygon_km2?.toFixed(2)} km²)`
          : "flood assessment (not flood-affected)"
      );
    }
    if (evidence?.accessibility) {
      const a = evidence.accessibility;
      if (a.medical_distance_km >= 0) {
        parts.push(
          `accessibility findings (${a.medical_distance_km.toFixed(1)}km to ${a.medical_facility_name})`
        );
      }
    }
    if (evidence?.exposure) {
      const e = evidence.exposure;
      if (e.total_buildings > 0) {
        parts.push(
          `building exposure (${e.exposed_count}/${e.total_buildings} exposed, ${(e.exposure_ratio * 100).toFixed(0)}%)`
        );
      }
    }

    const synParts = [];
    if (parts.length > 0) {
      synParts.push(`Combining ${parts.join(" and ")}...`);
    }
    synParts.push(
      `Priority: ${priority.category} (PDC ${priority.pdc_score.toFixed(2)})`
    );
    synParts.push(priority.recommendation);

    return synParts.join(" ");
  }, [assessment]);

  return (
    <div className="fade-in">
      <FlowConnector active={isActive || isComplete} complete={isComplete} />
      <div
        className={cn(
          "rounded-xl border bg-white shadow-sm transition-all duration-500 overflow-hidden",
          isComplete && "border-stone-300 shadow-md",
          isActive && "border-stone-200",
          isWaiting && "border-stone-100 opacity-60"
        )}
      >
        {/* Header */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-stone-100 bg-stone-50/50">
          <div className="w-8 h-8 rounded-lg bg-stone-900 flex items-center justify-center">
            <span className="text-sm">🎯</span>
          </div>
          <div className="flex-1">
            <span className="text-[13px] font-semibold text-stone-800">
              Coordinator
            </span>
            <p className="text-[11px] text-stone-400">
              Synthesizes specialist findings into final recommendation
            </p>
          </div>
          <div className="shrink-0">
            {isComplete && (
              <CheckCircle2 className="w-4 h-4 text-green-600" />
            )}
            {isActive && (
              <Loader2 className="w-4 h-4 text-stone-500 animate-spin" />
            )}
            {isWaiting && (
              <Clock className="w-4 h-4 text-stone-300" />
            )}
          </div>
        </div>

        {/* Synthesis content */}
        {isComplete && synthesisText && (
          <div className="px-4 py-3 slide-up">
            <div className="bg-stone-50 rounded-lg border border-stone-100 p-3">
              <p className="text-[13px] text-stone-700 leading-relaxed">
                {synthesisText}
              </p>
            </div>
          </div>
        )}

        {/* Waiting state */}
        {isWaiting && (
          <div className="px-4 py-3">
            <div className="flex items-center gap-2 text-[12px] text-stone-400">
              <div className="w-2 h-2 rounded-full bg-stone-200 animate-pulse" />
              Waiting for specialist agents to complete...
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------
   Main StagedReveal component
   ------------------------------------------------------------------ */

export default function StagedReveal({ agentTrace, assessment, loading }) {
  const [agentStates, setAgentStates] = useState({});
  const animationRef = useRef(null);
  const startTimeRef = useRef(null);

  // Reset states when new trace arrives
  useEffect(() => {
    if (!agentTrace || agentTrace.length === 0) {
      setAgentStates({});
      return;
    }

    // All agents start in "waiting" state
    const initial = {};
    agentTrace.forEach((entry, i) => {
      initial[i] = "waiting";
    });
    setAgentStates({});
    startTimeRef.current = performance.now();

    // Cancel any previous animation
    if (animationRef.current) {
      cancelAnimationFrame(animationRef.current);
    }

    // Compute timing boundaries from real data
    const firstStart = Math.min(...agentTrace.map((e) => e.started_at));
    const lastEnd = Math.max(...agentTrace.map((e) => e.completed_at));
    const totalRealDuration = (lastEnd - firstStart) * 1000; // ms

    // Map real timestamps to animation timestamps
    // Scale so the full trace takes proportional time
    // Minimum 2s, maximum 15s for the full animation
    const MIN_ANIM_DURATION = 2000;
    const MAX_ANIM_DURATION = 15000;
    const animDuration = Math.max(
      MIN_ANIM_DURATION,
      Math.min(MAX_ANIM_DURATION, totalRealDuration)
    );
    const timeScale = animDuration / Math.max(totalRealDuration, 1);

    // Schedule state transitions
    const scheduleUpdate = (index, newState, delay) => {
      setTimeout(() => {
        setAgentStates((prev) => ({ ...prev, [index]: newState }));
      }, delay);
    };

    agentTrace.forEach((entry, i) => {
      const relativeStart = (entry.started_at - firstStart) * 1000 * timeScale;
      const relativeEnd = (entry.completed_at - firstStart) * 1000 * timeScale;

      // Transition to "active" when this agent starts
      scheduleUpdate(i, "active", relativeStart);

      // Transition to "complete" when this agent finishes
      // If the agent has an error status, use "error" instead
      const finalState = entry.status === "error" ? "error" : "complete";
      scheduleUpdate(i, finalState, relativeEnd);
    });

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [agentTrace]);

  // Show loading skeleton while waiting for data
  if (loading && (!agentTrace || agentTrace.length === 0)) {
    return (
      <div className="rounded-xl border border-stone-200 bg-white p-5 shadow-sm space-y-3">
        <div className="skeleton h-5 w-48 rounded" />
        <div className="skeleton h-4 w-full rounded" />
        <div className="skeleton h-4 w-3/4 rounded" />
        <div className="skeleton h-4 w-1/2 rounded" />
      </div>
    );
  }

  if (!agentTrace || agentTrace.length === 0) return null;

  // Group trace entries by location_context for multi-location queries
  const hasLocationContext = agentTrace.some((e) => e.location_context);

  // Separate the query parser and location resolver (no location_context)
  // from per-location agents (have location_context)
  const pipelineAgents = agentTrace.filter((e) => !e.location_context);
  const locationGroups = {};
  if (hasLocationContext) {
    agentTrace
      .filter((e) => e.location_context)
      .forEach((entry) => {
        const ctx = entry.location_context;
        if (!locationGroups[ctx]) locationGroups[ctx] = [];
        locationGroups[ctx].push(entry);
      });
  }

  // Build the ordered list of all panels to render
  const panels = [];
  let globalIndex = 0;

  // Pipeline agents first
  pipelineAgents.forEach((entry) => {
    panels.push({ entry, globalIndex, showConnector: globalIndex > 0 });
    globalIndex++;
  });

  // Then per-location groups
  Object.entries(locationGroups).forEach(([locName, entries]) => {
    entries.forEach((entry) => {
      panels.push({ entry, globalIndex, showConnector: globalIndex > 0 });
      globalIndex++;
    });
  });

  return (
    <div className="space-y-0">
      {/* Section header */}
      <div className="flex items-center gap-2 mb-3">
        <Zap className="w-4 h-4 text-stone-400" />
        <h3 className="text-[13px] font-semibold text-stone-400 uppercase tracking-wider">
          Agent Orchestration
        </h3>
        <span className="text-[10px] text-stone-300 font-mono">
          {agentTrace.length} agent{agentTrace.length !== 1 ? "s" : ""}
        </span>
      </div>

      {/* Agent panels */}
      <div>
        {panels.map(({ entry, globalIndex, showConnector }) => (
          <AgentPanel
            key={`${entry.agent_name}-${entry.location_context || "pipeline"}-${globalIndex}`}
            entry={entry}
            state={agentStates[globalIndex] || "waiting"}
            index={globalIndex}
            showConnector={showConnector}
          />
        ))}

        {/* Coordinator panel at the end */}
        <CoordinatorPanel
          trace={agentTrace}
          assessment={assessment}
          state={
            // Coordinator completes after all specialist agents
            Object.values(agentStates).every((s) => s === "complete" || s === "error")
              ? "complete"
              : Object.values(agentStates).some((s) => s === "active")
              ? "active"
              : "waiting"
          }
        />
      </div>

      {/* Timing summary footer */}
      {agentTrace.length > 0 && (
        <div className="mt-3 flex items-center justify-between text-[11px] text-stone-400">
          <span>
            {Object.values(agentStates).filter((s) => s === "complete").length}/
            {agentTrace.length} agents completed
          </span>
          <span className="font-mono tabular-nums">
            Total:{" "}
            {(
              agentTrace.reduce((sum, e) => sum + (e.duration_ms || 0), 0) / 1000
            ).toFixed(1)}
            s real time
          </span>
        </div>
      )}
    </div>
  );
}
