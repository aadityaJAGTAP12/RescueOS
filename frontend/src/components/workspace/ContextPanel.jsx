import { useState, useEffect, useCallback } from "react";
import {
  X, ArrowLeft, AlertTriangle, Package, Zap, FileText, Shield,
  Stethoscope, MapPin, Clock, Users, ChevronDown, Route,
  CheckCircle, Search, Handshake,
} from "lucide-react";
import { useWorkspace } from "../../lib/workspaceContext";
import { cn } from "../../lib/utils";
import { formatDistanceToNow } from "date-fns";

// -------------------------------------------------------------------
// Panel header
// -------------------------------------------------------------------

function PanelHeader({ icon: Icon, title, subtitle, onClose, color = "#c8d6e5" }) {
  return (
    <div className="flex items-center justify-between px-4 py-3 border-b border-[#2a3a4e]">
      <div className="flex items-center gap-2.5">
        <div
          className="w-7 h-7 rounded flex items-center justify-center"
          style={{ backgroundColor: `${color}15` }}
        >
          <Icon className="w-3.5 h-3.5" style={{ color }} />
        </div>
        <div>
          <h3 className="text-[13px] font-semibold" style={{ color }}>
            {title}
          </h3>
          {subtitle && (
            <p className="text-[10px] text-[#6b7d93] mt-0.5">{subtitle}</p>
          )}
        </div>
      </div>
      <button
        onClick={onClose}
        className="w-6 h-6 rounded flex items-center justify-center hover:bg-[#1a2332] transition-colors"
      >
        <X className="w-3.5 h-3.5 text-[#6b7d93]" />
      </button>
    </div>
  );
}

// -------------------------------------------------------------------
// Status badge
// -------------------------------------------------------------------

function StatusBadge({ status, color }) {
  return (
    <span
      className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider border"
      style={{
        color,
        backgroundColor: `${color}15`,
        borderColor: `${color}30`,
      }}
    >
      {status}
    </span>
  );
}

// -------------------------------------------------------------------
// Need detail panel
// -------------------------------------------------------------------

function NeedDetail({ data, onClose, onOpenMatch }) {
  const [need, setNeed] = useState(data);
  const [updating, setUpdating] = useState(false);
  const [matches, setMatches] = useState(null);
  const [loadingMatches, setLoadingMatches] = useState(false);

  const handleStatusChange = async (newStatus) => {
    setUpdating(true);
    try {
      const resp = await fetch(`/api/needs/${need.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: newStatus, actor: "coordinator" }),
      });
      if (resp.ok) {
        const result = await resp.json();
        setNeed(result.need);
      }
    } catch (err) {
      console.error("Failed to update need:", err);
    } finally {
      setUpdating(false);
    }
  };

  const urgencyColor = {
    critical: "#dc2626",
    high: "#d97706",
    medium: "#eab308",
    low: "#16a34a",
  };

  const handleFindResources = async () => {
    setLoadingMatches(true);
    try {
      const resp = await fetch(`/api/needs/${need.id}/matches`);
      if (resp.ok) {
        const result = await resp.json();
        setMatches(result);
      }
    } catch (err) {
      console.error("Failed to fetch matches:", err);
    } finally {
      setLoadingMatches(false);
    }
  };

  const handleConfirmMatch = async (offerId) => {
    try {
      const resp = await fetch(`/api/matches/${need.id}/${offerId}/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      if (resp.ok) {
        const result = await resp.json();
        // Refresh need status
        setNeed({ ...need, status: "RESPONDING" });
        // Refresh matches to show updated state
        handleFindResources();
      }
    } catch (err) {
      console.error("Failed to confirm match:", err);
    }
  };

  return (
    <>
      <PanelHeader
        icon={AlertTriangle}
        title={need.title}
        subtitle={`Need · ${need.need_type}`}
        onClose={onClose}
        color={urgencyColor[need.urgency] || "#c8d6e5"}
      />
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Status & Urgency */}
        <div className="flex items-center gap-2 flex-wrap">
          <StatusBadge status={need.status} color="#4ea8de" />
          <StatusBadge
            status={need.urgency}
            color={urgencyColor[need.urgency] || "#78716c"}
          />
        </div>

        {/* Location */}
        {need.location_name && (
          <div className="flex items-center gap-2 text-[12px] text-[#c8d6e5]">
            <MapPin className="w-3.5 h-3.5 text-[#6b7d93]" />
            {need.location_name}
          </div>
        )}

        {/* Description */}
        {need.description && (
          <div className="text-[12px] text-[#a0aec0] leading-relaxed">
            {need.description}
          </div>
        )}

        {/* Requested resources */}
        {need.requested_resources && need.requested_resources.length > 0 && (
          <div>
            <div className="text-[10px] font-semibold text-[#6b7d93] uppercase tracking-wider mb-1.5">
              Requested Resources
            </div>
            <div className="space-y-1">
              {need.requested_resources.map((r, i) => (
                <div
                  key={i}
                  className="flex items-center gap-2 px-2.5 py-1.5 rounded bg-[#1a2332] border border-[#2a3a4e]"
                >
                  <Package className="w-3 h-3 text-[#0d9488]" />
                  <span className="text-[11px] text-[#c8d6e5]">
                    {r.quantity || r.type} {r.unit || r.type}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Timestamps */}
        <div className="text-[10px] text-[#6b7d93] space-y-0.5">
          {need.created_at && (
            <div>
              Created:{" "}
              {formatDistanceToNow(new Date(need.created_at), { addSuffix: true })}
            </div>
          )}
          {need.updated_at && (
            <div>
              Updated:{" "}
              {formatDistanceToNow(new Date(need.updated_at), { addSuffix: true })}
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="border-t border-[#2a3a4e] pt-3 space-y-2">
          <div className="text-[10px] font-semibold text-[#6b7d93] uppercase tracking-wider mb-1">
            Actions
          </div>
          <div className="flex flex-wrap gap-1.5">
            {need.status === "OPEN" && (
              <button
                onClick={handleFindResources}
                disabled={loadingMatches}
                className="px-2.5 py-1 rounded text-[11px] font-medium bg-purple-500/10 text-purple-400 border border-purple-500/20 hover:bg-purple-500/20 transition-colors"
              >
                <Search className="w-3 h-3 inline mr-1" />
                {loadingMatches ? "Searching..." : "Find Resources"}
              </button>
            )}
            {need.status === "OPEN" && (
              <button
                onClick={() => handleStatusChange("RESPONDING")}
                disabled={updating}
                className="px-2.5 py-1 rounded text-[11px] font-medium bg-blue-500/10 text-blue-400 border border-blue-500/20 hover:bg-blue-500/20 transition-colors"
              >
                Join Response
              </button>
            )}
            {need.status === "RESPONDING" && (
              <button
                onClick={() => handleStatusChange("RESOLVED")}
                disabled={updating}
                className="px-2.5 py-1 rounded text-[11px] font-medium bg-green-500/10 text-green-400 border border-green-500/20 hover:bg-green-500/20 transition-colors"
              >
                Mark Resolved
              </button>
            )}
            {need.status !== "CLOSED" && need.status !== "RESOLVED" && (
              <button
                onClick={() => handleStatusChange("CLOSED")}
                disabled={updating}
                className="px-2.5 py-1 rounded text-[11px] font-medium bg-stone-500/10 text-stone-400 border border-stone-500/20 hover:bg-stone-500/20 transition-colors"
              >
                Close
              </button>
            )}
          </div>
        </div>

        {/* Matches display */}
        {matches && matches.matches && (
          <div className="border-t border-[#2a3a4e] pt-3 space-y-2">
            <div className="text-[10px] font-semibold text-[#6b7d93] uppercase tracking-wider mb-1">
              Resource Matches ({matches.matches.length} found)
            </div>
            {matches.matches.length === 0 && (
              <div className="text-[11px] text-[#6b7d93] p-2 rounded bg-[#1a2332] border border-[#2a3a4e]">
                No compatible resource offers found at this time.
              </div>
            )}
            {matches.matches.map((match) => (
              <div
                key={match.offer_id}
                className={cn(
                  "p-2.5 rounded border space-y-1.5",
                  match.compatibility === "HIGH"
                    ? "bg-green-500/5 border-green-500/20"
                    : match.compatibility === "MEDIUM"
                    ? "bg-amber-500/5 border-amber-500/20"
                    : "bg-[#1a2332] border-[#2a3a4e]"
                )}
              >
                <div className="flex items-center justify-between">
                  <div className="text-[11px] font-semibold text-[#c8d6e5]">
                    {match.offer?.resource_type || "Resource"} — {match.available_quantity} {match.offer?.unit || "units"}
                  </div>
                  <StatusBadge
                    status={match.compatibility}
                    color={
                      match.compatibility === "HIGH"
                        ? "#16a34a"
                        : match.compatibility === "MEDIUM"
                        ? "#d97706"
                        : "#6b7d93"
                    }
                  />
                </div>
                <div className="text-[10px] text-[#6b7d93]">
                  {match.offer?.organization_id} · {match.offer?.location_name || match.offer?.district_id}
                </div>
                {match.unmet_quantity > 0 && (
                  <div className="text-[10px] text-amber-400">
                    Partial: {match.allocatable_quantity}/{match.requested_quantity} available
                  </div>
                )}
                <div className="space-y-0.5">
                  {match.reasons.slice(0, 3).map((reason, i) => (
                    <div key={i} className="text-[9px] text-[#6b7d93]">• {reason}</div>
                  ))}
                </div>
                {need.status === "OPEN" && (
                  <button
                    onClick={() => handleConfirmMatch(match.offer_id)}
                    className="w-full mt-1.5 px-2.5 py-1.5 rounded text-[11px] font-semibold bg-green-500/15 text-green-400 border border-green-500/30 hover:bg-green-500/25 transition-colors"
                  >
                    <Handshake className="w-3 h-3 inline mr-1" />
                    Confirm Collaboration
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}

// -------------------------------------------------------------------
// Operation detail panel
// -------------------------------------------------------------------

function OperationDetail({ data, onClose }) {
  const [operation, setOperation] = useState(data);

  const statusColor = {
    PLANNING: "#2563eb",
    ACTIVE: "#16a34a",
    PAUSED: "#d97706",
    COMPLETED: "#6b7280",
    CANCELLED: "#9ca3af",
  };

  return (
    <>
      <PanelHeader
        icon={Zap}
        title={operation.name}
        subtitle={`Operation · ${operation.operation_type}`}
        onClose={onClose}
        color={statusColor[operation.status] || "#c8d6e5"}
      />
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        <div className="flex items-center gap-2">
          <StatusBadge
            status={operation.status}
            color={statusColor[operation.status] || "#78716c"}
          />
        </div>

        {operation.description && (
          <div className="text-[12px] text-[#a0aec0] leading-relaxed">
            {operation.description}
          </div>
        )}

        {operation.location_name && (
          <div className="flex items-center gap-2 text-[12px] text-[#c8d6e5]">
            <MapPin className="w-3.5 h-3.5 text-[#6b7d93]" />
            {operation.location_name}
          </div>
        )}

        {operation.participants && operation.participants.length > 0 && (
          <div>
            <div className="text-[10px] font-semibold text-[#6b7d93] uppercase tracking-wider mb-1.5">
              Participants
            </div>
            <div className="space-y-1">
              {operation.participants.map((p, i) => (
                <div
                  key={i}
                  className="flex items-center gap-2 px-2.5 py-1.5 rounded bg-[#1a2332] border border-[#2a3a4e]"
                >
                  <Users className="w-3 h-3 text-[#4ea8de]" />
                  <span className="text-[11px] text-[#c8d6e5]">
                    {p.organization_id} ({p.role})
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="text-[10px] text-[#6b7d93] space-y-0.5">
          {operation.created_at && (
            <div>
              Created:{" "}
              {formatDistanceToNow(new Date(operation.created_at), {
                addSuffix: true,
              })}
            </div>
          )}
        </div>
      </div>
    </>
  );
}

// -------------------------------------------------------------------
// Offer detail panel
// -------------------------------------------------------------------

function OfferDetail({ data, onClose }) {
  return (
    <>
      <PanelHeader
        icon={Package}
        title={`${data.resource_type} — ${data.quantity} ${data.unit}`}
        subtitle="Resource Offer"
        onClose={onClose}
        color="#0d9488"
      />
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        <StatusBadge status={data.status} color="#0d9488" />

        {data.location_name && (
          <div className="flex items-center gap-2 text-[12px] text-[#c8d6e5]">
            <MapPin className="w-3.5 h-3.5 text-[#6b7d93]" />
            {data.location_name}
          </div>
        )}

        {data.notes && (
          <div className="text-[12px] text-[#a0aec0] leading-relaxed">
            {data.notes}
          </div>
        )}

        <div className="text-[10px] text-[#6b7d93]">
          Organization: {data.organization_id}
        </div>
      </div>
    </>
  );
}

// -------------------------------------------------------------------
// Field report detail panel
// -------------------------------------------------------------------

function ReportDetail({ data, onClose }) {
  const verified = data.verified || data.source === "field_intelligence_text";

  return (
    <>
      <PanelHeader
        icon={FileText}
        title={`${data.people_count || 0} people reported`}
        subtitle="Field Report"
        onClose={onClose}
        color={verified ? "#16a34a" : "#4f46e5"}
      />
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        <StatusBadge
          status={verified ? "verified" : "unverified"}
          color={verified ? "#16a34a" : "#d97706"}
        />

        {data.needs && data.needs.length > 0 && (
          <div>
            <div className="text-[10px] font-semibold text-[#6b7d93] uppercase tracking-wider mb-1.5">
              Needs
            </div>
            <div className="flex flex-wrap gap-1">
              {data.needs.map((need) => (
                <span
                  key={need}
                  className="px-2 py-0.5 rounded text-[10px] font-medium bg-amber-500/10 text-amber-400 border border-amber-500/20"
                >
                  {need.replace(/_/g, " ")}
                </span>
              ))}
            </div>
          </div>
        )}

        {data.note && (
          <div className="text-[12px] text-[#a0aec0] leading-relaxed">
            {data.note}
          </div>
        )}

        {data.raw_text && (
          <div className="text-[12px] text-[#a0aec0] leading-relaxed">
            {data.raw_text}
          </div>
        )}

        <div className="text-[10px] text-[#6b7d93] space-y-0.5">
          {data.timestamp && (
            <div>
              Submitted:{" "}
              {formatDistanceToNow(new Date(data.timestamp), {
                addSuffix: true,
              })}
            </div>
          )}
          {data.location_description && (
            <div>Location: {data.location_description}</div>
          )}
        </div>
      </div>
    </>
  );
}

// -------------------------------------------------------------------
// Facility detail panel
// -------------------------------------------------------------------

function FacilityDetail({ data, override, onClose }) {
  const [showOverride, setShowOverride] = useState(false);
  const [overrideStatus, setOverrideStatus] = useState("submerged");
  const [overrideReason, setOverrideReason] = useState("");

  const handleApplyOverride = async () => {
    try {
      await fetch("/api/override", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target_type: "facility",
          target_id: data.name,
          new_status: overrideStatus,
          reason: overrideReason,
        }),
      });
      onClose();
    } catch (err) {
      console.error("Override failed:", err);
    }
  };

  return (
    <>
      <PanelHeader
        icon={Stethoscope}
        title={data.name}
        subtitle="Medical Facility"
        onClose={onClose}
        color="#0891b2"
      />
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        <div className="text-[12px] text-[#a0aec0]">{data.facility_type}</div>

        {override && (
          <div className="px-3 py-2 rounded bg-amber-500/10 border border-amber-500/20">
            <div className="text-[11px] font-semibold text-amber-400">
              Override: {override.override_status}
            </div>
            <div className="text-[10px] text-amber-400/70 mt-0.5">
              {override.reason}
            </div>
          </div>
        )}

        {!showOverride ? (
          <button
            onClick={() => setShowOverride(true)}
            className="w-full px-3 py-2 rounded text-[12px] font-medium bg-amber-500/10 text-amber-400 border border-amber-500/20 hover:bg-amber-500/20 transition-colors"
          >
            Override Status
          </button>
        ) : (
          <div className="space-y-3 p-3 rounded bg-[#1a2332] border border-[#2a3a4e]">
            <div className="text-[11px] font-semibold text-[#c8d6e5]">
              Apply Override
            </div>
            <div className="grid grid-cols-3 gap-1.5">
              {["submerged", "damaged", "operational"].map((s) => (
                <button
                  key={s}
                  onClick={() => setOverrideStatus(s)}
                  className={cn(
                    "px-2 py-1.5 rounded text-[11px] font-medium border transition-colors",
                    overrideStatus === s
                      ? "bg-[#2a3a4e] text-[#c8d6e5] border-[#3a5a7e]"
                      : "text-[#6b7d93] border-[#2a3a4e] hover:border-[#3a5a7e]"
                  )}
                >
                  {s}
                </button>
              ))}
            </div>
            <textarea
              value={overrideReason}
              onChange={(e) => setOverrideReason(e.target.value)}
              placeholder="Reason for override..."
              className="w-full h-16 px-2.5 py-1.5 rounded border border-[#2a3a4e] bg-[#0f1419] text-[12px] text-[#c8d6e5] placeholder:text-[#6b7d93] outline-none resize-none"
            />
            <div className="flex gap-2">
              <button
                onClick={() => setShowOverride(false)}
                className="flex-1 px-2.5 py-1.5 rounded text-[11px] font-medium text-[#6b7d93] border border-[#2a3a4e] hover:bg-[#1a2332] transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleApplyOverride}
                disabled={!overrideReason.trim()}
                className={cn(
                  "flex-1 px-2.5 py-1.5 rounded text-[11px] font-medium transition-colors",
                  overrideReason.trim()
                    ? "bg-amber-500/20 text-amber-400 border border-amber-500/30 hover:bg-amber-500/30"
                    : "bg-[#1a2332] text-[#6b7d93] border border-[#2a3a4e] cursor-not-allowed"
                )}
              >
                Apply
              </button>
            </div>
          </div>
        )}
      </div>
    </>
  );
}

// -------------------------------------------------------------------
// Create Need form
// -------------------------------------------------------------------

function CreateNeedForm({ onClose }) {
  const { fetchNeeds } = useWorkspace();
  const [form, setForm] = useState({
    need_type: "food",
    title: "",
    description: "",
    location_name: "",
    lat: "",
    lon: "",
    urgency: "medium",
    requested_resources: [],
  });
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const resp = await fetch("/api/needs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...form,
          lat: form.lat ? parseFloat(form.lat) : null,
          lon: form.lon ? parseFloat(form.lon) : null,
        }),
      });
      if (resp.ok) {
        fetchNeeds();
        onClose();
      }
    } catch (err) {
      console.error("Failed to create need:", err);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <PanelHeader
        icon={AlertTriangle}
        title="Create Need"
        subtitle="Report a resource need"
        onClose={onClose}
        color="#dc2626"
      />
      <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-4 space-y-3">
        <Field label="Type">
          <select
            value={form.need_type}
            onChange={(e) => setForm({ ...form, need_type: e.target.value })}
            className="w-full px-2.5 py-1.5 rounded border border-[#2a3a4e] bg-[#0f1419] text-[12px] text-[#c8d6e5] outline-none"
          >
            {["food", "water", "medical", "shelter", "transport", "rescue", "other"].map(
              (t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              )
            )}
          </select>
        </Field>

        <Field label="Title">
          <input
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
            placeholder="e.g., 2 rescue boats required near Demow"
            className="w-full px-2.5 py-1.5 rounded border border-[#2a3a4e] bg-[#0f1419] text-[12px] text-[#c8d6e5] placeholder:text-[#6b7d93] outline-none"
            required
          />
        </Field>

        <Field label="Description">
          <textarea
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            placeholder="Details about the need..."
            className="w-full h-16 px-2.5 py-1.5 rounded border border-[#2a3a4e] bg-[#0f1419] text-[12px] text-[#c8d6e5] placeholder:text-[#6b7d93] outline-none resize-none"
          />
        </Field>

        <Field label="Urgency">
          <div className="grid grid-cols-4 gap-1.5">
            {["critical", "high", "medium", "low"].map((u) => (
              <button
                key={u}
                type="button"
                onClick={() => setForm({ ...form, urgency: u })}
                className={cn(
                  "px-2 py-1.5 rounded text-[11px] font-medium border transition-colors",
                  form.urgency === u
                    ? "bg-[#2a3a4e] text-[#c8d6e5] border-[#3a5a7e]"
                    : "text-[#6b7d93] border-[#2a3a4e] hover:border-[#3a5a7e]"
                )}
              >
                {u}
              </button>
            ))}
          </div>
        </Field>

        <Field label="Location Name">
          <input
            value={form.location_name}
            onChange={(e) => setForm({ ...form, location_name: e.target.value })}
            placeholder="e.g., Demow, Jorhat"
            className="w-full px-2.5 py-1.5 rounded border border-[#2a3a4e] bg-[#0f1419] text-[12px] text-[#c8d6e5] placeholder:text-[#6b7d93] outline-none"
          />
        </Field>

        <div className="grid grid-cols-2 gap-2">
          <Field label="Latitude">
            <input
              value={form.lat}
              onChange={(e) => setForm({ ...form, lat: e.target.value })}
              placeholder="26.74"
              className="w-full px-2.5 py-1.5 rounded border border-[#2a3a4e] bg-[#0f1419] text-[12px] text-[#c8d6e5] placeholder:text-[#6b7d93] outline-none"
            />
          </Field>
          <Field label="Longitude">
            <input
              value={form.lon}
              onChange={(e) => setForm({ ...form, lon: e.target.value })}
              placeholder="94.21"
              className="w-full px-2.5 py-1.5 rounded border border-[#2a3a4e] bg-[#0f1419] text-[12px] text-[#c8d6e5] placeholder:text-[#6b7d93] outline-none"
            />
          </Field>
        </div>

        <button
          type="submit"
          disabled={submitting || !form.title.trim()}
          className={cn(
            "w-full px-3 py-2 rounded text-[12px] font-semibold transition-colors",
            form.title.trim() && !submitting
              ? "bg-red-500/20 text-red-400 border border-red-500/30 hover:bg-red-500/30"
              : "bg-[#1a2332] text-[#6b7d93] border border-[#2a3a4e] cursor-not-allowed"
          )}
        >
          {submitting ? "Creating..." : "Create Need"}
        </button>
      </form>
    </>
  );
}

// -------------------------------------------------------------------
// Create Report form
// -------------------------------------------------------------------

function CreateReportForm({ defaultData, onClose }) {
  const { fetchFieldReports } = useWorkspace();
  const [form, setForm] = useState({
    raw_text: "",
    lat: defaultData?.lat || "",
    lon: defaultData?.lon || "",
  });
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const resp = await fetch("/api/field-intelligence", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ raw_text: form.raw_text }),
      });
      if (resp.ok) {
        fetchFieldReports();
        onClose();
      }
    } catch (err) {
      console.error("Failed to submit report:", err);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <PanelHeader
        icon={FileText}
        title="Report Issue"
        subtitle="Submit a field/community report"
        onClose={onClose}
        color="#4f46e5"
      />
      <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-4 space-y-3">
        <Field label="Observation">
          <textarea
            value={form.raw_text}
            onChange={(e) => setForm({ ...form, raw_text: e.target.value })}
            placeholder="Describe what you observed... (road blocked, bridge damaged, flood reached location, food shortage, etc.)"
            className="w-full h-24 px-2.5 py-1.5 rounded border border-[#2a3a4e] bg-[#0f1419] text-[12px] text-[#c8d6e5] placeholder:text-[#6b7d93] outline-none resize-none"
            required
          />
        </Field>

        {form.lat && form.lon && (
          <div className="text-[10px] text-[#6b7d93]">
            📍 Location: {parseFloat(form.lat).toFixed(4)}, {parseFloat(form.lon).toFixed(4)}
          </div>
        )}

        <button
          type="submit"
          disabled={submitting || !form.raw_text.trim()}
          className={cn(
            "w-full px-3 py-2 rounded text-[12px] font-semibold transition-colors",
            form.raw_text.trim() && !submitting
              ? "bg-indigo-500/20 text-indigo-400 border border-indigo-500/30 hover:bg-indigo-500/30"
              : "bg-[#1a2332] text-[#6b7d93] border border-[#2a3a4e] cursor-not-allowed"
          )}
        >
          {submitting ? "Submitting..." : "Submit Report"}
        </button>
      </form>
    </>
  );
}

// -------------------------------------------------------------------
// Create Offer form
// -------------------------------------------------------------------

function CreateOfferForm({ onClose }) {
  const { fetchOffers } = useWorkspace();
  const [form, setForm] = useState({
    resource_type: "boat",
    quantity: 1,
    unit: "units",
    location_name: "",
    lat: "",
    lon: "",
    notes: "",
    organization_id: "anonymous",
  });
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const resp = await fetch("/api/offers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...form,
          quantity: parseInt(form.quantity) || 0,
          lat: form.lat ? parseFloat(form.lat) : null,
          lon: form.lon ? parseFloat(form.lon) : null,
        }),
      });
      if (resp.ok) {
        fetchOffers();
        onClose();
      }
    } catch (err) {
      console.error("Failed to create offer:", err);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <PanelHeader
        icon={Package}
        title="Offer Resource"
        subtitle="Publish available resources"
        onClose={onClose}
        color="#0d9488"
      />
      <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-4 space-y-3">
        <Field label="Resource Type">
          <select
            value={form.resource_type}
            onChange={(e) => setForm({ ...form, resource_type: e.target.value })}
            className="w-full px-2.5 py-1.5 rounded border border-[#2a3a4e] bg-[#0f1419] text-[12px] text-[#c8d6e5] outline-none"
          >
            {["boat", "vehicle", "medical_team", "food", "water", "medicine", "shelter", "personnel", "other"].map(
              (t) => (
                <option key={t} value={t}>
                  {t.replace(/_/g, " ")}
                </option>
              )
            )}
          </select>
        </Field>

        <div className="grid grid-cols-2 gap-2">
          <Field label="Quantity">
            <input
              type="number"
              value={form.quantity}
              onChange={(e) => setForm({ ...form, quantity: e.target.value })}
              className="w-full px-2.5 py-1.5 rounded border border-[#2a3a4e] bg-[#0f1419] text-[12px] text-[#c8d6e5] outline-none"
              min="1"
              required
            />
          </Field>
          <Field label="Unit">
            <select
              value={form.unit}
              onChange={(e) => setForm({ ...form, unit: e.target.value })}
              className="w-full px-2.5 py-1.5 rounded border border-[#2a3a4e] bg-[#0f1419] text-[12px] text-[#c8d6e5] outline-none"
            >
              {["units", "people", "kg", "liters", "kits"].map((u) => (
                <option key={u} value={u}>
                  {u}
                </option>
              ))}
            </select>
          </Field>
        </div>

        <Field label="Location">
          <input
            value={form.location_name}
            onChange={(e) => setForm({ ...form, location_name: e.target.value })}
            placeholder="e.g., Jorhat Relief Camp"
            className="w-full px-2.5 py-1.5 rounded border border-[#2a3a4e] bg-[#0f1419] text-[12px] text-[#c8d6e5] placeholder:text-[#6b7d93] outline-none"
          />
        </Field>

        <div className="grid grid-cols-2 gap-2">
          <Field label="Latitude">
            <input
              value={form.lat}
              onChange={(e) => setForm({ ...form, lat: e.target.value })}
              placeholder="26.74"
              className="w-full px-2.5 py-1.5 rounded border border-[#2a3a4e] bg-[#0f1419] text-[12px] text-[#c8d6e5] placeholder:text-[#6b7d93] outline-none"
            />
          </Field>
          <Field label="Longitude">
            <input
              value={form.lon}
              onChange={(e) => setForm({ ...form, lon: e.target.value })}
              placeholder="94.21"
              className="w-full px-2.5 py-1.5 rounded border border-[#2a3a4e] bg-[#0f1419] text-[12px] text-[#c8d6e5] placeholder:text-[#6b7d93] outline-none"
            />
          </Field>
        </div>

        <Field label="Notes">
          <textarea
            value={form.notes}
            onChange={(e) => setForm({ ...form, notes: e.target.value })}
            placeholder="Additional details..."
            className="w-full h-16 px-2.5 py-1.5 rounded border border-[#2a3a4e] bg-[#0f1419] text-[12px] text-[#c8d6e5] placeholder:text-[#6b7d93] outline-none resize-none"
          />
        </Field>

        <button
          type="submit"
          disabled={submitting}
          className={cn(
            "w-full px-3 py-2 rounded text-[12px] font-semibold transition-colors",
            !submitting
              ? "bg-teal-500/20 text-teal-400 border border-teal-500/30 hover:bg-teal-500/30"
              : "bg-[#1a2332] text-[#6b7d93] border border-[#2a3a4e] cursor-not-allowed"
          )}
        >
          {submitting ? "Publishing..." : "Publish Offer"}
        </button>
      </form>
    </>
  );
}

// -------------------------------------------------------------------
// Settlement detail panel
// -------------------------------------------------------------------

function SettlementDetail({ data, onClose }) {
  return (
    <>
      <PanelHeader
        icon={MapPin}
        title={data.name}
        subtitle="Settlement"
        onClose={onClose}
        color="#78716c"
      />
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        <div className="text-[12px] text-[#a0aec0]">
          District: {data.district_id}
        </div>
        <div className="text-[11px] text-[#6b7d93] font-mono">
          {data.lat?.toFixed(4)}°N, {data.lon?.toFixed(4)}°E
        </div>
      </div>
    </>
  );
}

// -------------------------------------------------------------------
// AI Analysis panel (placeholder)
// -------------------------------------------------------------------

function AIAnalysisPanel({ onClose }) {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleQuery = async () => {
    if (!query.trim()) return;
    setLoading(true);
    try {
      const resp = await fetch("/api/planner", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
      });
      if (resp.ok) {
        const data = await resp.json();
        setResult(data);
      }
    } catch (err) {
      console.error("Planner query failed:", err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <PanelHeader
        icon={Shield}
        title="AI Coordinator"
        subtitle="Operational analysis"
        onClose={onClose}
        color="#7c3aed"
      />
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Query input */}
        <div className="flex gap-2">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleQuery()}
            placeholder="Ask about the situation..."
            className="flex-1 px-2.5 py-1.5 rounded border border-[#2a3a4e] bg-[#0f1419] text-[12px] text-[#c8d6e5] placeholder:text-[#6b7d93] outline-none"
          />
          <button
            onClick={handleQuery}
            disabled={loading || !query.trim()}
            className={cn(
              "px-3 py-1.5 rounded text-[11px] font-medium transition-colors",
              query.trim() && !loading
                ? "bg-purple-500/20 text-purple-400 border border-purple-500/30 hover:bg-purple-500/30"
                : "bg-[#1a2332] text-[#6b7d93] border border-[#2a3a4e] cursor-not-allowed"
            )}
          >
            {loading ? "..." : "Ask"}
          </button>
        </div>

        {/* Quick prompts */}
        <div className="flex flex-wrap gap-1.5">
          {[
            "What needs attention right now?",
            "Which areas have flood exposure?",
            "Where are boats needed?",
            "Which needs can be matched with offers?",
          ].map((prompt) => (
            <button
              key={prompt}
              onClick={() => {
                setQuery(prompt);
                setTimeout(() => handleQuery(), 100);
              }}
              className="px-2 py-0.5 rounded text-[10px] text-[#a78bfa] bg-purple-500/5 border border-purple-500/15 hover:bg-purple-500/10 transition-colors"
            >
              {prompt}
            </button>
          ))}
        </div>

        {/* Result */}
        {result && (
          <div className="space-y-3">
            {result.recommendation && (
              <div className="p-3 rounded bg-[#1a2332] border border-[#2a3a4e]">
                <div className="text-[10px] font-semibold text-[#a78bfa] uppercase tracking-wider mb-1">
                  Recommendation
                </div>
                <div className="text-[12px] text-[#c8d6e5] leading-relaxed whitespace-pre-wrap">
                  {result.recommendation}
                </div>
              </div>
            )}
            {result.why && (
              <div className="p-3 rounded bg-[#1a2332] border border-[#2a3a4e]">
                <div className="text-[10px] font-semibold text-[#6b7d93] uppercase tracking-wider mb-1">
                  Why
                </div>
                <div className="text-[11px] text-[#a0aec0] leading-relaxed whitespace-pre-wrap">
                  {result.why}
                </div>
              </div>
            )}
            {result.constraints && result.constraints.length > 0 && (
              <div className="p-3 rounded bg-[#1a2332] border border-[#2a3a4e]">
                <div className="text-[10px] font-semibold text-[#6b7d93] uppercase tracking-wider mb-1">
                  Constraints
                </div>
                <div className="space-y-0.5">
                  {result.constraints.map((c, i) => (
                    <div key={i} className="text-[11px] text-[#a0aec0]">
                      • {c}
                    </div>
                  ))}
                </div>
              </div>
            )}
            {result.uncertainty && result.uncertainty.length > 0 && (
              <div className="p-3 rounded bg-amber-500/5 border border-amber-500/15">
                <div className="text-[10px] font-semibold text-amber-400 uppercase tracking-wider mb-1">
                  Uncertainty
                </div>
                <div className="space-y-0.5">
                  {result.uncertainty.map((u, i) => (
                    <div key={i} className="text-[11px] text-amber-400/80">
                      ⚠ {u}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </>
  );
}

// -------------------------------------------------------------------
// Road detail panel
// -------------------------------------------------------------------

function RoadDetail({ data, onClose }) {
  const [showOverride, setShowOverride] = useState(false);
  const [overrideStatus, setOverrideStatus] = useState("blocked");
  const [overrideReason, setOverrideReason] = useState("");

  const handleApplyOverride = async () => {
    try {
      await fetch("/api/override", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target_type: "road",
          target_id: data.name,
          new_status: overrideStatus,
          reason: overrideReason,
        }),
      });
      onClose();
    } catch (err) {
      console.error("Override failed:", err);
    }
  };

  const statusColor = {
    open: "#16a34a",
    uncertain: "#d97706",
    blocked: "#dc2626",
    submerged: "#dc2626",
    damaged: "#dc2626",
    passable: "#16a34a",
    restricted: "#d97706",
  };
  const opStatus = data.operational_status || (data.flood_affected ? "uncertain" : "open");

  return (
    <>
      <PanelHeader
        icon={Route}
        title={data.name || "Unnamed road"}
        subtitle={`${data.highway_type}${data.is_bridge ? " · Bridge" : ""}`}
        onClose={onClose}
        color={statusColor[opStatus] || "#6b7d93"}
      />
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        <div className="flex items-center gap-2 flex-wrap">
          <StatusBadge status={opStatus} color={statusColor[opStatus] || "#6b7d93"} />
          {data.is_bridge && <StatusBadge status="bridge" color="#0891b2" />}
        </div>

        {/* Source + Override status */}
        <div className="p-3 rounded bg-[#1a2332] border border-[#2a3a4e] space-y-2">
          <div className="text-[10px] font-semibold text-[#6b7d93] uppercase tracking-wider">
            Status Detail
          </div>
          <div className="text-[11px] text-[#a0aec0]">
            Source: {data.flood_affected ? "Flood-affected" : "No flood impact detected"}
          </div>
          {data.override ? (
            <div className="mt-1 px-2.5 py-2 rounded bg-amber-500/10 border border-amber-500/20">
              <div className="text-[11px] font-semibold text-amber-400">
                Override: {data.override.status}
              </div>
              <div className="text-[10px] text-amber-400/70 mt-0.5">{data.override.reason}</div>
              <div className="text-[10px] text-[#6b7d93] mt-0.5">
                By {data.override.actor} · {data.override.timestamp}
              </div>
            </div>
          ) : (
            <div className="text-[11px] text-[#6b7d93]">No active override</div>
          )}
        </div>

        {/* Override actions */}
        {!showOverride ? (
          <button
            onClick={() => setShowOverride(true)}
            className="w-full px-3 py-2 rounded text-[12px] font-medium bg-amber-500/10 text-amber-400 border border-amber-500/20 hover:bg-amber-500/20 transition-colors"
          >
            Override Status
          </button>
        ) : (
          <div className="space-y-3 p-3 rounded bg-[#1a2332] border border-[#2a3a4e]">
            <div className="text-[11px] font-semibold text-[#c8d6e5]">Apply Override</div>
            <div className="grid grid-cols-3 gap-1.5">
              {["blocked", "passable", "restricted"].map((s) => (
                <button
                  key={s}
                  onClick={() => setOverrideStatus(s)}
                  className={cn(
                    "px-2 py-1.5 rounded text-[11px] font-medium border transition-colors",
                    overrideStatus === s
                      ? "bg-[#2a3a4e] text-[#c8d6e5] border-[#3a5a7e]"
                      : "text-[#6b7d93] border-[#2a3a4e] hover:border-[#3a5a7e]"
                  )}
                >
                  {s}
                </button>
              ))}
            </div>
            <textarea
              value={overrideReason}
              onChange={(e) => setOverrideReason(e.target.value)}
              placeholder="Reason for override..."
              className="w-full h-16 px-2.5 py-1.5 rounded border border-[#2a3a4e] bg-[#0f1419] text-[12px] text-[#c8d6e5] placeholder:text-[#6b7d93] outline-none resize-none"
            />
            <div className="flex gap-2">
              <button
                onClick={() => setShowOverride(false)}
                className="flex-1 px-2.5 py-1.5 rounded text-[11px] font-medium text-[#6b7d93] border border-[#2a3a4e] hover:bg-[#1a2332] transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleApplyOverride}
                disabled={!overrideReason.trim()}
                className={cn(
                  "flex-1 px-2.5 py-1.5 rounded text-[11px] font-medium transition-colors",
                  overrideReason.trim()
                    ? "bg-amber-500/20 text-amber-400 border border-amber-500/30 hover:bg-amber-500/30"
                    : "bg-[#1a2332] text-[#6b7d93] border border-[#2a3a4e] cursor-not-allowed"
                )}
              >
                Apply
              </button>
            </div>
          </div>
        )}
      </div>
    </>
  );
}

// -------------------------------------------------------------------
// Field helper
// -------------------------------------------------------------------

function Field({ label, children }) {
  return (
    <div>
      <label className="block text-[10px] font-semibold text-[#6b7d93] uppercase tracking-wider mb-1">
        {label}
      </label>
      {children}
    </div>
  );
}

// -------------------------------------------------------------------
// Main ContextPanel
// -------------------------------------------------------------------

export default function ContextPanel() {
  const { state, closePanel } = useWorkspace();

  if (!state.panelOpen) return null;

  const panelWidth = 384;

  return (
    <div
      className="bg-[#0f1419] border-l border-[#2a3a4e] flex flex-col shrink-0 overflow-hidden fade-in"
      style={{ width: panelWidth }}
    >
      {state.panelType === "need" && state.panelData && (
        <NeedDetail data={state.panelData} onClose={closePanel} />
      )}
      {state.panelType === "operation" && state.panelData && (
        <OperationDetail data={state.panelData} onClose={closePanel} />
      )}
      {state.panelType === "offer" && state.panelData && (
        <OfferDetail data={state.panelData} onClose={closePanel} />
      )}
      {state.panelType === "report" && state.panelData && (
        <ReportDetail data={state.panelData} onClose={closePanel} />
      )}
      {state.panelType === "facility" && state.panelData && (
        <FacilityDetail
          data={state.panelData}
          override={state.overrides[state.panelData.name]}
          onClose={closePanel}
        />
      )}
      {state.panelType === "settlement" && state.panelData && (
        <SettlementDetail data={state.panelData} onClose={closePanel} />
      )}
      {state.panelType === "road" && state.panelData && (
        <RoadDetail data={state.panelData} onClose={closePanel} />
      )}
      {state.panelType === "createNeed" && (
        <CreateNeedForm onClose={closePanel} />
      )}
      {state.panelType === "createReport" && (
        <CreateReportForm defaultData={state.panelData} onClose={closePanel} />
      )}
      {state.panelType === "createOffer" && (
        <CreateOfferForm onClose={closePanel} />
      )}
      {state.panelType === "aiAnalysis" && (
        <AIAnalysisPanel onClose={closePanel} />
      )}
    </div>
  );
}
