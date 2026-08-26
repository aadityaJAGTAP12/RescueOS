import { useState } from "react";
import { Search, Loader2, AlertTriangle, MapPin, ChevronRight, AlertCircle, HelpCircle } from "lucide-react";
import { cn } from "../lib/utils";
import StagedReveal from "./StagedReveal";

/* ------------------------------------------------------------------
   Example query chips — clickable prompts for demo
   ------------------------------------------------------------------ */

const EXAMPLE_QUERIES = [
  {
    label: "Assess Sivasagar Flood Zone",
    query: "What's the priority status of Sivasagar Flood Zone?",
  },
  {
    label: "Rank all 3 locations",
    query:
      "Rank Sivasagar Flood Zone, Sivasagar Settlement Flood, and Sivasagar by priority for flood response.",
  },
  {
    label: "Allocate 2 boats + 1 medical team",
    query:
      "We have 2 boats and 1 medical team. Rank Sivasagar Flood Zone, Sivasagar Settlement Flood, and Sivasagar by priority and allocate resources.",
  },
  {
    label: "Complex request (honest gaps)",
    query:
      "Act as an emergency logistics planner. Assess the 3 marooned villages near Dibrugarh, provide river gauge levels for the Brahmaputra, optimize truck routes to all flood zones, and calculate 7-day food sustainment for 5000 people.",
  },
];

/* ------------------------------------------------------------------
   Unresolved locations callout
   ------------------------------------------------------------------ */

function UnresolvedLocations({ locations }) {
  if (!locations || locations.length === 0) return null;

  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 shadow-sm">
      <div className="flex items-start gap-3">
        <div className="flex items-center justify-center w-7 h-7 rounded-lg bg-amber-100 shrink-0">
          <MapPin className="w-4 h-4 text-amber-600" />
        </div>
        <div className="flex-1 min-w-0">
          <h4 className="text-[13px] font-semibold text-amber-800 mb-1">
            Unresolved Locations
          </h4>
          <p className="text-[12px] text-amber-700 leading-relaxed mb-2">
            These locations could not be resolved to known coordinates. The
            system only matches against pre-configured reference locations — no
            guessing or geocoding is performed.
          </p>
          <div className="flex flex-wrap gap-1.5">
            {locations.map((loc, i) => (
              <span
                key={i}
                className="inline-flex items-center px-2 py-1 rounded-md text-[12px] font-medium bg-amber-100 text-amber-800 border border-amber-200"
              >
                "{loc}"
              </span>
            ))}
          </div>
          <p className="text-[11px] text-amber-600 mt-2">
            Please select a known location from the dropdown or provide explicit
            coordinates.
          </p>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------
   Capability gaps callout
   ------------------------------------------------------------------ */

function CapabilityGaps({ gaps }) {
  if (!gaps || gaps.length === 0) return null;

  return (
    <div className="rounded-xl border border-stone-200 bg-white p-4 shadow-sm">
      <div className="flex items-start gap-3">
        <div className="flex items-center justify-center w-7 h-7 rounded-lg bg-stone-100 shrink-0">
          <AlertTriangle className="w-4 h-4 text-stone-500" />
        </div>
        <div className="flex-1 min-w-0">
          <h4 className="text-[13px] font-semibold text-stone-800 mb-1">
            Requested Capabilities
          </h4>
          <div className="space-y-2">
            {gaps.map((gap) => (
              <div
                key={gap.capability}
                className="flex items-start gap-2 p-2 rounded-lg bg-stone-50 border border-stone-100"
              >
                <div
                  className={cn(
                    "w-2 h-2 rounded-full mt-1.5 shrink-0",
                    gap.status === "supported"
                      ? "bg-green-500"
                      : "bg-amber-400"
                  )}
                />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-[12px] font-semibold text-stone-700">
                      {gap.capability.replace(/_/g, " ")}
                    </span>
                    <span
                      className={cn(
                        "inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-semibold uppercase tracking-wider border",
                        gap.status === "supported"
                          ? "bg-green-50 text-green-700 border-green-200/60"
                          : "bg-amber-50 text-amber-700 border-amber-200/60"
                      )}
                    >
                      {gap.status === "supported" ? "Available" : "Not Available"}
                    </span>
                  </div>
                  <p className="text-[11px] text-stone-500 leading-relaxed">
                    {gap.reason}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------
   Extracted resources display
   ------------------------------------------------------------------ */

function ExtractedResources({ resources }) {
  if (!resources || resources.length === 0) return null;

  return (
    <div className="rounded-xl border border-stone-200 bg-white p-4 shadow-sm">
      <div className="flex items-center gap-2 mb-3">
        <div className="flex items-center justify-center w-7 h-7 rounded-lg bg-stone-100">
          <AlertCircle className="w-4 h-4 text-stone-500" />
        </div>
        <h4 className="text-[13px] font-semibold text-stone-800">
          Extracted Resources
        </h4>
      </div>
      <div className="space-y-2">
        {resources.map((r, i) => (
          <div
            key={i}
            className={cn(
              "flex items-start gap-3 p-2.5 rounded-lg border",
              r.flagged_as_possible_fabrication
                ? "bg-amber-50 border-amber-200"
                : "bg-stone-50 border-stone-100"
            )}
          >
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[12px] font-semibold text-stone-700">
                  "{r.raw_phrase}"
                </span>
                <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-semibold uppercase tracking-wider border bg-stone-100 text-stone-600 border-stone-200">
                  {r.resource_type}
                </span>
                {r.quantity_numeric !== null && (
                  <span className="text-[11px] font-mono text-stone-500">
                    qty: {r.quantity_numeric} {r.unit || ""}
                  </span>
                )}
                {r.quantity_numeric === null && r.quantity_text && (
                  <span className="text-[11px] text-stone-400 italic">
                    no explicit number stated
                  </span>
                )}
              </div>
              {r.flagged_as_possible_fabrication && (
                <div className="flex items-start gap-1.5 mt-1.5">
                  <AlertTriangle className="w-3.5 h-3.5 text-amber-500 mt-0.5 shrink-0" />
                  <p className="text-[11px] text-amber-700 leading-relaxed">
                    {r.verification_note ||
                      "This number may have been calculated rather than directly stated — please verify."}
                  </p>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------
   Clarification needed callout
   ------------------------------------------------------------------ */

function ClarificationNeeded({ items }) {
  if (!items || items.length === 0) return null;

  return (
    <div className="rounded-xl border border-blue-200 bg-blue-50 p-4 shadow-sm">
      <div className="flex items-start gap-3">
        <div className="flex items-center justify-center w-7 h-7 rounded-lg bg-blue-100 shrink-0">
          <HelpCircle className="w-4 h-4 text-blue-600" />
        </div>
        <div className="flex-1 min-w-0">
          <h4 className="text-[13px] font-semibold text-blue-800 mb-1">
            Clarification Needed
          </h4>
          <div className="space-y-2">
            {items.map((item, i) => (
              <div
                key={i}
                className="p-2.5 rounded-lg bg-white/60 border border-blue-100"
              >
                <span className="text-[12px] font-semibold text-blue-700 block mb-0.5">
                  {item.field}
                </span>
                <p className="text-[11px] text-blue-600 leading-relaxed">
                  {item.reason}
                </p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------
   Allocation plan display
   ------------------------------------------------------------------ */

function AllocationPlan({ plan }) {
  if (!plan) return null;

  return (
    <div className="rounded-xl border border-stone-200 bg-white p-4 shadow-sm">
      <div className="flex items-center gap-2 mb-3">
        <div className="flex items-center justify-center w-7 h-7 rounded-lg bg-stone-100">
          <ChevronRight className="w-4 h-4 text-stone-500" />
        </div>
        <h4 className="text-[13px] font-semibold text-stone-800">
          Resource Allocation Plan
        </h4>
      </div>

      {/* Ranked locations */}
      {plan.ranked_locations && plan.ranked_locations.length > 0 && (
        <div className="space-y-1.5 mb-3">
          {plan.ranked_locations.map((loc, i) => (
            <div
              key={loc.location}
              className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-stone-50 border border-stone-100"
            >
              <span className="text-[11px] font-mono font-semibold text-stone-400 w-5">
                #{i + 1}
              </span>
              <span className="text-[12px] font-medium text-stone-700 flex-1">
                {loc.location.replace(/_/g, " ")}
              </span>
              <span
                className={cn(
                  "text-[11px] font-mono font-semibold",
                  loc.pdc_score >= 0.75
                    ? "text-red-700"
                    : loc.pdc_score >= 0.5
                    ? "text-red-600"
                    : loc.pdc_score >= 0.25
                    ? "text-amber-600"
                    : "text-green-600"
                )}
              >
                {loc.pdc_score.toFixed(2)}
              </span>
              <span className="text-[10px] text-stone-400 uppercase">
                {loc.category}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Resources (best-effort mapping display) */}
      {plan.resources && (
        <div className="flex flex-wrap gap-1.5 mb-3">
          {Object.entries(plan.resources).map(([key, val]) =>
            val > 0 ? (
              <span
                key={key}
                className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-blue-50 text-blue-700 border border-blue-200/60"
              >
                {val} {key.replace(/_/g, " ")}
              </span>
          ) : null
          )}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------
   Main QueryInput component
   ------------------------------------------------------------------ */

export default function QueryInput({ onQueryResult }) {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  const handleSubmit = async (q) => {
    const text = (q || query).trim();
    if (!text) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const resp = await fetch("/api/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: text }),
      });
      if (!resp.ok) throw new Error(`Query failed: ${resp.status}`);
      const data = await resp.json();
      setResult(data);
      if (onQueryResult) onQueryResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleChipClick = (chipQuery) => {
    setQuery(chipQuery);
    handleSubmit(chipQuery);
  };

  return (
    <div className="space-y-3">
      {/* Input area */}
      <div className="bg-white rounded-xl border border-stone-200 shadow-sm">
        <div className="flex items-center gap-3 p-3">
          <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-stone-100 shrink-0">
            <Search className="w-4 h-4 text-stone-400" />
          </div>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
            placeholder="Ask about any location or request resource allocation..."
            className="flex-1 text-[14px] text-stone-800 placeholder:text-stone-400 outline-none bg-transparent"
            disabled={loading}
          />
          <button
            onClick={() => handleSubmit()}
            disabled={loading || !query.trim()}
            className={cn(
              "px-4 py-2 rounded-lg text-[13px] font-semibold transition-all duration-200",
              "focus-visible:ring-2 focus-visible:ring-stone-400 focus-visible:ring-offset-1",
              loading || !query.trim()
                ? "bg-stone-100 text-stone-400 cursor-not-allowed"
                : "bg-stone-900 text-white hover:bg-stone-800 active:bg-stone-950 shadow-sm"
            )}
          >
            {loading ? (
              <span className="flex items-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin" />
                Parsing...
              </span>
            ) : (
              "Run"
            )}
          </button>
        </div>
      </div>

      {/* Example chips — only show when no result yet */}
      {!result && !loading && (
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-[11px] text-stone-400 mr-1">Try:</span>
          {EXAMPLE_QUERIES.map((chip) => (
            <button
              key={chip.label}
              onClick={() => handleChipClick(chip.query)}
              className="px-2.5 py-1 rounded-md text-[11px] font-medium text-stone-500 bg-stone-50 border border-stone-200 hover:bg-stone-100 hover:text-stone-700 hover:border-stone-300 transition-all duration-150"
            >
              {chip.label}
            </button>
          ))}
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-[13px] text-red-700">
          {error}
        </div>
      )}

      {/* Loading state */}
      {loading && (
        <div className="rounded-xl border border-stone-200 bg-white p-6 shadow-sm">
          <div className="flex flex-col items-center gap-3">
            <Loader2 className="w-6 h-6 text-stone-400 animate-spin" />
            <div className="text-center">
              <p className="text-[13px] font-medium text-stone-600">
                Parsing query and gathering evidence...
              </p>
              <p className="text-[11px] text-stone-400 mt-1">
                The LLM extracts intent, then deterministic tools compute real
                results.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Results */}
      {result && !loading && (
        <div className="space-y-3">
          {/* Agent orchestration staged reveal */}
          {result.agent_trace && result.agent_trace.length > 0 && (
            <div className="rounded-xl border border-stone-200 bg-white p-4 shadow-sm">
              <StagedReveal
                agentTrace={result.agent_trace}
                assessment={result.resolved_locations?.[0]}
                loading={false}
              />
            </div>
          )}
          {/* Parsed intent summary */}
          <div className="rounded-xl border border-stone-200 bg-white p-4 shadow-sm">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-[12px] font-semibold text-stone-400 uppercase tracking-wider">
                Parsed Intent
              </span>
              <span
                className={cn(
                  "inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-semibold uppercase tracking-wider border",
                  result.parsed_intent?.parse_confidence === "high"
                    ? "bg-green-50 text-green-700 border-green-200/60"
                    : result.parsed_intent?.parse_confidence === "medium"
                    ? "bg-amber-50 text-amber-700 border-amber-200/60"
                    : "bg-stone-100 text-stone-600 border-stone-200"
                )}
              >
                {result.parsed_intent?.parse_confidence || "unknown"} confidence
              </span>
            </div>
            <div className="flex flex-wrap gap-2 text-[12px]">
              <span className="px-2 py-0.5 rounded bg-stone-100 text-stone-600">
                Intent: <strong>{result.parsed_intent?.intent}</strong>
              </span>
              {result.parsed_intent?.locations_mentioned?.length > 0 && (
                <span className="px-2 py-0.5 rounded bg-stone-100 text-stone-600">
                  Locations:{" "}
                  <strong>
                    {result.parsed_intent.locations_mentioned.join(", ")}
                  </strong>
                </span>
              )}
              {result.parsed_intent?.resources_mentioned?.length > 0 && (
                <span className="px-2 py-0.5 rounded bg-stone-100 text-stone-600">
                  Resources: <strong>
                    {result.parsed_intent.resources_mentioned
                      .map((r) => r.raw_phrase)
                      .join(", ")}
                  </strong>
                </span>
              )}
            </div>
          </div>

          {/* Extracted resources */}
          <ExtractedResources
            resources={result.parsed_intent?.resources_mentioned}
          />

          {/* Clarification needed */}
          <ClarificationNeeded
            items={result.clarification_needed}
          />

          {/* Unresolved locations */}
          <UnresolvedLocations
            locations={result.unresolved_locations}
          />

          {/* Capability gaps */}
          <CapabilityGaps gaps={result.capability_gaps} />

          {/* Allocation plan */}
          <AllocationPlan plan={result.allocation_plan} />

          {/* Resolved location results */}
          {result.resolved_locations?.length > 0 && (
            <div className="space-y-3">
              <h3 className="text-[13px] font-semibold text-stone-400 uppercase tracking-wider">
                Location Assessments ({result.resolved_locations.length})
              </h3>
              {result.resolved_locations.map((loc, i) => (
                <div key={i} className="text-[12px] text-stone-500">
                  <LocationResult assessment={loc} />
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------
   Inline location result card — reuses existing data shapes
   ------------------------------------------------------------------ */

function LocationResult({ assessment }) {
  if (!assessment) return null;

  const { priority, evidence, coordinates } = assessment;
  const locLabel = assessment.location?.replace(/_/g, " ") || "Unknown";

  return (
    <div className="rounded-xl border border-stone-200 bg-white p-4 shadow-sm">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <MapPin className="w-4 h-4 text-stone-400" />
          <span className="text-[14px] font-semibold text-stone-800">
            {locLabel}
          </span>
        </div>
        {coordinates && (
          <span className="text-[10px] text-stone-400 font-mono">
            {coordinates.lat?.toFixed(4)}°N, {coordinates.lon?.toFixed(4)}°E
          </span>
        )}
      </div>

      {/* Priority badge */}
      <div className="flex items-center gap-3 mb-3">
        <span
          className={cn(
            "px-2.5 py-1 rounded-md text-[12px] font-bold border",
            priority.category === "HIGH PRIORITY"
              ? "bg-red-50 text-red-700 border-red-200"
              : priority.category === "PRIORITY"
              ? "bg-red-50 text-red-600 border-red-200"
              : priority.category === "EXPOSED"
              ? "bg-amber-50 text-amber-600 border-amber-200"
              : priority.category === "SAFE"
              ? "bg-green-50 text-green-600 border-green-200"
              : "bg-stone-50 text-stone-600 border-stone-200"
          )}
        >
          {priority.category}
        </span>
        <span className="text-[12px] font-mono text-stone-500">
          PDC {priority.pdc_score.toFixed(2)}
        </span>
      </div>

      {/* Quick evidence summary */}
      <div className="grid grid-cols-3 gap-2">
        <EvidenceMini
          label="Flood"
          value={
            evidence.flood?.flooded ? "Flooded" : "Not flooded"
          }
          available={evidence.flood?.status === "available"}
        />
        <EvidenceMini
          label="Buildings"
          value={
            evidence.exposure?.total_buildings > 0
              ? `${evidence.exposure.exposed_count}/${evidence.exposure.total_buildings} exposed`
              : "No data"
          }
          available={evidence.exposure?.status === "available"}
        />
        <EvidenceMini
          label="Medical"
          value={
            evidence.accessibility?.medical_distance_km >= 0
              ? `${evidence.accessibility.medical_distance_km.toFixed(1)} km`
              : "Unknown"
          }
          available={evidence.accessibility?.status === "available"}
        />
      </div>

      {/* Recommendation */}
      <div className="mt-3 bg-stone-50 rounded-lg border border-stone-100 p-2.5">
        <p className="text-[12px] text-stone-600 leading-relaxed">
          {priority.recommendation}
        </p>
      </div>
    </div>
  );
}

function EvidenceMini({ label, value, available }) {
  return (
    <div
      className={cn(
        "rounded-lg border p-2 text-center",
        available
          ? "bg-stone-50 border-stone-100"
          : "bg-stone-50/50 border-stone-100/50"
      )}
    >
      <div className="text-[10px] text-stone-400 uppercase tracking-wider mb-0.5">
        {label}
      </div>
      <div
        className={cn(
          "text-[12px] font-semibold",
          available ? "text-stone-700" : "text-stone-400"
        )}
      >
        {value}
      </div>
    </div>
  );
}
