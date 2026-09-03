import { useState, useEffect, useRef, useCallback } from "react";
import {
  Shield, Bell, Search, ChevronDown, Radio, Brain,
  X, MapPin, AlertTriangle, Zap, Route, Landmark, Clock, Globe,
  Stethoscope, Package,
} from "lucide-react";
import { useWorkspace } from "../../lib/workspaceContext";
import { cn } from "../../lib/utils";

const SEARCH_ICONS = {
  district: MapPin,
  settlement: MapPin,
  need: AlertTriangle,
  operation: Zap,
  road: Route,
  bridge: Landmark,
  facility: Stethoscope,
  organization: Globe,
};

const SEARCH_COLORS = {
  district: "#6b7d93",
  settlement: "#78716c",
  need: "#dc2626",
  operation: "#2563eb",
  road: "#16a34a",
  bridge: "#16a34a",
  facility: "#0891b2",
  organization: "#2563eb",
};

export default function WorkspaceHeader({ onOpenAI, mode, onModeChange }) {
  const { state, setFilter, openPanel, setSelectedEntity, performSearch, setMapCenter, fetchDelta } = useWorkspace();
  const [timeContext, setTimeContext] = useState('CURRENT');
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchIdx, setSearchIdx] = useState(0);
  const searchInputRef = useRef(null);
  const unreadCount = state.notifications.filter((n) => !n.read).length;

  // Keyboard shortcut: Cmd/Ctrl + K to open search
  useEffect(() => {
    const handler = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setSearchOpen((prev) => !prev);
      }
      if (e.key === "Escape") {
        setSearchOpen(false);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  // Focus input when search opens
  useEffect(() => {
    if (searchOpen && searchInputRef.current) {
      searchInputRef.current.focus();
    }
  }, [searchOpen]);

  const handleSearchChange = useCallback((e) => {
    const val = e.target.value;
    setSearchQuery(val);
    performSearch(val);
    setSearchIdx(0);
  }, [performSearch]);

  const handleSearchSelect = useCallback((result) => {
    // Focus map on the entity
    if (result.lat && result.lon) {
      setMapCenter([result.lat, result.lon]);
    }
    // Open the context panel
    if (result.data) {
      openPanel(result.type, result.id, result.data);
    } else {
      openPanel(result.type, result.id, { name: result.name, id: result.id });
    }
    setSearchOpen(false);
    setSearchQuery("");
  }, [openPanel, setMapCenter]);

  const handleSearchKeyDown = useCallback((e) => {
    const results = state.searchResults || [];
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSearchIdx((prev) => Math.min(prev + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSearchIdx((prev) => Math.max(prev - 1, 0));
    } else if (e.key === "Enter" && results[searchIdx]) {
      handleSearchSelect(results[searchIdx]);
    }
  }, [state.searchResults, searchIdx, handleSearchSelect]);

  return (
    <header className="h-11 bg-[#0f1419] border-b border-[#2a3a4e] flex items-center px-3 gap-3 shrink-0 z-50">
      {/* Logo */}
      <div className="flex items-center gap-2 mr-2">
        <div className="flex items-center justify-center w-6 h-6 rounded bg-[#1a2332] border border-[#2a3a4e]">
          <Shield className="w-3.5 h-3.5 text-[#4ea8de]" strokeWidth={2.5} />
        </div>
        <span className="text-[13px] font-semibold text-[#c8d6e5] tracking-tight hidden sm:inline">
          ReliefOS
        </span>
      </div>

      {/* District selector */}
      <div className="flex items-center gap-1.5 px-2 py-1 rounded bg-[#1a2332] border border-[#2a3a4e] cursor-pointer hover:border-[#3a5a7e] transition-colors">
        <Radio className="w-3 h-3 text-[#4ea8de]" />
        <select
          value={state.filters.district || ""}
          onChange={(e) => setFilter("district", e.target.value || null)}
          className="bg-transparent text-[12px] text-[#c8d6e5] outline-none cursor-pointer appearance-none pr-1"
        >
          <option value="" className="bg-[#1a2332]">All Districts</option>
          {state.districts.map((d) => (
            <option key={d.id} value={d.id} className="bg-[#1a2332]">
              {d.name}
            </option>
          ))}
        </select>
        <ChevronDown className="w-3 h-3 text-[#6b7d93]" />
      </div>

      {/* Mode toggle */}
      <div className="flex items-center gap-0.5 px-1 py-0.5 rounded bg-[#1a2332] border border-[#2a3a4e]">
        <button
          onClick={() => onModeChange && onModeChange('network')}
          className={cn(
            'flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium transition-colors',
            mode === 'network'
              ? 'bg-[#2a3a4e] text-[#c8d6e5]'
              : 'text-[#6b7d93] hover:text-[#c8d6e5]'
          )}
        >
          <Globe className="w-3 h-3" />
          Network
        </button>
        <button
          onClick={() => onModeChange && onModeChange('organization')}
          className={cn(
            'flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium transition-colors',
            mode === 'organization'
              ? 'bg-[#2a3a4e] text-[#c8d6e5]'
              : 'text-[#6b7d93] hover:text-[#c8d6e5]'
          )}
        >
          <Shield className="w-3 h-3" />
          My Org
        </button>
      </div>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Time context */}
      <div className="flex items-center gap-1 px-1 py-0.5 rounded bg-[#1a2332] border border-[#2a3a4e]">
        <Clock className="w-3 h-3 text-[#6b7d93] ml-1" />
        {[{label: 'CURRENT', hours: 1}, {label: '24H', hours: 24}, {label: '7D', hours: 168}].map((t) => (
          <button
            key={t.label}
            onClick={() => {
              setTimeContext(t.label);
              if (t.label !== 'CURRENT') fetchDelta(t.hours);
            }}
            className={cn(
              "px-1.5 py-0.5 rounded text-[9px] font-medium transition-colors",
              timeContext === t.label
                ? "bg-[#2a3a4e] text-[#c8d6e5]"
                : "text-[#6b7d93] hover:text-[#c8d6e5]"
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* System status */}
      <div className="flex items-center gap-1.5 px-2 py-1 rounded text-[11px] font-medium">
        <div className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
        <span className="text-green-400 hidden sm:inline">Live</span>
      </div>

      {/* Quick actions */}
      <button
        onClick={() => openPanel("createNeed")}
        className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-[#1a2332] border border-[#2a3a4e] hover:border-red-500/40 transition-colors group"
        title="Report a new need"
      >
        <AlertTriangle className="w-3 h-3 text-red-400" />
        <span className="text-[10px] font-medium text-[#6b7d93] group-hover:text-red-400 hidden sm:inline">+ Need</span>
      </button>
      <button
        onClick={() => openPanel("createOperation")}
        className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-[#1a2332] border border-[#2a3a4e] hover:border-blue-500/40 transition-colors group"
        title="Create a new operation"
      >
        <Zap className="w-3 h-3 text-blue-400" />
        <span className="text-[10px] font-medium text-[#6b7d93] group-hover:text-blue-400 hidden sm:inline">+ Operation</span>
      </button>
      <button
        onClick={() => openPanel("createOffer")}
        className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-[#1a2332] border border-[#2a3a4e] hover:border-teal-500/40 transition-colors group"
        title="Publish a resource offer"
      >
        <Package className="w-3 h-3 text-teal-400" />
        <span className="text-[10px] font-medium text-[#6b7d93] group-hover:text-teal-400 hidden sm:inline">+ Offer</span>
      </button>

      {/* AI Coordinator */}
      <button
        onClick={onOpenAI}
        className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-[#1a2332] border border-[#2a3a4e] hover:border-[#7c3aed] transition-colors group"
      >
        <Brain className="w-3.5 h-3.5 text-[#7c3aed] group-hover:text-[#a78bfa]" />
        <span className="text-[11px] font-medium text-[#a78bfa] hidden sm:inline">AI</span>
      </button>

      {/* Notifications */}
      <button className="relative flex items-center gap-1.5 px-2 py-1 rounded hover:bg-[#1a2332] transition-colors">
        <Bell className="w-3.5 h-3.5 text-[#6b7d93]" />
        {unreadCount > 0 && (
          <span className="absolute -top-0.5 -right-0.5 w-4 h-4 rounded-full bg-red-500 text-[9px] font-bold text-white flex items-center justify-center">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>

      {/* Search / Command palette */}
      <div className="relative">
        <button
          onClick={() => setSearchOpen(!searchOpen)}
          className={cn(
            "flex items-center gap-1.5 px-2 py-1 rounded transition-colors",
            searchOpen ? "bg-[#1a2332] border border-[#2a3a4e]" : "hover:bg-[#1a2332]"
          )}
        >
          <Search className="w-3.5 h-3.5 text-[#6b7d93]" />
          <span className="text-[11px] text-[#6b7d93] hidden md:inline">⌘K</span>
        </button>

        {searchOpen && (
          <div className="absolute top-full right-0 mt-1 w-96 bg-[#0f1419] border border-[#2a3a4e] rounded-lg shadow-2xl z-[9999] overflow-hidden">
            <div className="flex items-center gap-2 px-3 py-2.5 border-b border-[#2a3a4e]">
              <Search className="w-4 h-4 text-[#4ea8de] shrink-0" />
              <input
                ref={searchInputRef}
                autoFocus
                value={searchQuery}
                onChange={handleSearchChange}
                onKeyDown={handleSearchKeyDown}
                placeholder="Search needs, operations, locations..."
                className="flex-1 bg-transparent text-[13px] text-[#c8d6e5] placeholder:text-[#6b7d93] outline-none"
              />
              <button
                onClick={() => { setSearchOpen(false); setSearchQuery(""); }}
                className="shrink-0 text-[#6b7d93] hover:text-[#c8d6e5] transition-colors"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
            <div className="max-h-80 overflow-y-auto">
              {(state.searchResults || []).length === 0 ? (
                <div className="p-4 text-center text-[12px] text-[#4a5568]">
                  {searchQuery.length < 2
                    ? "Type to search across all operational data..."
                    : "No results found"}
                </div>
              ) : (
                <div className="py-1">
                  {state.searchResults.map((result, idx) => {
                    const Icon = SEARCH_ICONS[result.type] || MapPin;
                    const color = SEARCH_COLORS[result.type] || "#6b7d93";
                    return (
                      <button
                        key={`${result.type}-${result.id}-${idx}`}
                        onClick={() => handleSearchSelect(result)}
                        onMouseEnter={() => setSearchIdx(idx)}
                        className={cn(
                          "w-full flex items-center gap-2.5 px-3 py-2 text-left transition-colors",
                          idx === searchIdx ? "bg-[#1a2332]" : "hover:bg-[#1a2332]/50"
                        )}
                      >
                        <div
                          className="w-6 h-6 rounded flex items-center justify-center shrink-0"
                          style={{ backgroundColor: `${color}15` }}
                        >
                          <Icon className="w-3 h-3" style={{ color }} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="text-[12px] text-[#c8d6e5] truncate font-medium">
                            {result.name}
                          </div>
                          <div className="text-[10px] text-[#6b7d93] capitalize">{result.type}</div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </header>
  );
}
