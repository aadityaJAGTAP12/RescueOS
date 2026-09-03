import { useState } from "react";
import WorkspaceHeader from "./WorkspaceHeader";
import LayerRail from "./LayerRail";
import MapCanvas from "./MapCanvas";
import ContextPanel from "./ContextPanel";
import ActivityBar from "./ActivityBar";
import OrganizationWorkspace from "./OrganizationWorkspace";
import { useWorkspace } from "../../lib/workspaceContext";
import { cn } from "../../lib/utils";
import { Globe, Shield } from "lucide-react";

export default function NetworkWorkspace() {
  const { openPanel } = useWorkspace();
  const [mode, setMode] = useState("network"); // "network" | "organization"

  const handleOpenAI = () => {
    openPanel("aiAnalysis");
  };

  const handleOpenNeed = (need) => {
    openPanel("need", need.id, need);
  };

  return (
    <div className="h-screen flex flex-col bg-[#0f1419] overflow-hidden">
      {/* Header */}
      <WorkspaceHeader onOpenAI={handleOpenAI} mode={mode} onModeChange={setMode} />

      {/* Main workspace body */}
      <div className="flex-1 flex overflow-hidden">
        {mode === "network" ? (
          <>
            {/* Left layer rail */}
            <LayerRail />

            {/* Center map canvas */}
            <MapCanvas />

            {/* Right context panel */}
            <ContextPanel />
          </>
        ) : (
          <>
            {/* Organization workspace replaces layer rail + map */}
            <div className="w-80 border-r border-[#2a3a4e] shrink-0 overflow-hidden">
              <OrganizationWorkspace onOpenNeed={handleOpenNeed} />
            </div>

            {/* Map remains visible */}
            <MapCanvas />

            {/* Right context panel */}
            <ContextPanel />
          </>
        )}
      </div>

      {/* Bottom activity bar */}
      <ActivityBar />
    </div>
  );
}
