import { useState } from "react";
import WorkspaceHeader from "./WorkspaceHeader";
import LayerRail from "./LayerRail";
import MapCanvas from "./MapCanvas";
import ContextPanel from "./ContextPanel";
import ActivityBar from "./ActivityBar";
import { useWorkspace } from "../../lib/workspaceContext";

export default function NetworkWorkspace() {
  const { openPanel } = useWorkspace();
  const [aiOpen, setAiOpen] = useState(false);

  const handleOpenAI = () => {
    openPanel("aiAnalysis");
  };

  return (
    <div className="h-screen flex flex-col bg-[#0f1419] overflow-hidden">
      {/* Header */}
      <WorkspaceHeader onOpenAI={handleOpenAI} />

      {/* Main workspace body */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left layer rail */}
        <LayerRail />

        {/* Center map canvas */}
        <MapCanvas />

        {/* Right context panel */}
        <ContextPanel />
      </div>

      {/* Bottom activity bar */}
      <ActivityBar />
    </div>
  );
}
