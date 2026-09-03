import { useState, useEffect, useCallback } from "react";
import {
  Shield, Package, Users, Map, Zap, AlertTriangle, Plus,
  ChevronRight, ExternalLink, Edit3, Trash2, CheckCircle,
  Clock, MapPin, Brain, Bell, Search,
} from "lucide-react";
import { useWorkspace } from "../../lib/workspaceContext";
import { cn } from "../../lib/utils";
import { formatDistanceToNow } from "date-fns";

// ---------------------------------------------------------------------------
// Mock org ID — in production this comes from auth
// ---------------------------------------------------------------------------
const CURRENT_ORG_ID = "org_demo";

// ---------------------------------------------------------------------------
// Organization Summary Panel
// ---------------------------------------------------------------------------

function OrgSummary({ summary, onRefresh }) {
  if (!summary) return null;

  const s = summary.summary || {};
  return (
    <div className="space-y-4">
      {/* Profile */}
      <div className="p-3 rounded bg-[#1a2332] border border-[#2a3a4e]">
        <div className="flex items-center gap-2 mb-2">
          <Shield className="w-4 h-4 text-[#4ea8de]" />
          <span className="text-[13px] font-semibold text-[#c8d6e5]">
            {summary.profile?.name || CURRENT_ORG_ID}
          </span>
        </div>
        {summary.profile?.description && (
          <div className="text-[11px] text-[#a0aec0]">{summary.profile.description}</div>
        )}
      </div>

      {/* Private State Summary */}
      <div className="space-y-2">
        <div className="text-[9px] font-semibold text-[#6b7d93] uppercase tracking-wider px-1">
          PRIVATE STATE
        </div>
        <div className="grid grid-cols-2 gap-2">
          <StatCard label="Resources" value={s.total_resources || 0} detail={`${s.available_resources || 0} available`} color="#0d9488" />
          <StatCard label="Teams" value={s.total_teams || 0} detail={`${s.available_teams || 0} available`} color="#2563eb" />
          <StatCard label="Missions" value={s.active_missions || 0} detail="active" color="#7c3aed" />
          <StatCard label="Published" value={s.published_offers || 0} detail="offers" color="#16a34a" />
        </div>
      </div>

      {/* Network State */}
      <div className="space-y-2">
        <div className="text-[9px] font-semibold text-[#6b7d93] uppercase tracking-wider px-1">
          NETWORK
        </div>
        <div className="grid grid-cols-2 gap-2">
          <StatCard label="Open Needs" value={s.network_requests || 0} detail="in network" color="#dc2626" />
          <StatCard label="My Operations" value={s.active_operations || 0} detail="active" color="#2563eb" />
        </div>
      </div>
    </div>
  );
}

function StatCard({ label, value, detail, color }) {
  return (
    <div className="p-2.5 rounded bg-[#1a2332] border border-[#2a3a4e]">
      <div className="text-[10px] text-[#6b7d93] uppercase tracking-wider">{label}</div>
      <div className="flex items-baseline gap-1.5 mt-1">
        <span className="text-[18px] font-bold font-mono" style={{ color }}>{value}</span>
        <span className="text-[9px] text-[#6b7d93]">{detail}</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Private Resources Panel
// ---------------------------------------------------------------------------

function PrivateResources({ orgId, onRefresh }) {
  const [resources, setResources] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);

  useEffect(() => {
    fetch(`/api/orgs/${orgId}/resources`)
      .then(r => r.json())
      .then(data => setResources(data.resources || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [orgId]);

  const handleAdd = async (resource) => {
    try {
      const resp = await fetch(`/api/orgs/${orgId}/resources`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(resource),
      });
      if (resp.ok) {
        const data = await resp.json();
        setResources([...resources, data.resource]);
        setShowAdd(false);
      }
    } catch (err) {
      console.error("Failed to add resource:", err);
    }
  };

  const handleStatusChange = async (resourceId, newStatus) => {
    try {
      const resp = await fetch(`/api/orgs/${orgId}/resources/${resourceId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: newStatus }),
      });
      if (resp.ok) {
        setResources(resources.map(r =>
          r.id === resourceId ? { ...r, status: newStatus } : r
        ));
      }
    } catch (err) {
      console.error("Failed to update resource:", err);
    }
  };

  const STATUS_COLORS = {
    available: "#16a34a",
    committed: "#d97706",
    deployed: "#2563eb",
    unavailable: "#6b7280",
    in_transit: "#0d9488",
  };

  if (loading) return <div className="text-[11px] text-[#6b7d93] p-2">Loading resources...</div>;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between px-1">
        <div className="text-[9px] font-semibold text-[#6b7d93] uppercase tracking-wider">
          PRIVATE RESOURCES ({resources.length})
        </div>
        <button
          onClick={() => setShowAdd(!showAdd)}
          className="text-[9px] text-[#4ea8de] hover:text-[#6bb8f0] flex items-center gap-1"
        >
          <Plus className="w-3 h-3" /> Add
        </button>
      </div>

      {/* Add form */}
      {showAdd && (
        <AddResourceForm onSubmit={handleAdd} onCancel={() => setShowAdd(false)} />
      )}

      {/* Resource list */}
      {resources.length === 0 ? (
        <div className="p-3 rounded bg-[#1a2332] border border-[#2a3a4e] text-center">
          <Package className="w-5 h-5 text-[#4a5568] mx-auto mb-1" />
          <div className="text-[11px] text-[#6b7d93]">No private resources</div>
          <div className="text-[9px] text-[#4a5568]">Add resources to your inventory</div>
        </div>
      ) : (
        <div className="space-y-1">
          {resources.map(r => (
            <div
              key={r.id}
              className="flex items-center gap-2 px-2.5 py-2 rounded bg-[#1a2332] border border-[#2a3a4e] group"
            >
              <Package className="w-3.5 h-3.5 shrink-0" style={{ color: STATUS_COLORS[r.status] || "#6b7d93" }} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="text-[11px] text-[#c8d6e5] font-medium">{r.type || r.resource_type}</span>
                  <span className="text-[10px] font-mono text-[#6b7d93]">{r.quantity} {r.unit}</span>
                </div>
                <div className="flex items-center gap-2 text-[9px] text-[#6b7d93]">
                  <span style={{ color: STATUS_COLORS[r.status] }}>{r.status}</span>
                  {r.location && <span>· {r.location}</span>}
                </div>
              </div>
              <select
                value={r.status}
                onChange={(e) => handleStatusChange(r.id, e.target.value)}
                className="text-[9px] bg-[#0f1419] border border-[#2a3a4e] rounded px-1 py-0.5 text-[#c8d6e5] outline-none"
              >
                <option value="available">available</option>
                <option value="committed">committed</option>
                <option value="deployed">deployed</option>
                <option value="unavailable">unavailable</option>
              </select>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function AddResourceForm({ onSubmit, onCancel }) {
  const [type, setType] = useState("");
  const [quantity, setQuantity] = useState(1);
  const [unit, setUnit] = useState("units");
  const [location, setLocation] = useState("");

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!type.trim()) return;
    onSubmit({
      type: type.trim(),
      resource_type: type.trim(),
      quantity: parseInt(quantity) || 1,
      unit,
      location: location.trim() || null,
      status: "available",
    });
  };

  return (
    <form onSubmit={handleSubmit} className="p-2.5 rounded bg-[#1a2332] border border-[#2a3a4e] space-y-2">
      <div className="text-[10px] font-semibold text-[#c8d6e5]">Add Resource</div>
      <input
        value={type}
        onChange={e => setType(e.target.value)}
        placeholder="Type (e.g. water, boat, medical)"
        className="w-full px-2 py-1.5 rounded border border-[#2a3a4e] bg-[#0f1419] text-[11px] text-[#c8d6e5] placeholder:text-[#6b7d93] outline-none"
      />
      <div className="flex gap-2">
        <input
          type="number"
          value={quantity}
          onChange={e => setQuantity(e.target.value)}
          className="flex-1 px-2 py-1.5 rounded border border-[#2a3a4e] bg-[#0f1419] text-[11px] text-[#c8d6e5] outline-none"
        />
        <select
          value={unit}
          onChange={e => setUnit(e.target.value)}
          className="px-2 py-1.5 rounded border border-[#2a3a4e] bg-[#0f1419] text-[11px] text-[#c8d6e5] outline-none"
        >
          <option value="units">units</option>
          <option value="kg">kg</option>
          <option value="liters">liters</option>
          <option value="people">people</option>
          <option value="kits">kits</option>
        </select>
      </div>
      <input
        value={location}
        onChange={e => setLocation(e.target.value)}
        placeholder="Location (optional)"
        className="w-full px-2 py-1.5 rounded border border-[#2a3a4e] bg-[#0f1419] text-[11px] text-[#c8d6e5] placeholder:text-[#6b7d93] outline-none"
      />
      <div className="flex gap-2">
        <button type="submit" className="flex-1 px-2 py-1.5 rounded text-[10px] font-medium bg-green-500/15 text-green-400 border border-green-500/30 hover:bg-green-500/25">
          Add
        </button>
        <button type="button" onClick={onCancel} className="px-2 py-1.5 rounded text-[10px] text-[#6b7d93] border border-[#2a3a4e] hover:bg-[#1a2332]">
          Cancel
        </button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Private Teams Panel
// ---------------------------------------------------------------------------

function PrivateTeams({ orgId }) {
  const [teams, setTeams] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);

  useEffect(() => {
    fetch(`/api/orgs/${orgId}/teams`)
      .then(r => r.json())
      .then(data => setTeams(data.teams || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [orgId]);

  const handleAdd = async (team) => {
    try {
      const resp = await fetch(`/api/orgs/${orgId}/teams`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(team),
      });
      if (resp.ok) {
        const data = await resp.json();
        setTeams([...teams, data.team]);
        setShowAdd(false);
      }
    } catch (err) {
      console.error("Failed to add team:", err);
    }
  };

  if (loading) return <div className="text-[11px] text-[#6b7d93] p-2">Loading teams...</div>;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between px-1">
        <div className="text-[9px] font-semibold text-[#6b7d93] uppercase tracking-wider">
          PRIVATE TEAMS ({teams.length})
        </div>
        <button
          onClick={() => setShowAdd(!showAdd)}
          className="text-[9px] text-[#4ea8de] hover:text-[#6bb8f0] flex items-center gap-1"
        >
          <Plus className="w-3 h-3" /> Add
        </button>
      </div>

      {showAdd && (
        <AddTeamForm onSubmit={handleAdd} onCancel={() => setShowAdd(false)} />
      )}

      {teams.length === 0 ? (
        <div className="p-3 rounded bg-[#1a2332] border border-[#2a3a4e] text-center">
          <Users className="w-5 h-5 text-[#4a5568] mx-auto mb-1" />
          <div className="text-[11px] text-[#6b7d93]">No private teams</div>
        </div>
      ) : (
        <div className="space-y-1">
          {teams.map(t => (
            <div key={t.id} className="px-2.5 py-2 rounded bg-[#1a2332] border border-[#2a3a4e]">
              <div className="flex items-center gap-2">
                <Users className="w-3.5 h-3.5 text-blue-400 shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="text-[11px] text-[#c8d6e5] font-medium">{t.name}</div>
                  <div className="flex items-center gap-2 text-[9px] text-[#6b7d93]">
                    <span style={{ color: t.status === "available" ? "#16a34a" : "#d97706" }}>{t.status}</span>
                    {t.members && <span>· {t.members.length} members</span>}
                    {t.location && <span>· {t.location}</span>}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function AddTeamForm({ onSubmit, onCancel }) {
  const [name, setName] = useState("");
  const [location, setLocation] = useState("");

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!name.trim()) return;
    onSubmit({ name: name.trim(), location: location.trim() || null, members: [], status: "available" });
  };

  return (
    <form onSubmit={handleSubmit} className="p-2.5 rounded bg-[#1a2332] border border-[#2a3a4e] space-y-2">
      <div className="text-[10px] font-semibold text-[#c8d6e5]">Add Team</div>
      <input
        value={name}
        onChange={e => setName(e.target.value)}
        placeholder="Team name"
        className="w-full px-2 py-1.5 rounded border border-[#2a3a4e] bg-[#0f1419] text-[11px] text-[#c8d6e5] placeholder:text-[#6b7d93] outline-none"
      />
      <input
        value={location}
        onChange={e => setLocation(e.target.value)}
        placeholder="Location (optional)"
        className="w-full px-2 py-1.5 rounded border border-[#2a3a4e] bg-[#0f1419] text-[11px] text-[#c8d6e5] placeholder:text-[#6b7d93] outline-none"
      />
      <div className="flex gap-2">
        <button type="submit" className="flex-1 px-2 py-1.5 rounded text-[10px] font-medium bg-green-500/15 text-green-400 border border-green-500/30">Add</button>
        <button type="button" onClick={onCancel} className="px-2 py-1.5 rounded text-[10px] text-[#6b7d93] border border-[#2a3a4e]">Cancel</button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Private Missions Panel
// ---------------------------------------------------------------------------

function PrivateMissions({ orgId }) {
  const [missions, setMissions] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`/api/orgs/${orgId}/missions`)
      .then(r => r.json())
      .then(data => setMissions(data.missions || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [orgId]);

  if (loading) return <div className="text-[11px] text-[#6b7d93] p-2">Loading missions...</div>;

  const STATUS_COLORS = {
    PLANNING: "#2563eb",
    READY: "#d97706",
    ACTIVE: "#16a34a",
    COMPLETED: "#6b7280",
  };

  return (
    <div className="space-y-2">
      <div className="text-[9px] font-semibold text-[#6b7d93] uppercase tracking-wider px-1">
        PRIVATE MISSIONS ({missions.length})
      </div>

      {missions.length === 0 ? (
        <div className="p-3 rounded bg-[#1a2332] border border-[#2a3a4e] text-center">
          <Map className="w-5 h-5 text-[#4a5568] mx-auto mb-1" />
          <div className="text-[11px] text-[#6b7d93]">No active missions</div>
        </div>
      ) : (
        <div className="space-y-1">
          {missions.map(m => (
            <div key={m.id} className="px-2.5 py-2 rounded bg-[#1a2332] border border-[#2a3a4e]">
              <div className="flex items-center gap-2">
                <Map className="w-3.5 h-3.5 shrink-0" style={{ color: STATUS_COLORS[m.status] || "#6b7d93" }} />
                <div className="flex-1 min-w-0">
                  <div className="text-[11px] text-[#c8d6e5] font-medium">{m.name}</div>
                  <div className="text-[9px] text-[#6b7d93]">
                    <span style={{ color: STATUS_COLORS[m.status] }}>{m.status}</span>
                    {m.linked_need_id && <span> · Need: {m.linked_need_id}</span>}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// NGO Agent Panel
// ---------------------------------------------------------------------------

function NGOAgentPanel({ orgId, summary }) {
  const [situation, setSituation] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedNeed, setSelectedNeed] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);
  const { state, openPanel } = useWorkspace();

  // Fetch situation summary
  useEffect(() => {
    fetch(`/api/orgs/${orgId}/agent/situation`)
      .then(r => r.json())
      .then(data => setSituation(data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [orgId]);

  const handleAnalyzeNeed = async (need) => {
    setSelectedNeed(need);
    setAnalyzing(true);
    setAnalysis(null);
    try {
      const resp = await fetch(`/api/orgs/${orgId}/agent/analyze-need`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ need }),
      });
      if (resp.ok) {
        const data = await resp.json();
        setAnalysis(data);
      }
    } catch (err) {
      console.error("Analysis failed:", err);
    } finally {
      setAnalyzing(false);
    }
  };

  const handlePublish = async (publication) => {
    try {
      const resp = await fetch(`/api/orgs/${orgId}/publish-offer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(publication),
      });
      if (resp.ok) {
        setAnalysis(null);
        setSelectedNeed(null);
      }
    } catch (err) {
      console.error("Publish failed:", err);
    }
  };

  if (loading) return <div className="text-[11px] text-[#6b7d93] p-2">Loading AI context...</div>;

  return (
    <div className="space-y-3">
      {/* Situation Summary */}
      <div className="p-3 rounded bg-[#1a2332] border border-[#2a3a4e]">
        <div className="flex items-center gap-2 mb-2">
          <Brain className="w-4 h-4 text-[#7c3aed]" />
          <span className="text-[12px] font-semibold text-[#c8d6e5]">NGO AI</span>
          <div className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
        </div>

        {situation && (
          <div className="space-y-2">
            <div className="text-[9px] font-semibold text-[#6b7d93] uppercase tracking-wider">
              MY SITUATION
            </div>
            <div className="grid grid-cols-2 gap-1.5 text-[10px]">
              <div className="text-[#a0aec0]">Resources: <span className="text-[#c8d6e5] font-mono">{situation.private_summary?.available_resources || 0} available</span></div>
              <div className="text-[#a0aec0]">Teams: <span className="text-[#c8d6e5] font-mono">{situation.private_summary?.available_teams || 0} available</span></div>
              <div className="text-[#a0aec0]">Missions: <span className="text-[#c8d6e5] font-mono">{situation.private_summary?.active_missions || 0} active</span></div>
              <div className="text-[#a0aec0]">Network Needs: <span className="text-[#c8d6e5] font-mono">{situation.network_summary?.open_needs || 0}</span></div>
            </div>

            {/* Attention items */}
            {situation.attention && situation.attention.length > 0 && (
              <div className="mt-2 space-y-1">
                <div className="text-[9px] font-semibold text-[#6b7d93] uppercase tracking-wider">
                  ATTENTION
                </div>
                {situation.attention.map((item, i) => (
                  <div key={i} className="flex items-start gap-2 text-[10px]">
                    <span className="shrink-0">•</span>
                    <span className="text-[#a0aec0]">{item.detail}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Quick Analysis */}
      <div className="p-3 rounded bg-[#1a2332] border border-[#2a3a4e]">
        <div className="text-[9px] font-semibold text-[#6b7d93] uppercase tracking-wider mb-2">
          QUICK ANALYSIS
        </div>
        <div className="text-[10px] text-[#a0aec0] mb-2">
          Select a network need to analyze with your private context:
        </div>
        <div className="space-y-1">
          {state.needs.filter(n => n.status === "OPEN").slice(0, 3).map(need => (
            <button
              key={need.id}
              onClick={() => handleAnalyzeNeed(need)}
              disabled={analyzing}
              className="w-full flex items-center gap-2 px-2 py-1.5 rounded bg-[#0f1419] border border-[#2a3a4e] hover:border-[#7c3aed]/30 transition-colors text-left"
            >
              <AlertTriangle className="w-3 h-3 text-red-400 shrink-0" />
              <span className="text-[10px] text-[#c8d6e5] flex-1 truncate">{need.title || need.need_type}</span>
              <span className="text-[9px] text-[#6b7d93]">{need.urgency}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Analysis Result */}
      {analyzing && (
        <div className="p-3 rounded bg-[#1a2332] border border-[#2a3a4e] text-center">
          <div className="text-[11px] text-[#7c3aed] animate-pulse">Analyzing...</div>
        </div>
      )}

      {analysis && !analyzing && (
        <div className="p-3 rounded bg-[#1a2332] border border-[#7c3aed]/30 space-y-2">
          <div className="flex items-center gap-2">
            <Brain className="w-3.5 h-3.5 text-[#7c3aed]" />
            <span className="text-[11px] font-semibold text-[#c8d6e5]">Analysis: {analysis.need_title}</span>
          </div>

          {/* Recommendation */}
          <div className="p-2 rounded bg-[#0f1419] border border-[#2a3a4e]">
            <div className="text-[9px] font-semibold text-[#6b7d93] uppercase tracking-wider mb-1">RECOMMENDATION</div>
            <div className="text-[11px] text-[#c8d6e5]">{analysis.recommendation}</div>
          </div>

          {/* Why */}
          <div className="p-2 rounded bg-[#0f1419] border border-[#2a3a4e]">
            <div className="text-[9px] font-semibold text-[#6b7d93] uppercase tracking-wider mb-1">WHY</div>
            <div className="text-[10px] text-[#a0aec0]">{analysis.why}</div>
          </div>

          {/* Private Factors */}
          {analysis.private_factors && analysis.private_factors.length > 0 && (
            <div className="p-2 rounded bg-[#0f1419] border border-[#2a3a4e]">
              <div className="text-[9px] font-semibold text-[#6b7d93] uppercase tracking-wider mb-1">PRIVATE FACTORS</div>
              <div className="space-y-0.5">
                {analysis.private_factors.map((f, i) => (
                  <div key={i} className="text-[10px] text-[#a0aec0]">• {f}</div>
                ))}
              </div>
            </div>
          )}

          {/* Uncertainty */}
          {analysis.uncertainty && analysis.uncertainty.length > 0 && (
            <div className="p-2 rounded bg-amber-500/5 border border-amber-500/20">
              <div className="text-[9px] font-semibold text-amber-400 uppercase tracking-wider mb-1">UNCERTAINTY</div>
              <div className="space-y-0.5">
                {analysis.uncertainty.map((u, i) => (
                  <div key={i} className="text-[10px] text-amber-400/80">⚠ {u}</div>
                ))}
              </div>
            </div>
          )}

          {/* Proposed Publication */}
          {analysis.proposed_publication && (
            <div className="p-2 rounded bg-green-500/5 border border-green-500/20 space-y-2">
              <div className="text-[9px] font-semibold text-green-400 uppercase tracking-wider">PROPOSED PUBLICATION</div>
              <div className="text-[10px] text-[#a0aec0]">
                {analysis.proposed_publication.quantity} {analysis.proposed_publication.resource_type}
                {analysis.proposed_publication.location_name && ` at ${analysis.proposed_publication.location_name}`}
              </div>
              <button
                onClick={() => handlePublish(analysis.proposed_publication)}
                className="w-full px-2.5 py-1.5 rounded text-[10px] font-medium bg-green-500/15 text-green-400 border border-green-500/30 hover:bg-green-500/25 transition-colors"
              >
                PUBLISH OFFER
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Network Requests Panel
// ---------------------------------------------------------------------------

function NetworkRequests({ orgId, onOpenNeed }) {
  const { state } = useWorkspace();
  const openNeeds = state.needs.filter(n => n.status === "OPEN");

  return (
    <div className="space-y-2">
      <div className="text-[9px] font-semibold text-[#6b7d93] uppercase tracking-wider px-1">
        NETWORK REQUESTS ({openNeeds.length})
      </div>

      {openNeeds.length === 0 ? (
        <div className="p-3 rounded bg-[#1a2332] border border-[#2a3a4e] text-center">
          <CheckCircle className="w-5 h-5 text-green-500 mx-auto mb-1" />
          <div className="text-[11px] text-[#6b7d93]">No open needs</div>
          <div className="text-[9px] text-[#4a5568]">All network requests are covered</div>
        </div>
      ) : (
        <div className="space-y-1">
          {openNeeds.slice(0, 10).map(need => (
            <button
              key={need.id}
              onClick={() => onOpenNeed(need)}
              className="w-full flex items-center gap-2 px-2.5 py-2 rounded bg-[#1a2332] border border-[#2a3a4e] hover:border-red-500/30 transition-colors text-left"
            >
              <AlertTriangle className="w-3.5 h-3.5 shrink-0" style={{
                color: need.urgency === "critical" ? "#dc2626" :
                       need.urgency === "high" ? "#d97706" : "#6b7d93"
              }} />
              <div className="flex-1 min-w-0">
                <div className="text-[11px] text-[#c8d6e5] truncate">{need.title || need.need_type}</div>
                <div className="text-[9px] text-[#6b7d93]">
                  {need.location_name || need.district_id} · {need.urgency}
                </div>
              </div>
              <ChevronRight className="w-3 h-3 text-[#6b7d93] shrink-0" />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main OrganizationWorkspace
// ---------------------------------------------------------------------------

export default function OrganizationWorkspace({ onOpenNeed }) {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("overview");

  const fetchSummary = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await fetch(`/api/orgs/${CURRENT_ORG_ID}/summary`);
      if (resp.ok) {
        const data = await resp.json();
        setSummary(data);
      }
    } catch (err) {
      console.error("Failed to fetch org summary:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSummary();
  }, [fetchSummary]);

  const tabs = [
    { id: "overview", label: "Overview", icon: Shield },
    { id: "ai", label: "AI", icon: Brain },
    { id: "resources", label: "Resources", icon: Package },
    { id: "teams", label: "Teams", icon: Users },
    { id: "missions", label: "Missions", icon: Map },
    { id: "requests", label: "Requests", icon: AlertTriangle },
  ];

  return (
    <div className="h-full flex flex-col bg-[#0f1419] overflow-hidden">
      {/* Header */}
      <div className="px-3 py-2 border-b border-[#2a3a4e]">
        <div className="flex items-center gap-2">
          <Shield className="w-4 h-4 text-[#4ea8de]" />
          <span className="text-[13px] font-semibold text-[#c8d6e5]">My Organization</span>
        </div>
        <div className="text-[9px] text-[#6b7d93] mt-0.5">{CURRENT_ORG_ID}</div>
      </div>

      {/* Tab bar */}
      <div className="flex border-b border-[#2a3a4e] overflow-x-auto">
        {tabs.map(tab => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                "flex items-center gap-1.5 px-2.5 py-1.5 text-[10px] font-medium border-b-2 transition-colors shrink-0",
                activeTab === tab.id
                  ? "border-[#4ea8de] text-[#4ea8de]"
                  : "border-transparent text-[#6b7d93] hover:text-[#c8d6e5]"
              )}
            >
              <Icon className="w-3 h-3" />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-3 space-y-4">
        {loading ? (
          <div className="text-[11px] text-[#6b7d93] text-center py-8">Loading organization data...</div>
        ) : (
          <>
            {activeTab === "overview" && <OrgSummary summary={summary} onRefresh={fetchSummary} />}
            {activeTab === "ai" && <NGOAgentPanel orgId={CURRENT_ORG_ID} summary={summary} />}
            {activeTab === "resources" && <PrivateResources orgId={CURRENT_ORG_ID} onRefresh={fetchSummary} />}
            {activeTab === "teams" && <PrivateTeams orgId={CURRENT_ORG_ID} />}
            {activeTab === "missions" && <PrivateMissions orgId={CURRENT_ORG_ID} />}
            {activeTab === "requests" && <NetworkRequests orgId={CURRENT_ORG_ID} onOpenNeed={onOpenNeed} />}
          </>
        )}
      </div>
    </div>
  );
}
