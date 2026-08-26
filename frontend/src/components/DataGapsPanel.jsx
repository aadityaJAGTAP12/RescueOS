import { Info } from "lucide-react";
import { cn } from "../lib/utils";

const STATUS_CONFIG = {
  not_connected: {
    label: "Not Connected",
    color: "bg-amber-50 text-amber-700 border-amber-200/60",
    iconColor: "text-amber-500",
  },
  not_available: {
    label: "Not Available",
    color: "bg-blue-50 text-blue-700 border-blue-200/60",
    iconColor: "text-blue-500",
  },
  not_implemented: {
    label: "Planned",
    color: "bg-stone-100 text-stone-600 border-stone-200",
    iconColor: "text-stone-400",
  },
};

export default function DataGapsPanel({ dataGaps, loading }) {
  if (loading) {
    return (
      <div className="rounded-xl border border-stone-200 bg-white p-4 shadow-sm space-y-3">
        <div className="skeleton h-5 w-48 rounded" />
        {[1, 2, 3].map((i) => (
          <div key={i} className="skeleton h-10 rounded-lg" />
        ))}
      </div>
    );
  }

  if (!dataGaps || dataGaps.length === 0) return null;

  return (
    <div className="rounded-xl border border-stone-200 bg-white p-4 shadow-sm">
      {/* Header */}
      <div className="flex items-center gap-2 mb-3">
        <div className="flex items-center justify-center w-7 h-7 rounded-lg bg-stone-100">
          <Info className="w-4 h-4 text-stone-500" />
        </div>
        <h3 className="text-[13px] font-semibold text-stone-800">
          Current System Scope
        </h3>
      </div>

      <p className="text-[12px] text-stone-500 mb-3 leading-relaxed">
        Known integrations and planned capabilities. This reflects honest system
        boundaries, not unfinished work.
      </p>

      {/* Gap items */}
      <div className="space-y-2">
        {dataGaps.map((gap) => {
          const statusStyle = STATUS_CONFIG[gap.status] || STATUS_CONFIG.not_implemented;
          return (
            <div
              key={gap.item}
              className="flex items-start gap-3 p-2.5 rounded-lg bg-stone-50/80 border border-stone-100"
            >
              <div className={cn("w-2 h-2 rounded-full mt-1.5 shrink-0", statusStyle.iconColor.replace("text-", "bg-"))} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5">
                  <span className="text-[12px] font-semibold text-stone-700">
                    {gap.item}
                  </span>
                  <span
                    className={cn(
                      "inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-semibold uppercase tracking-wider border",
                      statusStyle.color
                    )}
                  >
                    {statusStyle.label}
                  </span>
                </div>
                {gap.detail && (
                  <p className="text-[11px] text-stone-400 leading-relaxed">
                    {gap.detail}
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
