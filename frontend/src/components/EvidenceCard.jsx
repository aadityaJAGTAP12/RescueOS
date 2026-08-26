import {
  Droplets,
  Building2,
  Stethoscope,
  Users,
  HelpCircle,
} from "lucide-react";
import { humanizeKey, formatValue, getEvidenceFields, cn } from "../lib/utils";
import { formatDistanceToNow } from "date-fns";

/* ------------------------------------------------------------------
   Icon mapping for evidence types
   ------------------------------------------------------------------ */

const EVIDENCE_ICONS = {
  flood: Droplets,
  exposure: Building2,
  accessibility: Stethoscope,
  field_reports: Users,
};

function getEvidenceIcon(key) {
  return EVIDENCE_ICONS[key] || HelpCircle;
}

/* ------------------------------------------------------------------
   Status badge
   ------------------------------------------------------------------ */

function StatusBadge({ status }) {
  const styles = {
    available: "bg-green-50 text-green-700 border-green-200/60",
    unavailable: "bg-stone-50 text-stone-500 border-stone-200",
    none: "bg-stone-50 text-stone-400 border-stone-200",
  };

  return (
    <span
      className={cn(
        "inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider border",
        styles[status] || styles.none
      )}
    >
      {status}
    </span>
  );
}

/* ------------------------------------------------------------------
   Humanized timestamp
   ------------------------------------------------------------------ */

function HumanizedTimestamp({ isoString }) {
  if (!isoString) return <span className="text-stone-400">—</span>;

  try {
    const date = new Date(isoString);
    const relative = formatDistanceToNow(date, { addSuffix: true });
    return (
      <span className="text-stone-400" title={isoString}>
        Updated {relative}
      </span>
    );
  } catch {
    return <span className="text-stone-400">{isoString}</span>;
  }
}

/* ------------------------------------------------------------------
   Field reports special rendering
   ------------------------------------------------------------------ */

function FieldReportsContent({ data }) {
  const reports = data.reports || [];

  if (reports.length === 0) {
    return (
      <div className="py-4 text-center">
        <Users className="w-8 h-8 text-stone-200 mx-auto mb-2" />
        <p className="text-[13px] text-stone-400">
          No field reports for this location
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-2.5">
      {reports.map((report) => (
        <div
          key={report.report_id}
          className="rounded-lg border border-stone-100 bg-stone-50/50 p-3"
        >
          <div className="flex items-center justify-between mb-2">
            <span className="text-[13px] font-semibold text-stone-700">
              {report.people_count} people
            </span>
            {!report.verified && (
              <span className="text-[10px] font-bold text-amber-600 uppercase tracking-wider">
                Unverified
              </span>
            )}
          </div>
          <div className="text-[11px] text-stone-500 mb-2">
            Adults: {report.adults} · Children: {report.children} · Elderly:{" "}
            {report.elderly}
          </div>
          {report.needs && report.needs.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {report.needs.map((need) => (
                <span
                  key={need}
                  className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-amber-50 text-amber-700 border border-amber-200/60"
                >
                  {need.replace(/_/g, " ")}
                </span>
              ))}
            </div>
          )}
          {report.submitted_at && (
            <div className="mt-2 text-[10px] text-stone-400">
              Submitted {report.submitted_at}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------
   Main EvidenceCard component
   ------------------------------------------------------------------ */

export default function EvidenceCard({ evidenceKey, evidenceData }) {
  const Icon = getEvidenceIcon(evidenceKey);
  const title = humanizeKey(evidenceKey);
  const fields = getEvidenceFields(evidenceKey, evidenceData);

  return (
    <div className="rounded-xl border border-stone-200 bg-white p-4 shadow-sm transition-all duration-200 hover:shadow-md">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className="flex items-center justify-center w-7 h-7 rounded-lg bg-stone-100">
            <Icon className="w-4 h-4 text-stone-500" />
          </div>
          <h3 className="text-[13px] font-semibold text-stone-800">{title}</h3>
        </div>
        <StatusBadge status={evidenceData.status} />
      </div>

      {/* Source and timestamp */}
      <div className="flex items-center justify-between mb-3">
        <span className="text-[11px] text-stone-400">
          {evidenceData.source}
        </span>
        <HumanizedTimestamp isoString={evidenceData.last_updated} />
      </div>

      {/* Content */}
      {evidenceKey === "field_reports" ? (
        <FieldReportsContent data={evidenceData} />
      ) : fields && fields.length > 0 ? (
        <div className="grid grid-cols-2 gap-2">
          {fields.map(([key, value]) => (
            <div key={key} className="bg-stone-50/80 rounded-lg px-3 py-2">
              <div className="text-[10px] font-medium text-stone-400 uppercase tracking-wider mb-0.5">
                {humanizeKey(key)}
              </div>
              <div className="text-[13px] font-semibold text-stone-700 tabular-nums">
                {formatValue(key, value)}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="py-3 text-center text-[13px] text-stone-400">
          No data available
        </div>
      )}
    </div>
  );
}
