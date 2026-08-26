import EvidenceCard from "./EvidenceCard";
import { Layers } from "lucide-react";

export default function EvidencePanel({ assessment, loading }) {
  if (loading) {
    return (
      <div className="space-y-3">
        <div className="flex items-center gap-2 mb-2">
          <div className="skeleton h-5 w-32 rounded" />
        </div>
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            className="rounded-xl border border-stone-200 bg-white p-4 shadow-sm space-y-3"
          >
            <div className="flex items-center gap-2">
              <div className="skeleton h-7 w-7 rounded-lg" />
              <div className="skeleton h-4 w-32 rounded" />
            </div>
            <div className="skeleton h-3 w-48 rounded" />
            <div className="grid grid-cols-2 gap-2">
              <div className="skeleton h-14 rounded-lg" />
              <div className="skeleton h-14 rounded-lg" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (!assessment?.evidence) return null;

  const evidenceEntries = Object.entries(assessment.evidence);

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 mb-1">
        <Layers className="w-4 h-4 text-stone-400" />
        <h2 className="text-[13px] font-semibold text-stone-400 uppercase tracking-wider">
          Evidence Sources
        </h2>
      </div>

      {evidenceEntries.map(([key, data]) => (
        <EvidenceCard key={key} evidenceKey={key} evidenceData={data} />
      ))}
    </div>
  );
}
