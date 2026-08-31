import { useState } from "react";
import { Shield, Bell, Search, ChevronDown, Radio, Brain } from "lucide-react";
import { useWorkspace } from "../../lib/workspaceContext";
import { cn } from "../../lib/utils";

export default function WorkspaceHeader({ onOpenAI }) {
  const { state, setFilter } = useWorkspace();
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const unreadCount = state.notifications.filter((n) => !n.read).length;

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

      {/* Spacer */}
      <div className="flex-1" />

      {/* System status */}
      <div className="flex items-center gap-1.5 px-2 py-1 rounded text-[11px] font-medium">
        <div className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
        <span className="text-green-400 hidden sm:inline">System Active</span>
      </div>

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

      {/* Search */}
      <div className="relative">
        <button
          onClick={() => setSearchOpen(!searchOpen)}
          className="flex items-center gap-1.5 px-2 py-1 rounded hover:bg-[#1a2332] transition-colors"
        >
          <Search className="w-3.5 h-3.5 text-[#6b7d93]" />
          <span className="text-[11px] text-[#6b7d93] hidden md:inline">⌘K</span>
        </button>
        {searchOpen && (
          <div className="absolute top-full right-0 mt-1 w-80 bg-[#1a2332] border border-[#2a3a4e] rounded-lg shadow-xl z-50 overflow-hidden">
            <div className="flex items-center gap-2 px-3 py-2 border-b border-[#2a3a4e]">
              <Search className="w-3.5 h-3.5 text-[#6b7d93]" />
              <input
                autoFocus
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Escape") setSearchOpen(false);
                }}
                placeholder="Search needs, operations, locations..."
                className="flex-1 bg-transparent text-[13px] text-[#c8d6e5] placeholder:text-[#6b7d93] outline-none"
              />
            </div>
            <div className="p-3 text-[12px] text-[#6b7d93]">
              Type to search across all operational data...
            </div>
          </div>
        )}
      </div>
    </header>
  );
}
