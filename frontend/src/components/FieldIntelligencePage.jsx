import { useState, useEffect } from "react";
import {
  FileText,
  Send,
  MapPin,
  Users,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Clock,
  Shield,
  Road,
  Building2,
  CheckCircle2,
  XCircle,
} from "lucide-react";
import { cn, humanizeKey } from "../lib/utils";
import { formatDistanceToNow } from "date-fns";

/* ------------------------------------------------------------------
   Confidence badge
   ------------------------------------------------------------------ */

function ConfidenceBadge({ confidence }) {
  const styles = {
    high: "bg-green-50 text-green-700 border-green-200/60",
    medium: "bg-amber-50 text-amber-700 border-amber-200/60",
    low: "bg-red-50 text-red-700 border-red-200/60",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold uppercase tracking-wider border",
        styles[confidence] || styles.low
      )}
    >
      {confidence} confidence
    </span>
  );
}

/* ------------------------------------------------------------------
   Extraction result card
   ------------------------------------------------------------------ */

function ExtractionCard({ extraction }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="rounded-xl border border-stone-200 bg-white p-4 shadow-sm slide-up">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className="flex items-center justify-center w-7 h-7 rounded-lg bg-indigo-50">
            <FileText className="w-4 h-4 text-indigo-600" />
          </div>
          <span className="text-[13px] font-semibold text-stone-800">
            Extraction Result
          </span>
        </div>
        <ConfidenceBadge confidence={extraction.extraction_confidence} />
      </div>

      {/* Structured fields */}
      <div className="grid grid-cols-2 gap-2 mb-3">
        {/* Location */}
        <div className="bg-stone-50/80 rounded-lg px-3 py-2">
          <div className="text-[10px] font-medium text-stone-400 uppercase tracking-wider mb-0.5">
            Location
          </div>
          <div className="text-[13px] font-semibold text-stone-700">
            {extraction.location_description || "—"}
          </div>
          {!extraction.location_resolved && extraction.location_description && (
            <div className="text-[10px] text-amber-600 mt-0.5">
              Not resolved to coordinates
            </div>
          )}
        </div>

        {/* People count */}
        <div className="bg-stone-50/80 rounded-lg px-3 py-2">
          <div className="text-[10px] font-medium text-stone-400 uppercase tracking-wider mb-0.5">
            People Count
          </div>
          <div className="text-[13px] font-semibold text-stone-700">
            {extraction.people_count ?? "—"}
          </div>
        </div>

        {/* Needs */}
        <div className="bg-stone-50/80 rounded-lg px-3 py-2 col-span-2">
          <div className="text-[10px] font-medium text-stone-400 uppercase tracking-wider mb-1">
            Needs
          </div>
          <div className="flex flex-wrap gap-1">
            {extraction.needs && extraction.needs.length > 0 ? (
              extraction.needs.map((need) => (
                <span
                  key={need}
                  className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-amber-50 text-amber-700 border border-amber-200/60"
                >
                  {need.replace(/_/g, " ")}
                </span>
              ))
            ) : (
              <span className="text-[12px] text-stone-400">None identified</span>
            )}
          </div>
        </div>

        {/* Road mentions */}
        {extraction.road_status_mentions && extraction.road_status_mentions.length > 0 && (
          <div className="bg-stone-50/80 rounded-lg px-3 py-2 col-span-2">
            <div className="text-[10px] font-medium text-stone-400 uppercase tracking-wider mb-1">
              Road Status Mentions
            </div>
            <div className="space-y-1">
              {extraction.road_status_mentions.map((road, i) => (
                <div key={i} className="flex items-center gap-2 text-[12px]">
                  <Road className="w-3 h-3 text-stone-400" />
                  <span className="text-stone-600">{road.road_description || road}</span>
                  {road.status && (
                    <span className={cn(
                      "px-1.5 py-0.5 rounded text-[9px] font-semibold uppercase",
                      road.status === "blocked" ? "bg-red-50 text-red-600" :
                      road.status === "damaged" ? "bg-amber-50 text-amber-600" :
                      "bg-green-50 text-green-600"
                    )}>
                      {road.status}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Facility mentions */}
        {extraction.facility_status_mentions && extraction.facility_status_mentions.length > 0 && (
          <div className="bg-stone-50/80 rounded-lg px-3 py-2 col-span-2">
            <div className="text-[10px] font-medium text-stone-400 uppercase tracking-wider mb-1">
              Facility Status Mentions
            </div>
            <div className="space-y-1">
              {extraction.facility_status_mentions.map((fac, i) => (
                <div key={i} className="flex items-center gap-2 text-[12px]">
                  <Building2 className="w-3 h-3 text-stone-400" />
                  <span className="text-stone-600">{fac.facility_description || fac}</span>
                  {fac.status && (
                    <span className={cn(
                      "px-1.5 py-0.5 rounded text-[9px] font-semibold uppercase",
                      fac.status === "submerged" ? "bg-red-50 text-red-600" :
                      fac.status === "damaged" ? "bg-amber-50 text-amber-600" :
                      "bg-green-50 text-green-600"
                    )}>
                      {fac.status}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Note */}
        {extraction.note && (
          <div className="bg-stone-50/80 rounded-lg px-3 py-2 col-span-2">
            <div className="text-[10px] font-medium text-stone-400 uppercase tracking-wider mb-0.5">
              Note
            </div>
            <div className="text-[12px] text-stone-600">{extraction.note}</div>
          </div>
        )}
      </div>

      {/* Raw text — collapsible */}
      <div className="border border-stone-100 rounded-lg overflow-hidden">
        <button
          onClick={() => setExpanded(!expanded)}
          className="w-full flex items-center justify-between px-3 py-2 text-[12px] font-medium text-stone-500 hover:bg-stone-50 transition-colors"
        >
          <span className="flex items-center gap-1.5">
            <FileText className="w-3 h-3" />
            Original Report
          </span>
          {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
        </button>
        {expanded && (
          <div className="px-3 pb-3">
            <p className="text-[12px] text-stone-600 leading-relaxed bg-stone-50 rounded p-2 font-mono">
              {extraction.raw_text}
            </p>
          </div>
        )}
      </div>

      {/* Timestamp */}
      {extraction.extracted_at && (
        <div className="mt-2 text-[10px] text-stone-400 flex items-center gap-1">
          <Clock className="w-3 h-3" />
          Extracted {formatDistanceToNow(new Date(extraction.extracted_at), { addSuffix: true })}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------
   Main FieldIntelligencePage
   ------------------------------------------------------------------ */

export default function FieldIntelligencePage() {
  const [rawText, setRawText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);
  const [history, setHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(true);

  // Load history on mount
  useEffect(() => {
    fetchHistory();
  }, []);

  const fetchHistory = async () => {
    setHistoryLoading(true);
    try {
      const resp = await fetch("/api/field-intelligence/history");
      const data = await resp.json();
      setHistory(data.reports || []);
    } catch {
      // ignore
    } finally {
      setHistoryLoading(false);
    }
  };

  const handleSubmit = async () => {
    if (!rawText.trim()) return;
    setSubmitting(true);
    setResult(null);
    try {
      const resp = await fetch("/api/field-intelligence", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ raw_text: rawText }),
      });
      const data = await resp.json();
      setResult(data);
      setRawText("");
      // Refresh history
      fetchHistory();
    } catch (err) {
      setResult({ error: err.message });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      {/* Page header */}
      <div>
        <h2 className="text-lg font-semibold text-stone-900 flex items-center gap-2">
          <FileText className="w-5 h-5 text-stone-400" />
          Field Intelligence Intake
        </h2>
        <p className="text-[13px] text-stone-500 mt-1">
          Submit a raw field observation. The system extracts structured data via AI
          while preserving the original text as the authoritative source.
        </p>
      </div>

      {/* Input form */}
      <div className="rounded-xl border border-stone-200 bg-white p-5 shadow-sm">
        <label className="block text-[12px] font-semibold text-stone-500 uppercase tracking-wider mb-2">
          Field Observation
        </label>
        <textarea
          value={rawText}
          onChange={(e) => setRawText(e.target.value)}
          placeholder="e.g. Road to Dibrugarh blocked near old bridge. 200 people at school need food and water. Hospital running but low supplies..."
          className="w-full h-40 px-4 py-3 rounded-lg border border-stone-200 bg-stone-50/50 text-[14px] text-stone-800 placeholder:text-stone-400 resize-none focus:outline-none focus:ring-2 focus:ring-stone-300 focus:border-stone-300 transition-all"
          disabled={submitting}
        />
        <div className="flex items-center justify-between mt-3">
          <span className="text-[11px] text-stone-400">
            {rawText.length > 0 ? `${rawText.length} characters` : "Type or paste a field report"}
          </span>
          <button
            onClick={handleSubmit}
            disabled={!rawText.trim() || submitting}
            className={cn(
              "flex items-center gap-2 px-4 py-2 rounded-lg text-[13px] font-semibold transition-all duration-200",
              rawText.trim() && !submitting
                ? "bg-stone-900 text-white hover:bg-stone-800 shadow-sm"
                : "bg-stone-100 text-stone-400 cursor-not-allowed"
            )}
          >
            {submitting ? (
              <>
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Analyzing report...
              </>
            ) : (
              <>
                <Send className="w-3.5 h-3.5" />
                Extract & Submit
              </>
            )}
          </button>
        </div>
      </div>

      {/* Extraction result */}
      {result && result.extraction && <ExtractionCard extraction={result.extraction} />}
      {result && result.error && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-[13px] text-red-700">
          Error: {result.error}
        </div>
      )}

      {/* History */}
      <div>
        <h3 className="text-[13px] font-semibold text-stone-400 uppercase tracking-wider mb-3">
          Submission History
        </h3>
        {historyLoading ? (
          <div className="space-y-3">
            {[1, 2].map((i) => (
              <div key={i} className="skeleton h-20 rounded-xl" />
            ))}
          </div>
        ) : history.length === 0 ? (
          <div className="text-center py-8 text-[13px] text-stone-400">
            No field intelligence reports submitted yet.
          </div>
        ) : (
          <div className="space-y-3">
            {history.map((report) => (
              <div
                key={report.id}
                className="rounded-xl border border-stone-200 bg-white p-4 shadow-sm"
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <ConfidenceBadge confidence={report.extraction_confidence} />
                    {report.location_description && (
                      <span className="flex items-center gap-1 text-[11px] text-stone-500">
                        <MapPin className="w-3 h-3" />
                        {report.location_description}
                      </span>
                    )}
                  </div>
                  <span className="text-[10px] text-stone-400">
                    {report.timestamp
                      ? formatDistanceToNow(new Date(report.timestamp), { addSuffix: true })
                      : ""}
                  </span>
                </div>
                <p className="text-[12px] text-stone-600 line-clamp-2 mb-2">
                  {report.raw_text || report.note}
                </p>
                {report.needs && report.needs.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {report.needs.map((need) => (
                      <span
                        key={need}
                        className="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-medium bg-amber-50 text-amber-700 border border-amber-200/60"
                      >
                        {need.replace(/_/g, " ")}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
