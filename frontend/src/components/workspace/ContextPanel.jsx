import { useState, useEffect, useCallback, useRef } from "react";
import {
  X, ArrowLeft, AlertTriangle, Package, Zap, FileText, Shield,
  Stethoscope, MapPin, Clock, Users, ChevronDown, Route,
  CheckCircle, Search, Handshake, Info, AlertCircle, HelpCircle, Globe,
  Building2, Brain, Inbox, EyeOff, Crosshair,
} from "lucide-react";
import { useWorkspace } from "../../lib/workspaceContext";
import { cn } from "../../lib/utils";
import { MAP_STYLES } from "../../lib/mapStyles";
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
// Evidence / Uncertainty / Data Gap section
// -------------------------------------------------------------------

function EvidenceSection({ evidence, uncertainty, dataGaps, confidence }) {
  if (!evidence && !uncertainty && !dataGaps) return null;

  const evidenceItems = evidence?.evidence_items || evidence || [];
  const uncertaintyItems = uncertainty || evidence?.uncertainty || [];
  const gapItems = dataGaps || evidence?.data_gaps || [];
  const conf = confidence || evidence?.confidence;

  return (
    <div className="space-y-3 pt-4 border-t border-[#2a3a4e]">
      <div className="flex items-center justify-between">
        <div className="text-[10px] font-semibold text-[#6b7d93] uppercase tracking-wider">
          Evidence & Confidence
        </div>
        {conf && (
          <span className={cn(
            "text-[9px] font-medium px-1.5 py-0.5 rounded",
            conf === 'high' ? 'text-green-400 bg-green-500/10'
            : conf === 'medium' ? 'text-amber-400 bg-amber-500/10'
            : 'text-[#6b7d93] bg-[#1a2332]'
          )}>
            {conf} confidence
          </span>
        )}
      </div>

      {/* Evidence items */}
      {evidenceItems.length > 0 && (
        <div className="space-y-1.5">
          {evidenceItems.map((item, i) => (
            <div key={i} className="flex items-start gap-2 px-2.5 py-1.5 rounded bg-[#1a2332] border border-[#2a3a4e]">
              <Info className="w-3 h-3 text-blue-400 mt-0.5 shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="text-[11px] text-[#c8d6e5]">
                  {item.detail || item.type}
                </div>
                <div className="flex items-center gap-2 text-[9px] text-[#6b7d93] mt-0.5">
                  <span>{item.source || 'unknown'}</span>
                  {item.timestamp && (
                    <span>· {formatDistanceToNow(new Date(item.timestamp), { addSuffix: true })}</span>
                  )}
                  {item.verified !== undefined && (
                    <span className={item.verified ? 'text-green-400' : 'text-amber-400'}>
                      {item.verified ? 'verified' : 'unverified'}
                    </span>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Uncertainty */}
      {uncertaintyItems.length > 0 && (
        <div className="space-y-1">
          <div className="text-[9px] font-semibold text-amber-400/80 uppercase tracking-wider">
            Uncertainty
          </div>
          {uncertaintyItems.map((u, i) => (
            <div key={i} className="flex items-start gap-2 text-[10px] text-amber-400/80">
              <HelpCircle className="w-3 h-3 mt-0.5 shrink-0" />
              <span>{typeof u === 'string' ? u : u.detail || u.item || JSON.stringify(u)}</span>
            </div>
          ))}
        </div>
      )}

      {/* Data gaps */}
      {gapItems.length > 0 && (
        <div className="space-y-1">
          <div className="text-[9px] font-semibold text-[#6b7d93] uppercase tracking-wider">
            Data Gaps
          </div>
          {gapItems.map((g, i) => (
            <div key={i} className="flex items-start gap-2 text-[10px] text-[#6b7d93]">
              <AlertCircle className="w-3 h-3 mt-0.5 shrink-0" />
              <span>{typeof g === 'string' ? g : g.detail || g.item || JSON.stringify(g)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// -------------------------------------------------------------------
// Need detail panel
// -------------------------------------------------------------------

function NeedDetail({ data, onClose, onOpenMatch }) {
  const { state, refreshAll, fetchNeeds, fetchActivity } = useWorkspace();
  const [need, setNeed] = useState(data);
  const [updating, setUpdating] = useState(false);
  const [matches, setMatches] = useState(null);
  const [loadingMatches, setLoadingMatches] = useState(false);
  const [needEvidence, setNeedEvidence] = useState(null);
  const [error, setError] = useState(null);
  const [proposals, setProposals] = useState([]);
  const [loadingProposals, setLoadingProposals] = useState(false);
  const [showPropose, setShowPropose] = useState(false);
  const [selectedOrgId, setSelectedOrgId] = useState("");
  const [proposing, setProposing] = useState(false);
  const [proposalBusy, setProposalBusy] = useState(null);

  const loadNeedProposals = useCallback(async () => {
    setLoadingProposals(true);
    try {
      const resp = await fetch(`/api/network/coordination/proposals?need_id=${encodeURIComponent(need.id)}`);
      if (resp.ok) {
        const res = await resp.json();
        setProposals(res.proposals || []);
      }
    } catch (err) {
      console.error("Failed to load need proposals:", err);
    } finally {
      setLoadingProposals(false);
    }
  }, [need.id]);

  useEffect(() => {
    loadNeedProposals();
  }, [loadNeedProposals]);

  const handleCreateProposal = async (e) => {
    e.preventDefault();
    if (!selectedOrgId) return;
    setProposing(true);
    setError(null);
    try {
      const targetOrg = state.organizations.find(o => o.id === selectedOrgId);
      const resp = await fetch("/api/network/coordination/propose", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          need: need,
          organization_id: selectedOrgId,
          organization_name: targetOrg?.name || selectedOrgId,
        }),
      });
      if (resp.ok) {
        setShowPropose(false);
        setSelectedOrgId("");
        await loadNeedProposals();
        fetchActivity();
      } else {
        const err = await resp.json().catch(() => ({}));
        setError(err.error || `Failed to create proposal (${resp.status})`);
      }
    } catch (err) {
      console.error("Failed to propose coordination:", err);
      setError("Network error: could not reach server");
    } finally {
      setProposing(false);
    }
  };

  const handleSendProposal = async (proposalId) => {
    setProposalBusy(proposalId);
    try {
      const resp = await fetch(`/api/network/coordination/proposals/${proposalId}/send-to-org`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      if (resp.ok) {
        await loadNeedProposals();
        fetchActivity();
      }
    } catch (err) {
      console.error("Failed to send proposal to org:", err);
    } finally {
      setProposalBusy(null);
    }
  };

  const handleDeclineProposal = async (proposalId) => {
    setProposalBusy(proposalId);
    try {
      const resp = await fetch(`/api/network/coordination/proposals/${proposalId}/decline`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      if (resp.ok) {
        await loadNeedProposals();
        fetchActivity();
      }
    } catch (err) {
      console.error("Failed to decline proposal:", err);
    } finally {
      setProposalBusy(null);
    }
  };

  useEffect(() => {
    fetch(`/api/evidence/need/${need.id}`)
      .then(r => r.ok ? r.json() : null)
      .then(data => setNeedEvidence(data))
      .catch(() => {});
  }, [need.id]);

  const handleStatusChange = async (newStatus) => {
    setUpdating(true);
    setError(null);
    try {
      const resp = await fetch(`/api/needs/${need.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: newStatus, actor: "coordinator" }),
      });
      if (resp.ok) {
        const result = await resp.json();
        setNeed(result.need);
        // Refresh global workspace state so lists/activity reflect the change
        refreshAll();
      } else {
        const err = await resp.json().catch(() => ({}));
        setError(err.error || `Failed to update need (${resp.status})`);
      }
    } catch (err) {
      console.error("Failed to update need:", err);
      setError("Network error: could not reach server");
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
        // Refresh global state so operations list updates
        refreshAll();
        // Open the newly created collaboration operation
        if (result.operation) {
          onOpenMatch("operation", result.operation.id, result.operation);
        } else {
          // Fallback: refresh need status
          setNeed({ ...need, status: "RESPONDING" });
        }
        // Refresh matches to show updated state
        handleFindResources();
      }
    } catch (err) {
      console.error("Failed to confirm match:", err);
    }
  };

  const history = state.activity
    .filter((e) => e.entity_id === need.id)
    .sort((a, b) => new Date(b.created_at) - new Date(a.created_at));

  return (
    <>
      <PanelHeader
        icon={AlertTriangle}
        title={need.title}
        subtitle={`${need.id} · ${need.need_type} · ${need.status}`}
        onClose={onClose}
        color={urgencyColor[need.urgency] || "#c8d6e5"}
      />
      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        {/* SECTION 1: QUICK VIEW */}
        <div className="space-y-3">
          <div className="flex items-center gap-2 flex-wrap">
            <StatusBadge status={need.status} color="#4ea8de" />
            <StatusBadge
              status={need.urgency}
              color={urgencyColor[need.urgency] || "#78716c"}
            />
            {need.confidence > 0 && need.confidence < 1 && (
              <span className="text-[9px] font-mono text-[#6b7d93]">
                {(need.confidence * 100).toFixed(0)}% conf.
              </span>
            )}
          </div>

          {need.location_name && (
            <div className="flex items-center gap-2 text-[12px] text-[#c8d6e5] font-medium">
              <MapPin className="w-3.5 h-3.5 text-[#6b7d93]" />
              {need.location_name}
            </div>
          )}

          {need.description && (
            <div className="text-[13px] text-[#a0aec0] leading-relaxed font-medium">
              {need.description}
            </div>
          )}
        </div>

        {/* SECTION 2: REQUIREMENT & RESPONSE */}
        <div className="space-y-4 pt-4 border-t border-[#2a3a4e]">
          {need.requested_resources && need.requested_resources.length > 0 && (
            <div className="space-y-2">
              <div className="text-[10px] font-semibold text-[#6b7d93] uppercase tracking-wider">
                Requirement
              </div>
              <div className="grid grid-cols-1 gap-1.5">
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

          {/* Resource Gap Display */}
          {(() => {
            const linkedOps = state.operations.filter(op => op.need_id === need.id);
            const totalCommitted = linkedOps.reduce((sum, op) => sum + (op.metadata?.quantity_committed || 0), 0);
            const requested = need.requested_resources?.[0]?.quantity || 0;
            const gap = Math.max(0, requested - totalCommitted);
            if (requested === 0) return null;
            return (
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-semibold text-[#6b7d93] uppercase tracking-wider">
                    Response
                  </span>
                  <span className="text-[10px] font-mono text-[#c8d6e5]">
                    {totalCommitted}/{requested} {need.requested_resources?.[0]?.unit || 'units'}
                  </span>
                </div>
                <div className="w-full h-1.5 bg-[#1a2332] rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{
                      width: `${Math.min((totalCommitted / requested) * 100, 100)}%`,
                      backgroundColor: gap === 0 ? '#16a34a' : totalCommitted > 0 ? '#d97706' : '#dc2626',
                    }}
                  />
                </div>
                {gap > 0 && (
                  <div className="text-[10px] text-amber-400">
                    {gap} {need.requested_resources?.[0]?.unit || 'units'} still needed
                  </div>
                )}
                {gap === 0 && totalCommitted > 0 && (
                  <div className="text-[10px] text-green-400">
                    Fully resourced
                  </div>
                )}
              </div>
            );
          })()}

          <div className="flex items-center justify-between text-[10px] text-[#6b7d93]">
            <div>
              Created: {need.created_at && formatDistanceToNow(new Date(need.created_at), { addSuffix: true })}
            </div>
            {need.updated_at && (
              <div>
                Updated: {formatDistanceToNow(new Date(need.updated_at), { addSuffix: true })}
              </div>
            )}
          </div>
          {need.reporter_id && need.reporter_id !== 'anonymous' && (
            <div className="text-[10px] text-[#6b7d93]">
              Reported by: {need.reporter_id} ({need.reporter_type})
            </div>
          )}
        </div>

        {/* RESPONDERS (Organizations participating) */}
        {(() => {
          const linkedOps = state.operations.filter(op => op.need_id === need.id);
          const linkedOffers = state.offers.filter(o => o.district_id === need.district_id && o.status !== 'WITHDRAWN');
          if (linkedOps.length === 0 && linkedOffers.length === 0) return null;

          // Collect unique organizations from operations and offers
          const orgs = new Map();
          linkedOps.forEach(op => {
            if (op.lead_organization_id) {
              orgs.set(op.lead_organization_id, {
                id: op.lead_organization_id,
                role: 'responding',
                operation: op,
              });
            }
          });
          linkedOffers.forEach(offer => {
            if (!orgs.has(offer.organization_id)) {
              orgs.set(offer.organization_id, {
                id: offer.organization_id,
                role: 'offered',
                offer: offer,
              });
            }
          });

          return (
            <div className="space-y-3 pt-4 border-t border-[#2a3a4e]">
              <div className="text-[10px] font-semibold text-[#6b7d93] uppercase tracking-wider">
                Responders ({orgs.size})
              </div>
              <div className="space-y-1.5">
                {Array.from(orgs.values()).map(org => (
                  <div
                    key={org.id}
                    className="flex items-center gap-2 px-2.5 py-1.5 rounded bg-[#1a2332] border border-[#2a3a4e]"
                  >
                    <div className="w-5 h-5 rounded-full bg-blue-500/20 flex items-center justify-center shrink-0">
                      <span className="text-[9px] font-bold text-blue-400">
                        {org.id.charAt(0).toUpperCase()}
                      </span>
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-[11px] text-[#c8d6e5] truncate">{org.id}</div>
                    </div>
                    {org.operation && (
                      <button
                        onClick={() => onOpenMatch("operation", org.operation.id, org.operation)}
                        className="text-[9px] text-blue-400 hover:text-blue-300 shrink-0"
                      >
                        View Op →
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          );
        })()}

        {/* SECTION 3: COORDINATION (The "Analysis" Layer) */}
        <div className="space-y-3 pt-4 border-t border-[#2a3a4e]">
          <div className="text-[10px] font-semibold text-[#6b7d93] uppercase tracking-wider">
            Coordination
          </div>
          {/* Error display */}
          {error && (
            <div className="px-2.5 py-2 rounded bg-red-500/10 border border-red-500/20 text-[11px] text-red-400">
              {error}
            </div>
          )}
          <div className="flex flex-wrap gap-1.5">
            {need.status === "OPEN" && (
              <button
                onClick={handleFindResources}
                disabled={loadingMatches}
                className="px-2.5 py-1.5 rounded text-[11px] font-medium bg-purple-500/10 text-purple-400 border border-purple-500/20 hover:bg-purple-500/20 transition-colors flex items-center gap-1"
              >
                <Search className="w-3 h-3" />
                {loadingMatches ? "Searching..." : "Find Resources"}
              </button>
            )}
            {need.status === "OPEN" && (
              <button
                onClick={() => handleStatusChange("RESPONDING")}
                disabled={updating}
                className="px-2.5 py-1.5 rounded text-[11px] font-medium bg-blue-500/10 text-blue-400 border border-blue-500/20 hover:bg-blue-500/20 transition-colors"
              >
                Join Response
              </button>
            )}
            {need.status === "RESPONDING" && (
              <button
                onClick={() => handleStatusChange("RESOLVED")}
                disabled={updating}
                className="px-2.5 py-1.5 rounded text-[11px] font-medium bg-green-500/10 text-green-400 border border-green-500/20 hover:bg-green-500/20 transition-colors"
              >
                Mark Resolved
              </button>
            )}
            {(need.status === "RESOLVED" || need.status === "CLOSED") && (
              <button
                onClick={() => handleStatusChange("OPEN")}
                disabled={updating}
                className="px-2.5 py-1.5 rounded text-[11px] font-medium bg-amber-500/10 text-amber-400 border border-amber-500/20 hover:bg-amber-500/20 transition-colors"
              >
                Reopen
              </button>
            )}
            {need.status !== "CLOSED" && need.status !== "RESOLVED" && (
              <button
                onClick={() => handleStatusChange("CLOSED")}
                disabled={updating}
                className="px-2.5 py-1.5 rounded text-[11px] font-medium bg-stone-500/10 text-stone-400 border border-stone-500/20 hover:bg-stone-500/20 transition-colors"
              >
                Close
              </button>
            )}
          </div>

          {/* Propose Coordination Action */}
          {need.status === "OPEN" && (
            <div className="pt-2">
              {!showPropose ? (
                <button
                  onClick={() => setShowPropose(true)}
                  className="px-2.5 py-1.5 rounded text-[11px] font-medium bg-teal-500/10 text-teal-400 border border-teal-500/20 hover:bg-teal-500/20 transition-colors flex items-center gap-1"
                >
                  <Handshake className="w-3 h-3" />
                  Propose Coordination
                </button>
              ) : (
                <form onSubmit={handleCreateProposal} className="p-3 rounded bg-[#1a2332] border border-[#2a3a4e] space-y-2">
                  <div className="text-[10px] font-semibold text-[#6b7d93] uppercase tracking-wider">
                    Target Organization
                  </div>
                  <select
                    value={selectedOrgId}
                    onChange={(e) => setSelectedOrgId(e.target.value)}
                    className="w-full px-2 py-1.5 rounded border border-[#2a3a4e] bg-[#0f1419] text-[11px] text-[#c8d6e5] outline-none"
                    required
                  >
                    <option value="">Select an organization...</option>
                    {state.organizations.map((org) => (
                      <option key={org.id} value={org.id}>
                        {org.name} ({org.id})
                      </option>
                    ))}
                  </select>
                  <div className="flex gap-1.5">
                    <button
                      type="submit"
                      disabled={proposing || !selectedOrgId}
                      className="flex-1 px-2.5 py-1.5 rounded text-[10px] font-semibold bg-teal-500/15 text-teal-400 border border-teal-500/30 hover:bg-teal-500/25 transition-colors disabled:opacity-50"
                    >
                      {proposing ? "Creating…" : "Submit Proposal"}
                    </button>
                    <button
                      type="button"
                      onClick={() => setShowPropose(false)}
                      className="px-2.5 py-1.5 rounded text-[10px] text-[#6b7d93] border border-[#2a3a4e] hover:bg-[#0f1419]"
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              )}
            </div>
          )}

          {/* Linked Coordination Proposals */}
          {proposals.length > 0 && (
            <div className="space-y-2 pt-2">
              <div className="text-[10px] font-semibold text-[#6b7d93] uppercase tracking-wider">
                Coordination Proposals ({proposals.length})
              </div>
              <div className="space-y-1.5">
                {proposals.map((p) => {
                  const statusColors = {
                    PROPOSED: "#4ea8de",
                    PENDING_ORG_REVIEW: "#d97706",
                    ORG_RECOMMENDED: "#a855f7",
                    PUBLISHED: "#16a34a",
                    CONFIRMED: "#16a34a",
                    DECLINED: "#dc2626",
                    EXPIRED: "#6b7d93",
                  };
                  const color = statusColors[p.status] || "#6b7d93";
                  return (
                    <div
                      key={p.id}
                      className="p-2.5 rounded bg-[#1a2332] border border-[#2a3a4e] space-y-1.5"
                    >
                      <div className="flex items-center justify-between">
                        <div className="text-[11px] font-semibold text-[#c8d6e5] truncate">
                          {p.organization_name || p.organization_id}
                        </div>
                        <StatusBadge status={p.status} color={color} />
                      </div>
                      <div className="text-[10px] text-[#a0aec0] line-clamp-2">
                        {p.summary}
                      </div>
                      <div className="flex items-center justify-between pt-1">
                        <button
                          onClick={() => onOpenMatch("proposal", p.id, p)}
                          className="text-[10px] text-[#4ea8de] hover:underline"
                        >
                          View Details →
                        </button>
                        <div className="flex items-center gap-1">
                          {p.status === "PROPOSED" && (
                            <button
                              onClick={() => handleSendProposal(p.id)}
                              disabled={proposalBusy === p.id}
                              className="px-2 py-0.5 rounded text-[9px] font-semibold bg-teal-500/15 text-teal-400 border border-teal-500/30 hover:bg-teal-500/25 transition-colors disabled:opacity-50"
                            >
                              {proposalBusy === p.id ? "…" : "Send to Org"}
                            </button>
                          )}
                          {p.status !== "DECLINED" && p.status !== "CONFIRMED" && p.status !== "PUBLISHED" && (
                            <button
                              onClick={() => handleDeclineProposal(p.id)}
                              disabled={proposalBusy === p.id}
                              className="px-1.5 py-0.5 rounded text-[9px] text-red-400/80 border border-red-500/20 hover:bg-red-500/10 transition-colors disabled:opacity-50"
                            >
                              Decline
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* RESOURCE MATCHES */}
        {matches && matches.matches && (
          <div className="space-y-3 pt-4 border-t border-[#2a3a4e]">
            <div className="text-[10px] font-semibold text-[#6b7d93] uppercase tracking-wider">
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

        {/* EVIDENCE SECTION */}
        {needEvidence && (
          <EvidenceSection
            evidence={needEvidence}
            confidence={needEvidence.confidence}
          />
        )}

        {/* ACTIVITY TIMELINE (GitHub-like) */}
        {history.length > 0 && (
          <div className="space-y-3 pt-4 border-t border-[#2a3a4e]">
            <div className="text-[10px] font-semibold text-[#6b7d93] uppercase tracking-wider">
              Activity
            </div>
            <div className="relative pl-4 space-y-3">
              {/* Timeline line */}
              <div className="absolute left-[7px] top-1 bottom-1 w-px bg-[#2a3a4e]" />
              {history.slice(0, 10).map((event, i) => {
                const eventColor = {
                  need_created: '#dc2626',
                  need_resolved: '#16a34a',
                  need_reopened: '#d97706',
                  need_accepted: '#2563eb',
                  match_confirmed: '#16a34a',
                  operation_created: '#2563eb',
                  resource_offered: '#0d9488',
                  status_changed: '#d97706',
                  need_updated: '#d97706',
                  field_update: '#4f46e5',
                }[event.event_type] || '#6b7d93';
                return (
                  <div key={i} className="relative flex gap-3">
                    {/* Timeline dot */}
                    <div
                      className="absolute -left-4 top-1 w-3 h-3 rounded-full border-2 border-[#0f1419]"
                      style={{ backgroundColor: eventColor }}
                    />
                    <div className="flex-1 space-y-0.5">
                      <div className="text-[11px] text-[#c8d6e5] font-medium">
                        {event.detail || event.event_type}
                      </div>
                      <div className="flex items-center gap-2 text-[9px] text-[#6b7d93]">
                        <span>{event.actor || 'System'}</span>
                        {event.created_at && (
                          <span>· {formatDistanceToNow(new Date(event.created_at), { addSuffix: true })}</span>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
              {history.length > 10 && (
                <div className="text-[10px] text-[#6b7d93] pl-1">
                  +{history.length - 10} more events
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </>
  );
}

// -------------------------------------------------------------------
// Operation detail panel
// -------------------------------------------------------------------

function OperationDetail({ data, onClose, onOpenNeed }) {
  const { state, refreshAll } = useWorkspace();
  const [operation, setOperation] = useState(data);
  const [updating, setUpdating] = useState(false);
  const [opEvidence, setOpEvidence] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch(`/api/evidence/operation/${operation.id}`)
      .then(r => r.ok ? r.json() : null)
      .then(data => setOpEvidence(data))
      .catch(() => {});
  }, [operation.id]);

  const handleStatusChange = async (newStatus) => {
    setUpdating(true);
    setError(null);
    try {
      const resp = await fetch(`/api/operations/${operation.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: newStatus }),
      });
      if (resp.ok) {
        const result = await resp.json();
        setOperation(result.operation);
        // Refresh global workspace state
        refreshAll();
      } else {
        const err = await resp.json().catch(() => ({}));
        setError(err.error || `Failed to update operation (${resp.status})`);
      }
    } catch (err) {
      console.error("Failed to update operation:", err);
      setError("Network error: could not reach server");
    } finally {
      setUpdating(false);
    }
  };

  const statusColor = {
    PLANNING: "#2563eb",
    ACTIVE: "#16a34a",
    PAUSED: "#d97706",
    COMPLETED: "#6b7280",
    CANCELLED: "#9ca3af",
  };

  // Find linked need
  const linkedNeed = operation.need_id
    ? state.needs.find(n => n.id === operation.need_id)
    : null;

  // Activity for this operation
  const history = state.activity
    .filter(e => e.entity_id === operation.id)
    .sort((a, b) => new Date(b.created_at) - new Date(a.created_at));

  return (
    <>
      <PanelHeader
        icon={Zap}
        title={operation.name}
        subtitle={`${operation.id} · ${operation.operation_type} · ${operation.status}`}
        onClose={onClose}
        color={statusColor[operation.status] || "#c8d6e5"}
      />
      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        {/* SECTION 1: STATUS */}
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <StatusBadge
              status={operation.status}
              color={statusColor[operation.status] || "#78716c"}
            />
            {operation.lead_organization_id && (
              <span className="text-[10px] text-[#6b7d93]">
                Led by {operation.lead_organization_id}
              </span>
            )}
          </div>

          {operation.description && (
            <div className="text-[13px] text-[#a0aec0] leading-relaxed font-medium">
              {operation.description}
            </div>
          )}
        </div>

        {/* SECTION 2: LINKED NEED */}
        {linkedNeed && (
          <div className="space-y-2 pt-4 border-t border-[#2a3a4e]">
            <div className="text-[10px] font-semibold text-[#6b7d93] uppercase tracking-wider">
              Linked Need
            </div>
            <button
              onClick={() => onOpenNeed && onOpenNeed("need", linkedNeed.id, linkedNeed)}
              className="w-full flex items-center justify-between px-2.5 py-2 rounded bg-[#1a2332] border border-[#2a3a4e] hover:border-red-500/30 transition-colors group"
            >
              <div className="flex items-center gap-2">
                <AlertTriangle className="w-3 h-3 text-red-400" />
                <span className="text-[11px] text-[#c8d6e5] group-hover:text-white transition-colors">
                  {linkedNeed.title || linkedNeed.need_type}
                </span>
              </div>
              <StatusBadge status={linkedNeed.status} color="#4ea8de" />
            </button>
          </div>
        )}

        {/* SECTION 3: LOCATION */}
        <div className="space-y-2 pt-4 border-t border-[#2a3a4e]">
          {operation.location_name && (
            <div className="flex items-center gap-2 text-[12px] text-[#c8d6e5] font-medium">
              <MapPin className="w-3.5 h-3.5 text-[#6b7d93]" />
              {operation.location_name}
            </div>
          )}
          {operation.participants && operation.participants.length > 0 && (
            <div className="space-y-2">
              <div className="text-[10px] font-semibold text-[#6b7d93] uppercase tracking-wider">
                Participants
              </div>
              <div className="grid grid-cols-1 gap-1.5">
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
        </div>

        {/* SECTION 4: COORDINATION */}
        <div className="space-y-3 pt-4 border-t border-[#2a3a4e]">
          <div className="text-[10px] font-semibold text-[#6b7d93] uppercase tracking-wider">
            Actions
          </div>
          {/* Error display */}
          {error && (
            <div className="px-2.5 py-2 rounded bg-red-500/10 border border-red-500/20 text-[11px] text-red-400">
              {error}
            </div>
          )}
          <div className="flex flex-wrap gap-1.5">
            {operation.status === "PLANNING" && (
              <button
                onClick={() => handleStatusChange("ACTIVE")}
                disabled={updating}
                className="px-2.5 py-1.5 rounded text-[11px] font-medium bg-green-500/10 text-green-400 border border-green-500/20 hover:bg-green-500/20 transition-colors"
              >
                Activate
              </button>
            )}
            {(operation.status === "ACTIVE" || operation.status === "PLANNING") && (
              <button
                onClick={() => handleStatusChange("COMPLETED")}
                disabled={updating}
                className="px-2.5 py-1.5 rounded text-[11px] font-medium bg-blue-500/10 text-blue-400 border border-blue-500/20 hover:bg-blue-500/20 transition-colors"
              >
                Complete
              </button>
            )}
            {operation.status !== "COMPLETED" && operation.status !== "CANCELLED" && (
              <button
                onClick={() => handleStatusChange("CANCELLED")}
                disabled={updating}
                className="px-2.5 py-1.5 rounded text-[11px] font-medium bg-stone-500/10 text-stone-400 border border-stone-500/20 hover:bg-stone-500/20 transition-colors"
              >
                Cancel
              </button>
            )}
          </div>
        </div>

        {/* EVIDENCE SECTION */}
        {opEvidence && (
          <EvidenceSection
            evidence={opEvidence}
            confidence={opEvidence.confidence}
          />
        )}

        {/* SECTION 5: ACTIVITY */}
        {history.length > 0 && (
          <div className="space-y-3 pt-4 border-t border-[#2a3a4e]">
            <div className="text-[10px] font-semibold text-[#6b7d93] uppercase tracking-wider">
              Activity
            </div>
            <div className="relative pl-4 space-y-3">
              <div className="absolute left-[7px] top-1 bottom-1 w-px bg-[#2a3a4e]" />
              {history.slice(0, 10).map((event, i) => {
                const eventColor = {
                  operation_created: '#2563eb',
                  operation_activated: '#16a34a',
                  operation_resolved: '#16a34a',
                  operation_cancelled: '#9ca3af',
                  match_confirmed: '#16a34a',
                  status_changed: '#d97706',
                  field_update: '#4f46e5',
                }[event.event_type] || '#6b7d93';
                return (
                  <div key={i} className="relative flex gap-3">
                    <div
                      className="absolute -left-4 top-1 w-3 h-3 rounded-full border-2 border-[#0f1419]"
                      style={{ backgroundColor: eventColor }}
                    />
                    <div className="flex-1 space-y-0.5">
                      <div className="text-[11px] text-[#c8d6e5] font-medium">
                        {event.detail || event.event_type}
                      </div>
                      <div className="flex items-center gap-2 text-[9px] text-[#6b7d93]">
                        <span>{event.actor || 'System'}</span>
                        {event.created_at && (
                          <span>· {formatDistanceToNow(new Date(event.created_at), { addSuffix: true })}</span>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* METADATA */}
        <div className="flex items-center justify-between text-[10px] text-[#6b7d93] pt-4 border-t border-[#2a3a4e]">
          <div>
            Created: {operation.created_at && formatDistanceToNow(new Date(operation.created_at), { addSuffix: true })}
          </div>
        </div>
      </div>
    </>
  );
}

// -------------------------------------------------------------------
// Offer detail panel
// -------------------------------------------------------------------

function OfferDetail({ data, onClose }) {
  const { state } = useWorkspace();

  // Find matching needs for this offer
  const matchingNeeds = state.needs.filter(n =>
    n.district_id === data.district_id &&
    n.status !== 'RESOLVED' && n.status !== 'CLOSED' &&
    n.need_type === data.resource_type
  );

  return (
    <>
      <PanelHeader
        icon={Package}
        title={`${data.resource_type} — ${data.quantity} ${data.unit}`}
        subtitle={`${data.id} · Resource Offer · ${data.status}`}
        onClose={onClose}
        color="#0d9488"
      />
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        <div className="flex items-center gap-2">
          <StatusBadge status={data.status} color="#0d9488" />
          {data.quantity > 0 && (
            <span className="text-[10px] font-mono text-[#6b7d93]">
              {data.quantity} {data.unit}
            </span>
          )}
        </div>

        {data.location_name && (
          <div className="flex items-center gap-2 text-[12px] text-[#c8d6e5]">
            <MapPin className="w-3.5 h-3.5 text-[#6b7d93]" />
            {data.location_name}
          </div>
        )}

        <div className="flex items-center gap-2 text-[11px] text-[#a0aec0]">
          <span className="text-[10px] text-[#6b7d93]">Organization:</span>
          <span className="font-medium">{data.organization_id}</span>
        </div>

        {data.notes && (
          <div className="text-[12px] text-[#a0aec0] leading-relaxed">
            {data.notes}
          </div>
        )}

        <div className="text-[10px] text-[#6b7d93]">
          Published: {data.created_at && formatDistanceToNow(new Date(data.created_at), { addSuffix: true })}
        </div>

        {/* Matching needs */}
        {matchingNeeds.length > 0 && (
          <div className="space-y-2 pt-3 border-t border-[#2a3a4e]">
            <div className="text-[10px] font-semibold text-[#6b7d93] uppercase tracking-wider">
              Matching Needs ({matchingNeeds.length})
            </div>
            {matchingNeeds.slice(0, 5).map(need => (
              <div
                key={need.id}
                className="flex items-center justify-between px-2.5 py-1.5 rounded bg-[#1a2332] border border-[#2a3a4e]"
              >
                <div className="flex items-center gap-2">
                  <AlertTriangle className="w-3 h-3 text-red-400" />
                  <span className="text-[11px] text-[#c8d6e5]">
                    {need.title || need.need_type}
                  </span>
                </div>
                <StatusBadge status={need.urgency} color="#d97706" />
              </div>
            ))}
          </div>
        )}
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
  const { refreshAll } = useWorkspace();
  const [showOverride, setShowOverride] = useState(false);
  const [overrideStatus, setOverrideStatus] = useState("submerged");
  const [overrideReason, setOverrideReason] = useState("");
  const [error, setError] = useState(null);

  const handleApplyOverride = async () => {
    setError(null);
    try {
      const resp = await fetch("/api/override", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target_type: "facility",
          target_id: data.name,
          new_status: overrideStatus,
          reason: overrideReason,
        }),
      });
      if (resp.ok) {
        refreshAll();
        onClose();
      } else {
        const err = await resp.json().catch(() => ({}));
        setError(err.error || `Failed to apply override (${resp.status})`);
      }
    } catch (err) {
      console.error("Override failed:", err);
      setError("Network error: could not reach server");
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
  const { state, refreshAll, startPinpoint, clearPinpoint } = useWorkspace();
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
  const [error, setError] = useState(null);

  // Auto-sync coordinates from pinpoint mode
  useEffect(() => {
    if (state.pinpointMode?.coords && state.pinpointMode.formType === "need") {
      setForm((prev) => ({
        ...prev,
        lat: state.pinpointMode.coords.lat.toString(),
        lon: state.pinpointMode.coords.lon.toString(),
      }));
    }
  }, [state.pinpointMode?.coords, state.pinpointMode?.formType]);

  const handleClose = () => {
    clearPinpoint();
    onClose();
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
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
        clearPinpoint();
        refreshAll();
        onClose();
      } else {
        const err = await resp.json().catch(() => ({}));
        setError(err.error || `Failed to create need (${resp.status})`);
      }
    } catch (err) {
      console.error("Failed to create need:", err);
      setError("Network error: could not reach server");
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
        onClose={handleClose}
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

        <div>
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[11px] font-medium text-[#c8d6e5]">Geographic Coordinates</span>
            <button
              type="button"
              onClick={() => startPinpoint("need")}
              className={cn(
                "flex items-center gap-1.5 px-2 py-0.5 rounded text-[10px] font-medium border transition-all",
                state.pinpointMode?.active && state.pinpointMode?.formType === "need"
                  ? "bg-red-500/20 text-red-400 border-red-500/60 animate-pulse"
                  : "bg-[#1a2332] text-[#c8d6e5] border-[#2a3a4e] hover:border-red-500/40 hover:text-red-400"
              )}
            >
              <Crosshair className="w-3 h-3 text-red-400" />
              {state.pinpointMode?.active && state.pinpointMode?.formType === "need"
                ? "Pinpoint Active (Click Map)"
                : "Pinpoint on Map"}
            </button>
          </div>
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
          {form.lat && form.lon && (
            <div className="text-[10px] text-red-400/80 mt-1 flex items-center gap-1">
              <MapPin className="w-3 h-3" />
              Pinned at {form.lat}, {form.lon}
            </div>
          )}
        </div>

        {/* Error display */}
        {error && (
          <div className="px-2.5 py-2 rounded bg-red-500/10 border border-red-500/20 text-[11px] text-red-400">
            {error}
          </div>
        )}
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
  const { state, refreshAll, startPinpoint, clearPinpoint } = useWorkspace();
  const [form, setForm] = useState({
    raw_text: "",
    lat: defaultData?.lat ? defaultData.lat.toString() : "",
    lon: defaultData?.lon ? defaultData.lon.toString() : "",
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  // Auto-sync coordinates from pinpoint mode
  useEffect(() => {
    if (state.pinpointMode?.coords && state.pinpointMode.formType === "report") {
      setForm((prev) => ({
        ...prev,
        lat: state.pinpointMode.coords.lat.toString(),
        lon: state.pinpointMode.coords.lon.toString(),
      }));
    }
  }, [state.pinpointMode?.coords, state.pinpointMode?.formType]);

  const handleClose = () => {
    clearPinpoint();
    onClose();
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const resp = await fetch("/api/field-intelligence", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          raw_text: form.raw_text,
          lat: form.lat ? parseFloat(form.lat) : null,
          lon: form.lon ? parseFloat(form.lon) : null,
        }),
      });
      if (resp.ok) {
        clearPinpoint();
        refreshAll();
        onClose();
      } else {
        const err = await resp.json().catch(() => ({}));
        setError(err.error || `Failed to submit report (${resp.status})`);
      }
    } catch (err) {
      console.error("Failed to submit report:", err);
      setError("Network error: could not reach server");
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
        onClose={handleClose}
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

        <div>
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[11px] font-medium text-[#c8d6e5]">Geographic Coordinates</span>
            <button
              type="button"
              onClick={() => startPinpoint("report")}
              className={cn(
                "flex items-center gap-1.5 px-2 py-0.5 rounded text-[10px] font-medium border transition-all",
                state.pinpointMode?.active && state.pinpointMode?.formType === "report"
                  ? "bg-indigo-500/20 text-indigo-400 border-indigo-500/60 animate-pulse"
                  : "bg-[#1a2332] text-[#c8d6e5] border-[#2a3a4e] hover:border-indigo-500/40 hover:text-indigo-400"
              )}
            >
              <Crosshair className="w-3 h-3 text-indigo-400" />
              {state.pinpointMode?.active && state.pinpointMode?.formType === "report"
                ? "Pinpoint Active (Click Map)"
                : "Pinpoint on Map"}
            </button>
          </div>
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
        </div>

        {/* Error display */}
        {error && (
          <div className="px-2.5 py-2 rounded bg-red-500/10 border border-red-500/20 text-[11px] text-red-400">
            {error}
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
  const { state, refreshAll, startPinpoint, clearPinpoint } = useWorkspace();
  const [form, setForm] = useState({
    resource_type: "boat",
    quantity: 1,
    unit: "units",
    location_name: "",
    lat: "",
    lon: "",
    notes: "",
    // Display-only hint: the server derives the publishing org from the
    // session context (identity seam) and never trusts this value.
    organization_id: state.orgId || "",
  });
  const [submitting, setSubmitting] = useState(false);
  const submittingRef = useRef(false); // sync double-submit guard (rapid re-clicks)
  const [error, setError] = useState(null);

  // Keep the displayed org in sync with the session context.
  useEffect(() => {
    if (state.orgId) {
      setForm((current) => ({
        ...current,
        organization_id: state.orgId,
      }));
    }
  }, [state.orgId]);

  // Auto-sync coordinates from pinpoint mode
  useEffect(() => {
    if (state.pinpointMode?.coords && state.pinpointMode.formType === "offer") {
      setForm((prev) => ({
        ...prev,
        lat: state.pinpointMode.coords.lat.toString(),
        lon: state.pinpointMode.coords.lon.toString(),
      }));
    }
  }, [state.pinpointMode?.coords, state.pinpointMode?.formType]);

  const handleClose = () => {
    clearPinpoint();
    onClose();
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (submittingRef.current) return;
    submittingRef.current = true;
    setSubmitting(true);
    setError(null);
    try {
      // The server resolves the publishing org from the session context;
      // form.organization_id is display-only and ignored server-side.
      const resp = await fetch(`/api/my-org/publish-offer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          resource_type: form.resource_type,
          quantity: parseInt(form.quantity) || 0,
          unit: form.unit,
          location_name: form.location_name,
          lat: form.lat ? parseFloat(form.lat) : null,
          lon: form.lon ? parseFloat(form.lon) : null,
          district_id: state.filters.district,
          notes: form.notes,
        }),
      });
      if (resp.ok) {
        clearPinpoint();
        refreshAll();
        onClose();
      } else {
        const err = await resp.json().catch(() => ({}));
        setError(err.error || `Failed to create offer (${resp.status})`);
      }
    } catch (err) {
      console.error("Failed to create offer:", err);
      setError("Network error: could not reach server");
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
    }
  };

  return (
    <>
      <PanelHeader
        icon={Package}
        title="Offer Resource"
        subtitle="Publish available resources"
        onClose={handleClose}
        color="#0d9488"
      />
      <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-4 space-y-3">
        <Field label="Organization">
          <select
            value={form.organization_id}
            onChange={(e) => setForm({ ...form, organization_id: e.target.value })}
            className="w-full px-2.5 py-1.5 rounded border border-[#2a3a4e] bg-[#0f1419] text-[12px] text-[#c8d6e5] outline-none"
            required
          >
            {state.organizations.length === 0 ? (
              <option value="org_reliefos_default">ReliefOS Coordination Cell</option>
            ) : (
              state.organizations.map((organization) => (
                <option key={organization.id} value={organization.id}>
                  {organization.name}
                </option>
              ))
            )}
          </select>
        </Field>
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

        <div>
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[11px] font-medium text-[#c8d6e5]">Geographic Coordinates</span>
            <button
              type="button"
              onClick={() => startPinpoint("offer")}
              className={cn(
                "flex items-center gap-1.5 px-2 py-0.5 rounded text-[10px] font-medium border transition-all",
                state.pinpointMode?.active && state.pinpointMode?.formType === "offer"
                  ? "bg-teal-500/20 text-teal-400 border-teal-500/60 animate-pulse"
                  : "bg-[#1a2332] text-[#c8d6e5] border-[#2a3a4e] hover:border-teal-500/40 hover:text-teal-400"
              )}
            >
              <Crosshair className="w-3 h-3 text-teal-400" />
              {state.pinpointMode?.active && state.pinpointMode?.formType === "offer"
                ? "Pinpoint Active (Click Map)"
                : "Pinpoint on Map"}
            </button>
          </div>
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
          {form.lat && form.lon && (
            <div className="text-[10px] text-teal-400/80 mt-1 flex items-center gap-1">
              <MapPin className="w-3 h-3" />
              Pinned at {form.lat}, {form.lon}
            </div>
          )}
        </div>

        <Field label="Notes">
          <textarea
            value={form.notes}
            onChange={(e) => setForm({ ...form, notes: e.target.value })}
            placeholder="Additional details..."
            className="w-full h-16 px-2.5 py-1.5 rounded border border-[#2a3a4e] bg-[#0f1419] text-[12px] text-[#c8d6e5] placeholder:text-[#6b7d93] outline-none resize-none"
          />
        </Field>

        {/* Error display */}
        {error && (
          <div className="px-2.5 py-2 rounded bg-red-500/10 border border-red-500/20 text-[11px] text-red-400">
            {error}
          </div>
        )}
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
// Create Operation form
// -------------------------------------------------------------------

function CreateOperationForm({ onClose }) {
  const { state, refreshAll, startPinpoint, clearPinpoint } = useWorkspace();
  const [form, setForm] = useState({
    name: "",
    operation_type: "supply_delivery",
    description: "",
    need_id: "",
    lead_organization_id: "",
    location_name: "",
    lat: "",
    lon: "",
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  // Auto-sync coordinates from pinpoint mode
  useEffect(() => {
    if (state.pinpointMode?.coords && state.pinpointMode.formType === "operation") {
      setForm((prev) => ({
        ...prev,
        lat: state.pinpointMode.coords.lat.toString(),
        lon: state.pinpointMode.coords.lon.toString(),
      }));
    }
  }, [state.pinpointMode?.coords, state.pinpointMode?.formType]);

  const handleClose = () => {
    clearPinpoint();
    onClose();
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const resp = await fetch("/api/operations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...form,
          need_id: form.need_id || null,
          lead_organization_id: form.lead_organization_id || null,
          lat: form.lat ? parseFloat(form.lat) : null,
          lon: form.lon ? parseFloat(form.lon) : null,
        }),
      });
      if (resp.ok) {
        clearPinpoint();
        refreshAll();
        onClose();
      } else {
        const err = await resp.json().catch(() => ({}));
        setError(err.error || `Failed to create operation (${resp.status})`);
      }
    } catch (err) {
      console.error("Failed to create operation:", err);
      setError("Network error: could not reach server");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <PanelHeader
        icon={Zap}
        title="Create Operation"
        subtitle="Start a coordinated response"
        onClose={handleClose}
        color="#2563eb"
      />
      <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-4 space-y-3">
        <Field label="Operation Name">
          <input
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="e.g., Water delivery to Demow camp"
            className="w-full px-2.5 py-1.5 rounded border border-[#2a3a4e] bg-[#0f1419] text-[12px] text-[#c8d6e5] placeholder:text-[#6b7d93] outline-none"
            required
          />
        </Field>

        <Field label="Type">
          <select
            value={form.operation_type}
            onChange={(e) => setForm({ ...form, operation_type: e.target.value })}
            className="w-full px-2.5 py-1.5 rounded border border-[#2a3a4e] bg-[#0f1419] text-[12px] text-[#c8d6e5] outline-none"
          >
            {["rescue", "medical", "supply_delivery", "evacuation", "assessment", "collaboration", "other"].map(
              (t) => (
                <option key={t} value={t}>
                  {t.replace(/_/g, " ")}
                </option>
              )
            )}
          </select>
        </Field>

        <Field label="Description">
          <textarea
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            placeholder="Details about this operation..."
            className="w-full h-16 px-2.5 py-1.5 rounded border border-[#2a3a4e] bg-[#0f1419] text-[12px] text-[#c8d6e5] placeholder:text-[#6b7d93] outline-none resize-none"
          />
        </Field>

        <Field label="Linked Need (optional)">
          <select
            value={form.need_id}
            onChange={(e) => setForm({ ...form, need_id: e.target.value })}
            className="w-full px-2.5 py-1.5 rounded border border-[#2a3a4e] bg-[#0f1419] text-[12px] text-[#c8d6e5] outline-none"
          >
            <option value="">None</option>
            {state.needs.filter(n => n.status !== "RESOLVED" && n.status !== "CLOSED").map(n => (
              <option key={n.id} value={n.id}>
                {n.title || n.need_type} ({n.id})
              </option>
            ))}
          </select>
        </Field>

        <Field label="Lead Organization (optional)">
          <select
            value={form.lead_organization_id}
            onChange={(e) => setForm({ ...form, lead_organization_id: e.target.value })}
            className="w-full px-2.5 py-1.5 rounded border border-[#2a3a4e] bg-[#0f1419] text-[12px] text-[#c8d6e5] outline-none"
          >
            <option value="">None</option>
            {state.organizations.map(o => (
              <option key={o.id} value={o.id}>
                {o.name} ({o.id})
              </option>
            ))}
          </select>
        </Field>

        <Field label="Location Name">
          <input
            value={form.location_name}
            onChange={(e) => setForm({ ...form, location_name: e.target.value })}
            placeholder="e.g., Demow, Jorhat"
            className="w-full px-2.5 py-1.5 rounded border border-[#2a3a4e] bg-[#0f1419] text-[12px] text-[#c8d6e5] placeholder:text-[#6b7d93] outline-none"
          />
        </Field>

        <div>
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[11px] font-medium text-[#c8d6e5]">Geographic Coordinates</span>
            <button
              type="button"
              onClick={() => startPinpoint("operation")}
              className={cn(
                "flex items-center gap-1.5 px-2 py-0.5 rounded text-[10px] font-medium border transition-all",
                state.pinpointMode?.active && state.pinpointMode?.formType === "operation"
                  ? "bg-blue-500/20 text-blue-400 border-blue-500/60 animate-pulse"
                  : "bg-[#1a2332] text-[#c8d6e5] border-[#2a3a4e] hover:border-blue-500/40 hover:text-blue-400"
              )}
            >
              <Crosshair className="w-3 h-3 text-blue-400" />
              {state.pinpointMode?.active && state.pinpointMode?.formType === "operation"
                ? "Pinpoint Active (Click Map)"
                : "Pinpoint on Map"}
            </button>
          </div>
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
          {form.lat && form.lon && (
            <div className="text-[10px] text-blue-400/80 mt-1 flex items-center gap-1">
              <MapPin className="w-3 h-3" />
              Pinned at {form.lat}, {form.lon}
            </div>
          )}
        </div>

        {/* Error display */}
        {error && (
          <div className="px-2.5 py-2 rounded bg-red-500/10 border border-red-500/20 text-[11px] text-red-400">
            {error}
          </div>
        )}
        <button
          type="submit"
          disabled={submitting || !form.name.trim()}
          className={cn(
            "w-full px-3 py-2 rounded text-[12px] font-semibold transition-colors",
            form.name.trim() && !submitting
              ? "bg-blue-500/20 text-blue-400 border border-blue-500/30 hover:bg-blue-500/30"
              : "bg-[#1a2332] text-[#6b7d93] border border-[#2a3a4e] cursor-not-allowed"
          )}
        >
          {submitting ? "Creating..." : "Create Operation"}
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
// Severity styling helpers
// -------------------------------------------------------------------

const SEVERITY_CONFIG = {
  critical: { color: "#dc2626", bg: "rgba(220,38,38,0.1)", border: "rgba(220,38,38,0.25)" },
  high:     { color: "#f97316", bg: "rgba(249,115,22,0.1)", border: "rgba(249,115,22,0.25)" },
  medium:   { color: "#eab308", bg: "rgba(234,179,8,0.1)",  border: "rgba(234,179,8,0.25)" },
  low:      { color: "#22c55e", bg: "rgba(34,197,94,0.1)",  border: "rgba(34,197,94,0.25)" },
};

const FINDING_TYPE_LABELS = {
  coordination_gap:   "Coordination Gap",
  duplicate_response: "Duplicate Response",
  consequence_alert:  "Consequence Alert",
};

// -------------------------------------------------------------------
// AI Coordinator Findings panel
// -------------------------------------------------------------------

// -------------------------------------------------------------------
// Network Agent Section — Network Main Agent analysis
// -------------------------------------------------------------------

function NetworkAgentSection() {
  const { openPanel, setMapCenter } = useWorkspace();
  const [networkAnalysis, setNetworkAnalysis] = useState(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    fetch("/api/network/agent/situation")
      .then(r => r.ok ? r.json() : null)
      .then(data => setNetworkAnalysis(data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="p-2 rounded bg-[#1a2332] border border-[#2a3a4e]">
        <div className="text-[10px] text-[#6b7d93] animate-pulse">Loading network analysis...</div>
      </div>
    );
  }

  if (!networkAnalysis) return null;

  const severity = networkAnalysis.severity_summary || {};
  const actions = networkAnalysis.recommended_actions || [];
  const risks = networkAnalysis.risks || [];

  return (
    <div className="space-y-2 pt-3 border-t border-[#2a3a4e]">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-2 py-1.5 rounded bg-[#1a2332] border border-[#2a3a4e] hover:border-[#4ea8de]/30 transition-colors"
      >
        <div className="flex items-center gap-2">
          <Globe className="w-3.5 h-3.5 text-[#4ea8de]" />
          <span className="text-[11px] font-semibold text-[#c8d6e5]">Network Agent</span>
        </div>
        <div className="flex items-center gap-1.5">
          {severity.critical > 0 && <span className="text-[9px] font-mono text-red-400">{severity.critical}</span>}
          {severity.urgent > 0 && <span className="text-[9px] font-mono text-amber-400">{severity.urgent}</span>}
          <ChevronDown className={cn("w-3 h-3 text-[#6b7d93] transition-transform", expanded && "rotate-180")} />
        </div>
      </button>

      {expanded && (
        <div className="space-y-2 px-1">
          {/* Summary */}
          <div className="text-[10px] text-[#a0aec0]">{networkAnalysis.summary}</div>

          {/* Priority needs */}
          {networkAnalysis.priority_needs && networkAnalysis.priority_needs.length > 0 && (
            <div className="space-y-1">
              <div className="text-[9px] font-semibold text-[#6b7d93] uppercase tracking-wider">PRIORITY NEEDS</div>
              {networkAnalysis.priority_needs.slice(0, 3).map((n, i) => (
                <div key={i} className="flex items-center gap-2 text-[10px]">
                  <AlertTriangle className="w-3 h-3 shrink-0" style={{ color: n.severity === 'critical' ? '#dc2626' : '#d97706' }} />
                  <span className="text-[#a0aec0]">{n.title}</span>
                </div>
              ))}
            </div>
          )}

          {/* Risks */}
          {risks.length > 0 && (
            <div className="space-y-1">
              <div className="text-[9px] font-semibold text-[#6b7d93] uppercase tracking-wider">RISKS</div>
              {risks.slice(0, 3).map((r, i) => (
                <div key={i} className="flex items-center gap-2 text-[10px]">
                  <Shield className="w-3 h-3 shrink-0 text-amber-400" />
                  <span className="text-[#a0aec0]">{r.title}</span>
                </div>
              ))}
            </div>
          )}

          {/* Recommended actions */}
          {actions.length > 0 && (
            <div className="space-y-1">
              <div className="text-[9px] font-semibold text-[#6b7d93] uppercase tracking-wider">RECOMMENDED ACTIONS</div>
              {actions.slice(0, 3).map((a, i) => (
                <div key={i} className="text-[10px] text-[#a0aec0]">• {a.detail}</div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function AIAnalysisPanel({ onClose }) {
  const { openPanel, setMapCenter, state, fetchAiAnalysis } = useWorkspace();
  const analysis = state.aiAnalysis;
  const loading = state.aiLoading && !analysis;
  const error = null;

  const findings = analysis?.findings || [];
  const summary = analysis?.summary || { total: 0, critical: 0, high: 0, medium: 0, low: 0 };
  const dataGaps = analysis?.data_gaps || [];

  return (
    <>
      <PanelHeader
        icon={Shield}
        title="AI Coordinator"
        subtitle={
          loading
            ? "Analyzing..."
            : `${summary.total} finding${summary.total !== 1 ? "s" : ""} · ${_timeAgo(analysis?.generated_at)}`
        }
        onClose={onClose}
        color="#7c3aed"
      />
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {/* Loading state */}
        {loading && (
          <div className="flex items-center justify-center py-8">
            <div className="text-[12px] text-[#6b7d93] animate-pulse">
              Analyzing operational state...
            </div>
          </div>
        )}

        {/* Error state */}
        {error && !loading && (
          <div className="p-3 rounded bg-red-500/10 border border-red-500/20">
            <div className="text-[12px] text-red-400">{error}</div>
            <button
              onClick={fetchAiAnalysis}
              className="mt-2 text-[11px] text-red-400 underline hover:text-red-300"
            >
              Retry
            </button>
          </div>
        )}

        {/* Summary badges */}
        {!loading && !error && summary.total > 0 && (
          <div className="flex items-center gap-2 flex-wrap">
            {summary.critical > 0 && (
              <span
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold uppercase"
                style={{ color: SEVERITY_CONFIG.critical.color, backgroundColor: SEVERITY_CONFIG.critical.bg, border: `1px solid ${SEVERITY_CONFIG.critical.border}` }}
              >
                {summary.critical} critical
              </span>
            )}
            {summary.high > 0 && (
              <span
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold uppercase"
                style={{ color: SEVERITY_CONFIG.high.color, backgroundColor: SEVERITY_CONFIG.high.bg, border: `1px solid ${SEVERITY_CONFIG.high.border}` }}
              >
                {summary.high} high
              </span>
            )}
            {summary.medium > 0 && (
              <span
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold uppercase"
                style={{ color: SEVERITY_CONFIG.medium.color, backgroundColor: SEVERITY_CONFIG.medium.bg, border: `1px solid ${SEVERITY_CONFIG.medium.border}` }}
              >
                {summary.medium} medium
              </span>
            )}
            {summary.low > 0 && (
              <span
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold uppercase"
                style={{ color: SEVERITY_CONFIG.low.color, backgroundColor: SEVERITY_CONFIG.low.bg, border: `1px solid ${SEVERITY_CONFIG.low.border}` }}
              >
                {summary.low} low
              </span>
            )}
          </div>
        )}

        {/* No findings */}
        {!loading && !error && findings.length === 0 && (
          <div className="py-6 text-center">
            <CheckCircle className="w-6 h-6 text-green-500 mx-auto mb-2" />
            <div className="text-[12px] text-[#6b7d93]">
              No coordination issues detected
            </div>
            <div className="text-[10px] text-[#4a5568] mt-1">
              All needs have responders and routes are clear
            </div>
          </div>
        )}

        {/* Finding cards */}
        {findings.map((finding, idx) => {
          const sev = SEVERITY_CONFIG[finding.severity] || SEVERITY_CONFIG.medium;
          return (
            <div
              key={idx}
              className="rounded border overflow-hidden"
              style={{ backgroundColor: sev.bg, borderColor: sev.border }}
            >
              {/* Card header */}
              <div className="px-3 py-2 border-b" style={{ borderColor: sev.border }}>
                <div className="flex items-center gap-2">
                  <span
                    className="px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider"
                    style={{ color: sev.color, backgroundColor: `${sev.color}20`, border: `1px solid ${sev.color}40` }}
                  >
                    {finding.severity}
                  </span>
                  <span className="text-[10px] text-[#6b7d93]">
                    {FINDING_TYPE_LABELS[finding.type] || finding.type}
                  </span>
                </div>
                <div className="text-[13px] font-semibold mt-1" style={{ color: sev.color }}>
                  {finding.title}
                </div>
              </div>

              {/* Card body */}
              <div className="px-3 py-2 space-y-2">
                <div className="text-[11px] text-[#a0aec0] leading-relaxed">
                  {finding.summary}
                </div>

                {/* Location */}
                {finding.location && (
                  <div className="flex items-center gap-1.5 text-[10px] text-[#6b7d93]">
                    <MapPin className="w-3 h-3" />
                    {finding.location}
                  </div>
                )}

                {/* Evidence */}
                {finding.evidence && Object.keys(finding.evidence).length > 0 && (
                  <div className="p-2 rounded bg-[#0f1419]/60 border border-[#2a3a4e]/50">
                    <div className="text-[9px] font-semibold text-[#6b7d93] uppercase tracking-wider mb-1">
                      Evidence
                    </div>
                    <div className="space-y-0.5">
                      {_renderEvidence(finding.evidence)}
                    </div>
                  </div>
                )}

                {/* Uncertainty */}
                {finding.uncertainty && finding.uncertainty.length > 0 && (
                  <div className="space-y-0.5">
                    {finding.uncertainty.map((u, i) => (
                      <div key={i} className="text-[10px] text-amber-400/80 flex items-start gap-1">
                        <span className="shrink-0">⚠</span>
                        <span>{u}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Suggested action */}
              {finding.suggested_action && (
                <div className="px-3 py-2 border-t" style={{ borderColor: sev.border }}>
                  <button
                    onClick={() => _handleFindingAction(finding, openPanel, setMapCenter, state)}
                    className="w-full px-3 py-1.5 rounded text-[11px] font-medium transition-colors border bg-purple-500/10 text-purple-400 border-purple-500/25 hover:bg-purple-500/20"
                  >
                    {finding.suggested_action.label}
                  </button>
                </div>
              )}
            </div>
          );
        })}

        {/* Data gaps */}
        {!loading && !error && dataGaps.length > 0 && (
          <div className="mt-2">
            <div className="text-[10px] font-semibold text-[#6b7d93] uppercase tracking-wider mb-2">
              Data Gaps
            </div>
            <div className="space-y-1.5">
              {dataGaps.map((gap, i) => (
                <div
                  key={i}
                  className="px-2.5 py-2 rounded bg-[#1a2332] border border-[#2a3a4e]"
                >
                  <div className="text-[11px] text-[#a0aec0]">
                    {gap.item || gap}
                  </div>
                  {gap.detail && (
                    <div className="text-[10px] text-[#6b7d93] mt-0.5">
                      {gap.detail}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Refresh */}
        {/* Network Agent Section */}
        {!loading && !error && <NetworkAgentSection />}

        {!loading && !error && (
          <button
            onClick={fetchAiAnalysis}
            className="w-full mt-2 px-3 py-1.5 rounded text-[11px] text-[#6b7d93] border border-[#2a3a4e] hover:bg-[#1a2332] transition-colors"
          >
            Refresh analysis
          </button>
        )}
      </div>
    </>
  );
}

// -------------------------------------------------------------------
// Finding action handler — navigates to the relevant workspace object
// -------------------------------------------------------------------

function _handleFindingAction(finding, openPanel, setMapCenter, state) {
  const target = finding.review_target;
  if (!target) return;

  // 1. Apply district filter if the finding has one
  if (target.district_id) {
    // Only set filter if not already filtered to this district
    if (state.filters.district !== target.district_id) {
      // District filter is set via the reducer; we use the workspace's setFilter
      // But since we don't have setFilter here, we rely on map_center for context
    }
  }

  // 2. Center the map on the finding's location if available
  if (target.map_center && target.map_center[0] != null && target.map_center[1] != null) {
    setMapCenter(target.map_center);
  }

  // 3. Open the relevant panel with the entity data
  if (target.panel_type && target.entity_id) {
    // Try to find the full object from workspace state for a richer panel
    let entityData = target.entity_data || null;

    if (!entityData) {
      // Look up from workspace state
      if (target.panel_type === "need") {
        entityData = state.needs.find((n) => n.id === target.entity_id) || null;
      } else if (target.panel_type === "operation") {
        entityData = state.operations.find((o) => o.id === target.entity_id) || null;
      } else if (target.panel_type === "offer") {
        entityData = state.offers.find((o) => o.id === target.entity_id) || null;
      }
    }

    openPanel(target.panel_type, target.entity_id, entityData);
  }
}

// -------------------------------------------------------------------
// Evidence rendering helper
// -------------------------------------------------------------------

function _renderEvidence(evidence) {
  const entries = Object.entries(evidence).filter(([, v]) => v != null && v !== "");
  return entries.map(([key, value]) => {
    const label = key.replace(/_/g, " ");
    let display = value;
    if (typeof value === "boolean") display = value ? "Yes" : "No";
    if (typeof value === "number") {
      display = key.includes("_hours") ? `${value}h` : value;
    }
    if (Array.isArray(value)) display = value.length > 0 ? value.join(", ") : "None";
    return (
      <div key={key} className="flex items-start gap-2 text-[10px]">
        <span className="text-[#6b7d93] shrink-0 min-w-[80px]">
          {label}:
        </span>
        <span className="text-[#a0aec0] break-all">
          {String(display)}
        </span>
      </div>
    );
  });
}

// -------------------------------------------------------------------
// Time ago helper
// -------------------------------------------------------------------

function _timeAgo(isoStr) {
  if (!isoStr) return "";
  try {
    const date = new Date(isoStr);
    const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
    if (seconds < 60) return "just now";
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    return `${Math.floor(seconds / 86400)}d ago`;
  } catch {
    return "";
  }
}

// -------------------------------------------------------------------
// Road detail panel
// -------------------------------------------------------------------

function RoadDetail({ data, onClose }) {
  const { refreshAll } = useWorkspace();
  const [showOverride, setShowOverride] = useState(false);
  const [overrideStatus, setOverrideStatus] = useState("blocked");
  const [overrideReason, setOverrideReason] = useState("");
  const [error, setError] = useState(null);

  const handleApplyOverride = async () => {
    setError(null);
    try {
      const resp = await fetch("/api/override", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target_type: "road",
          target_id: data.name,
          new_status: overrideStatus,
          reason: overrideReason,
        }),
      });
      if (resp.ok) {
        refreshAll();
        onClose();
      } else {
        const err = await resp.json().catch(() => ({}));
        setError(err.error || `Failed to apply override (${resp.status})`);
      }
    } catch (err) {
      console.error("Override failed:", err);
      setError("Network error: could not reach server");
    }
  };

  const statusColor = {
    open: MAP_STYLES.road.open.color,
    uncertain: MAP_STYLES.road.uncertain.color,
    blocked: MAP_STYLES.road.blocked.color,
    submerged: MAP_STYLES.road.blocked.color,
    damaged: MAP_STYLES.road.blocked.color,
    passable: MAP_STYLES.road.open.color,
    restricted: MAP_STYLES.road.uncertain.color,
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
// Organization detail panel
// -------------------------------------------------------------------

function OrganizationDetail({ data, onClose }) {
  return (
    <>
      <PanelHeader
        icon={Globe}
        title={data.name}
        subtitle={`${data.id} · ${data.organization_type}`}
        onClose={onClose}
        color="#2563eb"
      />
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        <div className="flex items-center gap-2">
          <StatusBadge
            status={data.active ? "active" : "inactive"}
            color={data.active ? "#16a34a" : "#6b7d93"}
          />
          <span className="text-[10px] text-[#6b7d93] capitalize">
            {data.organization_type}
          </span>
        </div>

        {data.description && (
          <div className="text-[12px] text-[#a0aec0] leading-relaxed">
            {data.description}
          </div>
        )}

        {data.published_capabilities && data.published_capabilities.length > 0 && (
          <div className="space-y-2">
            <div className="text-[10px] font-semibold text-[#6b7d93] uppercase tracking-wider">
              Published Capabilities
            </div>
            <div className="flex flex-wrap gap-1">
              {data.published_capabilities.map((cap, i) => (
                <span
                  key={i}
                  className="px-2 py-0.5 rounded text-[10px] font-medium bg-blue-500/10 text-blue-400 border border-blue-500/20"
                >
                  {cap}
                </span>
              ))}
            </div>
          </div>
        )}

        {data.public_contact && Object.keys(data.public_contact).length > 0 && (
          <div className="space-y-1">
            <div className="text-[10px] font-semibold text-[#6b7d93] uppercase tracking-wider">
              Contact
            </div>
            <div className="text-[11px] text-[#a0aec0]">
              {JSON.stringify(data.public_contact)}
            </div>
          </div>
        )}

        <div className="text-[10px] text-[#6b7d93]">
          Joined: {data.created_at && formatDistanceToNow(new Date(data.created_at), { addSuffix: true })}
        </div>
      </div>
    </>
  );
}

// -------------------------------------------------------------------
// Building detail panel
// -------------------------------------------------------------------

function BuildingDetail({ data, onClose }) {
  return (
    <>
      <PanelHeader
        icon={Building2}
        title={data.id || "Building"}
        subtitle="Building"
        onClose={onClose}
        color="#a8a29e"
      />
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        <div className="flex items-center gap-2">
          <StatusBadge
            status={data.in_flood_zone ? "in flood zone" : "clear"}
            color={data.in_flood_zone ? "#dc2626" : "#16a34a"}
          />
        </div>

        {data.district_id && (
          <div className="text-[11px] text-[#a0aec0]">
            District: {data.district_id}
          </div>
        )}

        {data.tags && Object.keys(data.tags).length > 0 && (
          <div className="space-y-2">
            <div className="text-[10px] font-semibold text-[#6b7d93] uppercase tracking-wider">
              Tags
            </div>
            <div className="p-2.5 rounded bg-[#1a2332] border border-[#2a3a4e] space-y-1">
              {Object.entries(data.tags).map(([key, value]) => (
                <div key={key} className="flex items-start gap-2 text-[10px]">
                  <span className="text-[#6b7d93] shrink-0 min-w-[80px]">{key}:</span>
                  <span className="text-[#a0aec0] break-all">{String(value)}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </>
  );
}

// -------------------------------------------------------------------
// Incident empty state panel
// -------------------------------------------------------------------

function IncidentEmptyState({ onClose }) {
  return (
    <>
      <PanelHeader
        icon={Shield}
        title="Incidents"
        subtitle="Operational incidents"
        onClose={onClose}
        color="#d97706"
      />
      <div className="flex-1 overflow-y-auto p-4">
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <div className="w-12 h-12 rounded-full bg-[#1a2332] border border-[#2a3a4e] flex items-center justify-center mb-3">
            <Inbox className="w-5 h-5 text-[#6b7d93]" />
          </div>
          <div className="text-[13px] font-medium text-[#c8d6e5] mb-1">
            No active incidents recorded
          </div>
          <div className="text-[11px] text-[#6b7d93] max-w-[240px] leading-relaxed">
            Incidents will appear here when field teams or the AI coordinator log operational incidents during the response.
          </div>
        </div>
      </div>
    </>
  );
}

// -------------------------------------------------------------------
// Proposal detail panel
// -------------------------------------------------------------------

function ProposalDetail({ data, onClose, onOpenNeed }) {
  const { state, refreshAll, openPanel } = useWorkspace();
  const [proposal, setProposal] = useState(data);
  const [actionBusy, setActionBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (data?.id) {
      fetch(`/api/network/coordination/proposals/${encodeURIComponent(data.id)}`)
        .then((r) => (r.ok ? r.json() : null))
        .then((res) => {
          if (res?.proposal) setProposal(res.proposal);
        })
        .catch(() => {});
    }
  }, [data?.id]);

  const handleSendToOrg = async () => {
    setActionBusy(true);
    setError(null);
    try {
      const resp = await fetch(`/api/network/coordination/proposals/${proposal.id}/send-to-org`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      if (resp.ok) {
        const res = await resp.json();
        setProposal(res.proposal);
        refreshAll();
      } else {
        const err = await resp.json().catch(() => ({}));
        setError(err.error || `Failed to send proposal (${resp.status})`);
      }
    } catch {
      setError("Network error: could not reach server");
    } finally {
      setActionBusy(false);
    }
  };

  const handleDecline = async () => {
    setActionBusy(true);
    setError(null);
    try {
      const resp = await fetch(`/api/network/coordination/proposals/${proposal.id}/decline`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      if (resp.ok) {
        const res = await resp.json();
        setProposal(res.proposal);
        refreshAll();
      } else {
        const err = await resp.json().catch(() => ({}));
        setError(err.error || `Failed to decline proposal (${resp.status})`);
      }
    } catch {
      setError("Network error: could not reach server");
    } finally {
      setActionBusy(false);
    }
  };

  const STATUS_COLORS = {
    PROPOSED: "#4ea8de",
    PENDING_ORG_REVIEW: "#d97706",
    ORG_RECOMMENDED: "#a855f7",
    PUBLISHED: "#16a34a",
    CONFIRMED: "#16a34a",
    DECLINED: "#dc2626",
    EXPIRED: "#6b7d93",
  };

  const statusColor = STATUS_COLORS[proposal.status] || "#6b7d93";

  return (
    <>
      <PanelHeader
        icon={Handshake}
        title={proposal.organization_name || proposal.organization_id || "Proposal"}
        subtitle={`${proposal.id} · ${proposal.proposal_type || "coordination"}`}
        onClose={onClose}
        color={statusColor}
      />
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Status + Need link */}
        <div className="flex items-center justify-between">
          <StatusBadge status={proposal.status} color={statusColor} />
          {proposal.need_id && (
            <button
              onClick={() => {
                const need = state.needs.find((n) => n.id === proposal.need_id);
                if (need) {
                  openPanel("need", proposal.need_id, need);
                } else {
                  onOpenNeed("need", proposal.need_id, { id: proposal.need_id });
                }
              }}
              className="text-[11px] text-[#4ea8de] hover:underline flex items-center gap-1"
            >
              View Need ({proposal.need_id}) →
            </button>
          )}
        </div>

        {error && (
          <div className="px-2.5 py-2 rounded bg-red-500/10 border border-red-500/20 text-[11px] text-red-400">
            {error}
          </div>
        )}

        {/* Summary */}
        <div className="p-3 rounded bg-[#1a2332] border border-[#2a3a4e] space-y-1">
          <div className="text-[10px] font-semibold text-[#6b7d93] uppercase tracking-wider">
            Proposal Summary
          </div>
          <div className="text-[12px] text-[#c8d6e5] leading-relaxed">
            {proposal.summary || "No summary provided"}
          </div>
          {proposal.recommended_action && (
            <div className="text-[11px] text-[#a0aec0] pt-1">
              <span className="text-[#6b7d93]">Recommended: </span>
              {proposal.recommended_action}
            </div>
          )}
        </div>

        {/* Target Org */}
        <div className="p-3 rounded bg-[#1a2332] border border-[#2a3a4e] space-y-1">
          <div className="text-[10px] font-semibold text-[#6b7d93] uppercase tracking-wider">
            Target Organization
          </div>
          <div className="text-[12px] font-medium text-[#c8d6e5]">
            {proposal.organization_name || proposal.organization_id}
          </div>
          <div className="text-[10px] text-[#6b7d93] font-mono">
            ID: {proposal.organization_id}
          </div>
        </div>

        {/* Evidence & Findings */}
        {((proposal.public_evidence && proposal.public_evidence.length > 0) ||
          (proposal.network_findings && proposal.network_findings.length > 0)) && (
          <div className="space-y-2">
            <div className="text-[10px] font-semibold text-[#6b7d93] uppercase tracking-wider">
              Evidence & Findings
            </div>
            <div className="p-2.5 rounded bg-[#1a2332] border border-[#2a3a4e] space-y-1.5">
              {(proposal.public_evidence || []).map((e, idx) => (
                <div key={idx} className="flex items-start gap-1.5 text-[11px] text-[#a0aec0]">
                  <Info className="w-3.5 h-3.5 text-blue-400 mt-0.5 shrink-0" />
                  <span>{e.detail || e.type || JSON.stringify(e)}</span>
                </div>
              ))}
              {(proposal.network_findings || []).map((f, idx) => (
                <div key={idx} className="flex items-start gap-1.5 text-[11px] text-[#a0aec0]">
                  <Info className="w-3.5 h-3.5 text-teal-400 mt-0.5 shrink-0" />
                  <span>{f.detail || f.type || JSON.stringify(f)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Constraints */}
        {proposal.constraints && proposal.constraints.length > 0 && (
          <div className="space-y-1">
            <div className="text-[10px] font-semibold text-[#6b7d93] uppercase tracking-wider">
              Constraints
            </div>
            <div className="p-2.5 rounded bg-[#1a2332] border border-[#2a3a4e] space-y-1">
              {proposal.constraints.map((c, idx) => (
                <div key={idx} className="text-[11px] text-amber-400/80">• {c}</div>
              ))}
            </div>
          </div>
        )}

        {/* Uncertainty */}
        {proposal.uncertainty && proposal.uncertainty.length > 0 && (
          <div className="space-y-1">
            <div className="text-[10px] font-semibold text-[#6b7d93] uppercase tracking-wider">
              Uncertainty
            </div>
            <div className="p-2.5 rounded bg-[#1a2332] border border-[#2a3a4e] space-y-1">
              {proposal.uncertainty.map((u, idx) => (
                <div key={idx} className="text-[11px] text-amber-400/80">⚠ {u}</div>
              ))}
            </div>
          </div>
        )}

        {/* Published Offer Link */}
        {proposal.published_offer_id && (
          <div className="p-3 rounded bg-green-500/10 border border-green-500/25 space-y-1.5">
            <div className="text-[10px] font-semibold text-green-400 uppercase tracking-wider">
              Published Resource Offer
            </div>
            <div className="text-[11px] text-[#c8d6e5]">
              Offer ID: <span className="font-mono text-green-300">{proposal.published_offer_id}</span>
            </div>
            <button
              onClick={() => {
                const offer = state.offers.find((o) => o.id === proposal.published_offer_id);
                openPanel("offer", proposal.published_offer_id, offer || { id: proposal.published_offer_id });
              }}
              className="text-[11px] text-green-400 hover:underline flex items-center gap-1 mt-1"
            >
              Open Offer Details →
            </button>
          </div>
        )}

        {/* Timestamps */}
        <div className="flex items-center justify-between text-[10px] text-[#6b7d93] pt-2 border-t border-[#2a3a4e]">
          <div>
            Created: {proposal.created_at ? formatDistanceToNow(new Date(proposal.created_at), { addSuffix: true }) : "—"}
          </div>
          {proposal.updated_at && (
            <div>
              Updated: {formatDistanceToNow(new Date(proposal.updated_at), { addSuffix: true })}
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="pt-3 border-t border-[#2a3a4e] space-y-2">
          {proposal.status === "PROPOSED" && (
            <button
              onClick={handleSendToOrg}
              disabled={actionBusy}
              className="w-full px-3 py-2 rounded text-[11px] font-semibold bg-teal-500/15 text-teal-400 border border-teal-500/30 hover:bg-teal-500/25 transition-colors disabled:opacity-50"
            >
              {actionBusy ? "Sending…" : "Send to Organization"}
            </button>
          )}

          {proposal.status !== "DECLINED" && proposal.status !== "CONFIRMED" && proposal.status !== "PUBLISHED" && (
            <button
              onClick={handleDecline}
              disabled={actionBusy}
              className="w-full px-3 py-1.5 rounded text-[11px] font-medium text-red-400/80 border border-red-500/20 hover:bg-red-500/10 transition-colors disabled:opacity-50"
            >
              {actionBusy ? "Declining…" : "Decline Proposal"}
            </button>
          )}
        </div>
      </div>
    </>
  );
}

// -------------------------------------------------------------------
// Organizations list panel
// -------------------------------------------------------------------

function OrganizationsListPanel({ onClose }) {
  const { state, openPanel } = useWorkspace();
  const [searchTerm, setSearchTerm] = useState("");
  const orgs = state.organizations || [];

  const filtered = orgs.filter((org) => {
    if (!searchTerm) return true;
    const term = searchTerm.toLowerCase();
    return (
      org.name?.toLowerCase().includes(term) ||
      org.organization_type?.toLowerCase().includes(term) ||
      org.published_capabilities?.some((c) => c.toLowerCase().includes(term))
    );
  });

  return (
    <>
      <PanelHeader
        icon={Globe}
        title="Organizations"
        subtitle={`${filtered.length} registered organization${filtered.length !== 1 ? "s" : ""}`}
        onClose={onClose}
        color="#2563eb"
      />
      <div className="p-3 border-b border-[#2a3a4e]">
        <div className="relative">
          <Search className="w-3.5 h-3.5 text-[#6b7d93] absolute left-2.5 top-2.5" />
          <input
            type="text"
            placeholder="Filter organizations or capabilities..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 rounded bg-[#1a2332] border border-[#2a3a4e] text-[11px] text-[#c8d6e5] placeholder:text-[#6b7d93] outline-none focus:border-[#3a5a7e]"
          />
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-3 space-y-2.5">
        {filtered.length === 0 ? (
          <div className="text-center py-8 text-[11px] text-[#6b7d93]">
            No organizations found
          </div>
        ) : (
          filtered.map((org) => (
            <div
              key={org.id}
              onClick={() => openPanel("organization", org.id, org)}
              className="p-3 rounded bg-[#1a2332] border border-[#2a3a4e] hover:border-[#3a5a7e] cursor-pointer transition-colors space-y-1.5"
            >
              <div className="flex items-center justify-between">
                <div className="text-[12px] font-semibold text-[#c8d6e5]">{org.name}</div>
                <StatusBadge
                  status={org.active ? "active" : "inactive"}
                  color={org.active ? "#16a34a" : "#6b7d93"}
                />
              </div>
              <div className="text-[10px] text-[#6b7d93] capitalize">
                Type: {org.organization_type || "NGO"}
              </div>
              {org.description && (
                <div className="text-[11px] text-[#a0aec0] line-clamp-2 leading-relaxed">
                  {org.description}
                </div>
              )}
              {org.published_capabilities && org.published_capabilities.length > 0 && (
                <div className="flex flex-wrap gap-1 pt-1">
                  {org.published_capabilities.map((cap, i) => (
                    <span
                      key={i}
                      className="px-1.5 py-0.5 rounded text-[9px] font-medium bg-blue-500/10 text-blue-400 border border-blue-500/20"
                    >
                      {cap}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </>
  );
}

// -------------------------------------------------------------------
// Field reports list panel
// -------------------------------------------------------------------

function ReportsListPanel({ onClose }) {
  const { state, openPanel, setMapCenter } = useWorkspace();
  const reports = state.fieldReports || [];

  const filtered = reports.filter((r) => {
    if (state.filters.urgency && r.urgency && r.urgency !== state.filters.urgency) return false;
    if (state.filters.status && r.status && r.status !== state.filters.status) return false;
    return true;
  });

  return (
    <>
      <PanelHeader
        icon={FileText}
        title="Field Reports"
        subtitle={`${filtered.length} report${filtered.length !== 1 ? "s" : ""}`}
        onClose={onClose}
        color="#4f46e5"
      />
      <div className="p-3 border-b border-[#2a3a4e] flex items-center justify-between">
        <div className="text-[10px] text-[#6b7d93]">
          {state.filters.district ? `District: ${state.filters.district}` : "All Districts"}
        </div>
        <button
          onClick={() => openPanel("createReport")}
          className="px-2.5 py-1 rounded text-[11px] font-medium bg-indigo-500/15 text-indigo-400 border border-indigo-500/30 hover:bg-indigo-500/25 transition-colors"
        >
          + Submit Report
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-3 space-y-2.5">
        {filtered.length === 0 ? (
          <div className="text-center py-8 text-[11px] text-[#6b7d93]">
            No field reports match current filters
          </div>
        ) : (
          filtered.map((report) => {
            const verified = report.verified || report.source === "field_intelligence_text";
            return (
              <div
                key={report.id || report.report_id}
                onClick={() => {
                  if (report.lat && report.lon) {
                    setMapCenter([report.lat, report.lon], 13);
                  }
                  openPanel("report", report.id || report.report_id, report);
                }}
                className="p-3 rounded bg-[#1a2332] border border-[#2a3a4e] hover:border-[#3a5a7e] cursor-pointer transition-colors space-y-1.5"
              >
                <div className="flex items-center justify-between">
                  <span className="text-[12px] font-medium text-[#c8d6e5]">
                    {report.title || `${report.people_count || "Field"} People Reported`}
                  </span>
                  <StatusBadge
                    status={verified ? "verified" : "unverified"}
                    color={verified ? "#16a34a" : "#d97706"}
                  />
                </div>
                <div className="text-[11px] text-[#a0aec0] line-clamp-2">
                  {report.note || report.raw_text || (report.needs ? `Needs: ${report.needs.join(", ")}` : "No description")}
                </div>
                <div className="flex items-center justify-between text-[10px] text-[#6b7d93] pt-1">
                  <span>Source: {report.source || "field"}</span>
                  {report.timestamp && (
                    <span>{_timeAgo(report.timestamp)}</span>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    </>
  );
}

// -------------------------------------------------------------------
// Active overrides list panel
// -------------------------------------------------------------------

function OverridesListPanel({ onClose }) {
  const { state, openPanel, setMapCenter } = useWorkspace();
  const overrides = state.overrides || {};
  const entries = Object.entries(overrides).map(([key, val]) => ({
    target_id: key,
    ...val,
  }));

  return (
    <>
      <PanelHeader
        icon={Zap}
        title="Active Overrides"
        subtitle={`${entries.length} override${entries.length !== 1 ? "s" : ""}`}
        onClose={onClose}
        color="#f59e0b"
      />
      <div className="flex-1 overflow-y-auto p-3 space-y-2.5">
        {entries.length === 0 ? (
          <div className="text-center py-8 text-[11px] text-[#6b7d93]">
            No manual overrides active
          </div>
        ) : (
          entries.map((ov, idx) => (
            <div
              key={idx}
              onClick={() => {
                const facility = state.medicalFacilities.find((f) => f.name === ov.target_id || f.id === ov.target_id);
                if (facility) {
                  if (facility.lat && facility.lon) setMapCenter([facility.lat, facility.lon], 14);
                  openPanel("facility", facility.id, facility);
                }
              }}
              className="p-3 rounded bg-[#1a2332] border border-[#2a3a4e] hover:border-[#3a5a7e] cursor-pointer transition-colors space-y-1.5"
            >
              <div className="flex items-center justify-between">
                <span className="text-[12px] font-medium text-[#c8d6e5]">{ov.target_id}</span>
                <StatusBadge
                  status={ov.override_status || ov.status || "OVERRIDE"}
                  color="#f59e0b"
                />
              </div>
              {ov.reason && (
                <div className="text-[11px] text-[#a0aec0]">
                  Reason: {ov.reason}
                </div>
              )}
              <div className="flex items-center justify-between text-[10px] text-[#6b7d93] pt-1">
                <span>By: {ov.actor || "Operator"}</span>
                {ov.timestamp && <span>{_timeAgo(ov.timestamp)}</span>}
              </div>
            </div>
          ))
        )}
      </div>
    </>
  );
}

// -------------------------------------------------------------------
// Needs list panel
// -------------------------------------------------------------------

function NeedsListPanel({ onClose }) {
  const { state, openPanel, setMapCenter } = useWorkspace();
  const needs = state.needs || [];

  const filtered = needs.filter((n) => {
    if (state.filters.district && n.district_id !== state.filters.district) return false;
    if (state.filters.urgency && n.urgency !== state.filters.urgency) return false;
    if (state.filters.status && n.status !== state.filters.status) return false;
    return true;
  });

  const urgencyColor = {
    critical: "#dc2626",
    high: "#d97706",
    medium: "#eab308",
    low: "#16a34a",
  };

  return (
    <>
      <PanelHeader
        icon={AlertTriangle}
        title="Needs Directory"
        subtitle={`${filtered.length} need${filtered.length !== 1 ? "s" : ""}`}
        onClose={onClose}
        color="#dc2626"
      />
      <div className="p-3 border-b border-[#2a3a4e] flex items-center justify-between">
        <div className="text-[10px] text-[#6b7d93]">
          {state.filters.urgency ? `Urgency: ${state.filters.urgency}` : "All Urgencies"} · {state.filters.status ? `Status: ${state.filters.status}` : "All Statuses"}
        </div>
        <button
          onClick={() => openPanel("createNeed")}
          className="px-2.5 py-1 rounded text-[11px] font-medium bg-red-500/15 text-red-400 border border-red-500/30 hover:bg-red-500/25 transition-colors"
        >
          + Log Need
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-3 space-y-2.5">
        {filtered.length === 0 ? (
          <div className="text-center py-8 text-[11px] text-[#6b7d93]">
            No needs match current filters
          </div>
        ) : (
          filtered.map((need) => (
            <div
              key={need.id}
              onClick={() => {
                if (need.lat && need.lon) setMapCenter([need.lat, need.lon], 13);
                openPanel("need", need.id, need);
              }}
              className="p-3 rounded bg-[#1a2332] border border-[#2a3a4e] hover:border-[#3a5a7e] cursor-pointer transition-colors space-y-1.5"
            >
              <div className="flex items-center justify-between">
                <span className="text-[12px] font-medium text-[#c8d6e5]">{need.title || need.need_type}</span>
                <StatusBadge
                  status={need.urgency || "normal"}
                  color={urgencyColor[need.urgency] || "#6b7d93"}
                />
              </div>
              <div className="text-[11px] text-[#a0aec0]">
                {need.people_affected ? `${need.people_affected} people affected` : (need.description || need.need_type)}
              </div>
              <div className="flex items-center justify-between text-[10px] text-[#6b7d93] pt-1">
                <span>📍 {need.location_name || need.district_id || "Unspecified"}</span>
                <span className="capitalize">Status: {need.status}</span>
              </div>
            </div>
          ))
        )}
      </div>
    </>
  );
}

// -------------------------------------------------------------------
// Offers list panel
// -------------------------------------------------------------------

function OffersListPanel({ onClose }) {
  const { state, openPanel, setMapCenter } = useWorkspace();
  const offers = state.offers || [];

  const filtered = offers.filter((o) => {
    if (state.filters.district && o.district_id !== state.filters.district) return false;
    return true;
  });

  return (
    <>
      <PanelHeader
        icon={Package}
        title="Resource Offers"
        subtitle={`${filtered.length} offer${filtered.length !== 1 ? "s" : ""}`}
        onClose={onClose}
        color="#0d9488"
      />
      <div className="p-3 border-b border-[#2a3a4e] flex items-center justify-between">
        <div className="text-[10px] text-[#6b7d93]">
          {state.filters.district ? `District: ${state.filters.district}` : "All Districts"}
        </div>
        <button
          onClick={() => openPanel("createOffer")}
          className="px-2.5 py-1 rounded text-[11px] font-medium bg-teal-500/15 text-teal-400 border border-teal-500/30 hover:bg-teal-500/25 transition-colors"
        >
          + Submit Offer
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-3 space-y-2.5">
        {filtered.length === 0 ? (
          <div className="text-center py-8 text-[11px] text-[#6b7d93]">
            No resource offers match current filters
          </div>
        ) : (
          filtered.map((offer) => (
            <div
              key={offer.id}
              onClick={() => {
                if (offer.lat && offer.lon) setMapCenter([offer.lat, offer.lon], 13);
                openPanel("offer", offer.id, offer);
              }}
              className="p-3 rounded bg-[#1a2332] border border-[#2a3a4e] hover:border-[#3a5a7e] cursor-pointer transition-colors space-y-1.5"
            >
              <div className="flex items-center justify-between">
                <span className="text-[12px] font-medium text-[#c8d6e5]">{offer.resource_type}</span>
                <StatusBadge
                  status={offer.status || "OFFERED"}
                  color="#0d9488"
                />
              </div>
              <div className="text-[11px] text-[#a0aec0]">
                Quantity: {offer.quantity} {offer.unit}
              </div>
              <div className="flex items-center justify-between text-[10px] text-[#6b7d93] pt-1">
                <span>Org: {offer.organization_name || offer.organization_id || "NGO"}</span>
                <span>📍 {offer.location_name || offer.district_id || "—"}</span>
              </div>
            </div>
          ))
        )}
      </div>
    </>
  );
}

// -------------------------------------------------------------------
// Operations list panel
// -------------------------------------------------------------------

function OperationsListPanel({ onClose }) {
  const { state, openPanel, setMapCenter } = useWorkspace();
  const operations = state.operations || [];

  const filtered = operations.filter((op) => {
    if (state.filters.district && op.district_id !== state.filters.district) return false;
    if (state.filters.status) {
      const statusMap = { OPEN: "PLANNING", RESPONDING: "ACTIVE", RESOLVED: "COMPLETED" };
      const targetStatus = statusMap[state.filters.status] || state.filters.status;
      if (op.status !== targetStatus) return false;
    }
    return true;
  });

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
        icon={Shield}
        title="Operations"
        subtitle={`${filtered.length} operation${filtered.length !== 1 ? "s" : ""}`}
        onClose={onClose}
        color="#2563eb"
      />
      <div className="p-3 border-b border-[#2a3a4e] flex items-center justify-between">
        <div className="text-[10px] text-[#6b7d93]">
          {state.filters.status ? `Status: ${state.filters.status}` : "All Operations"}
        </div>
        <button
          onClick={() => openPanel("createOperation")}
          className="px-2.5 py-1 rounded text-[11px] font-medium bg-blue-500/15 text-blue-400 border border-blue-500/30 hover:bg-blue-500/25 transition-colors"
        >
          + Launch Operation
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-3 space-y-2.5">
        {filtered.length === 0 ? (
          <div className="text-center py-8 text-[11px] text-[#6b7d93]">
            No operations match current filters
          </div>
        ) : (
          filtered.map((op) => (
            <div
              key={op.id}
              onClick={() => {
                if (op.lat && op.lon) setMapCenter([op.lat, op.lon], 13);
                openPanel("operation", op.id, op);
              }}
              className="p-3 rounded bg-[#1a2332] border border-[#2a3a4e] hover:border-[#3a5a7e] cursor-pointer transition-colors space-y-1.5"
            >
              <div className="flex items-center justify-between">
                <span className="text-[12px] font-medium text-[#c8d6e5]">{op.name || op.operation_type}</span>
                <StatusBadge
                  status={op.status || "PLANNING"}
                  color={statusColor[op.status] || "#6b7280"}
                />
              </div>
              <div className="text-[11px] text-[#a0aec0]">
                Type: {op.operation_type}
              </div>
              <div className="flex items-center justify-between text-[10px] text-[#6b7d93] pt-1">
                <span>📍 {op.location_name || op.district_id || "—"}</span>
                {op.assigned_team && <span>Team: {op.assigned_team}</span>}
              </div>
            </div>
          ))
        )}
      </div>
    </>
  );
}

// -------------------------------------------------------------------
// Main ContextPanel
// -------------------------------------------------------------------

export default function ContextPanel() {
  const { state, closePanel, openPanel, clearPinpoint } = useWorkspace();

  const handleClosePanel = () => {
    clearPinpoint();
    closePanel();
  };

  if (!state.panelOpen) return null;

  const panelWidth = 384;

  return (
    <div
      className="bg-[#0f1419] border-l border-[#2a3a4e] flex flex-col shrink-0 overflow-hidden fade-in"
      style={{ width: panelWidth }}
    >
      {state.panelType === "need" && state.panelData && (
        <NeedDetail
          data={state.panelData}
          onClose={handleClosePanel}
          onOpenMatch={openPanel}
        />
      )}
      {state.panelType === "proposal" && state.panelData && (
        <ProposalDetail
          data={state.panelData}
          onClose={closePanel}
          onOpenNeed={openPanel}
        />
      )}
      {state.panelType === "operation" && state.panelData && (
        <OperationDetail data={state.panelData} onClose={closePanel} onOpenNeed={openPanel} />
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
      {state.panelType === "organization" && state.panelData && (
        <OrganizationDetail data={state.panelData} onClose={closePanel} />
      )}
      {state.panelType === "organizationsList" && (
        <OrganizationsListPanel onClose={closePanel} />
      )}
      {state.panelType === "reportsList" && (
        <ReportsListPanel onClose={closePanel} />
      )}
      {state.panelType === "overridesList" && (
        <OverridesListPanel onClose={closePanel} />
      )}
      {state.panelType === "needsList" && (
        <NeedsListPanel onClose={closePanel} />
      )}
      {state.panelType === "offersList" && (
        <OffersListPanel onClose={closePanel} />
      )}
      {state.panelType === "operationsList" && (
        <OperationsListPanel onClose={closePanel} />
      )}
      {state.panelType === "building" && state.panelData && (
        <BuildingDetail data={state.panelData} onClose={closePanel} />
      )}
      {state.panelType === "incident" && (
        <IncidentEmptyState onClose={handleClosePanel} />
      )}
      {state.panelType === "createNeed" && (
        <CreateNeedForm onClose={handleClosePanel} />
      )}
      {state.panelType === "createReport" && (
        <CreateReportForm defaultData={state.panelData} onClose={handleClosePanel} />
      )}
      {state.panelType === "createOffer" && (
        <CreateOfferForm onClose={handleClosePanel} />
      )}
      {state.panelType === "createOperation" && (
        <CreateOperationForm onClose={handleClosePanel} />
      )}
      {state.panelType === "aiAnalysis" && (
        <AIAnalysisPanel onClose={handleClosePanel} />
      )}
    </div>
  );
}
