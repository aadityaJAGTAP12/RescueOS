import { getCategoryStyle, cn } from "../lib/utils";
import { TrendingUp, Target, AlertCircle } from "lucide-react";

/* ------------------------------------------------------------------
   PDC Score Gauge — visual scale showing the 35/35/30 weighting
   ------------------------------------------------------------------ */

function PDCGauge({ score, category }) {
  const percentage = Math.round(score * 100);
  const catStyle = getCategoryStyle(category);

  // Color stops for the gauge track
  const gaugeColor =
    score >= 0.75
      ? "#991b1b"
      : score >= 0.5
      ? "#dc2626"
      : score >= 0.25
      ? "#d97706"
      : "#16a34a";

  return (
    <div className="flex items-center gap-3">
      <div className="relative flex-1 h-2 bg-stone-100 rounded-full overflow-hidden">
        <div
          className="absolute inset-y-0 left-0 rounded-full transition-all duration-700 ease-out"
          style={{
            width: `${percentage}%`,
            backgroundColor: gaugeColor,
          }}
        />
        {/* Threshold markers */}
        <div className="absolute top-0 bottom-0 left-[25%] w-px bg-stone-300/50" />
        <div className="absolute top-0 bottom-0 left-[50%] w-px bg-stone-300/50" />
        <div className="absolute top-0 bottom-0 left-[75%] w-px bg-stone-300/50" />
      </div>
      <span className="text-[13px] font-mono font-semibold text-stone-700 tabular-nums w-10 text-right">
        {score.toFixed(2)}
      </span>
    </div>
  );
}

/* ------------------------------------------------------------------
   Weight breakdown pills — shows the 35/35/30 formula
   ------------------------------------------------------------------ */

function WeightBreakdown() {
  const weights = [
    { label: "Exposure", weight: "35%", color: "bg-blue-50 text-blue-700 border-blue-200/60" },
    { label: "Flood Scale", weight: "35%", color: "bg-cyan-50 text-cyan-700 border-cyan-200/60" },
    { label: "Accessibility", weight: "30%", color: "bg-violet-50 text-violet-700 border-violet-200/60" },
  ];

  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      {weights.map((w) => (
        <span
          key={w.label}
          className={cn(
            "inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold border",
            w.color
          )}
        >
          {w.label}
          <span className="opacity-60">{w.weight}</span>
        </span>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------
   Main OperationalAnswer component
   ------------------------------------------------------------------ */

export default function OperationalAnswer({ assessment, loading }) {
  if (loading) {
    return (
      <div className="rounded-xl border border-stone-200 bg-white p-5 shadow-sm space-y-4">
        <div className="skeleton h-5 w-40 rounded" />
        <div className="skeleton h-8 w-32 rounded" />
        <div className="skeleton h-2 w-full rounded-full" />
        <div className="skeleton h-4 w-full rounded" />
        <div className="skeleton h-4 w-3/4 rounded" />
      </div>
    );
  }

  if (!assessment) return null;

  const { priority } = assessment;
  const catStyle = getCategoryStyle(priority.category);

  return (
    <div
      className={cn(
        "rounded-xl border bg-white p-5 shadow-sm transition-all duration-300",
        catStyle.border
      )}
      style={{
        borderLeftWidth: "4px",
        borderLeftColor:
          priority.category === "HIGH PRIORITY"
            ? "#991b1b"
            : priority.category === "PRIORITY"
            ? "#dc2626"
            : priority.category === "EXPOSED"
            ? "#d97706"
            : "#16a34a",
      }}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Target className="w-4 h-4 text-stone-400" />
          <span className="text-[12px] font-semibold text-stone-400 uppercase tracking-wider">
            Priority Assessment
          </span>
        </div>
        <WeightBreakdown />
      </div>

      {/* Category display */}
      <div className="mb-3">
        <div className={cn("text-2xl font-bold tracking-tight", catStyle.color)}>
          {priority.category}
        </div>
      </div>

      {/* PDC Score gauge */}
      <div className="mb-4">
        <div className="flex items-center gap-2 mb-1.5">
          <span className="text-[11px] font-medium text-stone-400 uppercase tracking-wider">
            PDC Score
          </span>
        </div>
        <PDCGauge score={priority.pdc_score} category={priority.category} />
      </div>

      {/* Recommendation */}
      <div className="bg-stone-50 rounded-lg border border-stone-100 p-3">
        <div className="flex items-start gap-2">
          <AlertCircle className="w-4 h-4 text-stone-400 mt-0.5 shrink-0" />
          <p className="text-[13px] text-stone-700 leading-relaxed">
            {priority.recommendation}
          </p>
        </div>
      </div>

      {/* Location coordinates */}
      {assessment.coordinates && (
        <div className="mt-3 text-[11px] text-stone-400 font-mono">
          {assessment.coordinates.lat?.toFixed(4)}°N, {assessment.coordinates.lon?.toFixed(4)}°E
        </div>
      )}
    </div>
  );
}
