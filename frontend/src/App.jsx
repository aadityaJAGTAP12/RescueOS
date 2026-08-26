import { useState, useCallback, useEffect } from "react";
import { BrowserRouter, Routes, Route, Link, useLocation } from "react-router-dom";
import Header from "./components/Header";
import LocationSelector from "./components/LocationSelector";
import SituationMap from "./components/SituationMap";
import OperationalAnswer from "./components/OperationalAnswer";
import EvidencePanel from "./components/EvidencePanel";
import DataGapsPanel from "./components/DataGapsPanel";
import FieldIntelligencePage from "./components/FieldIntelligencePage";
import QueryInput from "./components/QueryInput";
import StagedReveal from "./components/StagedReveal";

/* ------------------------------------------------------------------
   Dashboard page — the main assessment view
   ------------------------------------------------------------------ */

function DashboardPage() {
  const [selectedLocation, setSelectedLocation] = useState(null);
  const [assessment, setAssessment] = useState(null);
  const [route, setRoute] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchAssessment = useCallback(async (locationId) => {
    setLoading(true);
    setError(null);
    setRoute(null);
    try {
      const resp = await fetch(`/api/assess?location=${encodeURIComponent(locationId)}`);
      if (!resp.ok) throw new Error(`Assessment failed: ${resp.status}`);
      const data = await resp.json();
      setAssessment(data);
      
      // Fetch route from origin (Sivasagar) to this location
      if (data.coordinates?.lat && data.coordinates?.lon) {
        try {
          // Origin: Sivasagar town center
          const originLat = 26.98;
          const originLon = 94.66;
          const routeResp = await fetch(
            `/api/route?start_lat=${originLat}&start_lon=${originLon}&end_lat=${data.coordinates.lat}&end_lon=${data.coordinates.lon}`
          );
          if (routeResp.ok) {
            const routeData = await routeResp.json();
            setRoute(routeData);
          }
        } catch (routeErr) {
          console.error("Route fetch failed:", routeErr);
          // Non-critical - assessment still works without route
        }
      }
    } catch (err) {
      setError(err.message);
      setAssessment(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleSelectLocation = useCallback(
    (locationId) => {
      setSelectedLocation(locationId);
      fetchAssessment(locationId);
    },
    [fetchAssessment]
  );

  useEffect(() => {
    handleSelectLocation("sivasagar_flood_zone");
  }, []);

  return (
    <>
      {/* Free-text query input */}
      <div className="mb-4 sm:mb-6">
        <QueryInput />
      </div>

      {/* Location selector bar */}
      <div className="mb-4 sm:mb-6 bg-white rounded-xl border border-stone-200 px-4 py-3 shadow-sm">
        <LocationSelector selectedId={selectedLocation} onSelect={handleSelectLocation} />
      </div>

      {error && (
        <div className="mb-4 rounded-xl border border-red-200 bg-red-50 p-4 text-[13px] text-red-700">
          {error}
        </div>
      )}

      {/* Main grid */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_380px] gap-4 sm:gap-5">
        <div className="space-y-4 sm:space-y-5 min-w-0">
          <div className={loading ? "opacity-60 transition-opacity duration-300" : "transition-opacity duration-300"}>
            <SituationMap assessment={assessment} loading={loading} route={route} />
          </div>
          <EvidencePanel assessment={assessment} loading={loading} />
        </div>
        <div className="space-y-4 sm:space-y-5">
          <OperationalAnswer assessment={assessment} loading={loading} />
          {assessment?.agent_trace && assessment.agent_trace.length > 0 && (
            <div className="rounded-xl border border-stone-200 bg-white p-4 shadow-sm">
              <StagedReveal
                agentTrace={assessment.agent_trace}
                assessment={assessment}
                loading={loading}
              />
            </div>
          )}
          <DataGapsPanel dataGaps={assessment?.data_gaps} loading={loading} />
        </div>
      </div>
    </>
  );
}

/* ------------------------------------------------------------------
   App — routing and layout
   ------------------------------------------------------------------ */

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-stone-50 flex flex-col">
        <Header />
        <main className="flex-1 max-w-[1600px] mx-auto w-full px-4 sm:px-6 lg:px-8 py-4 sm:py-6">
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/field-intelligence" element={<FieldIntelligencePage />} />
          </Routes>
        </main>
        <footer className="border-t border-stone-200 bg-white/50">
          <div className="max-w-[1600px] mx-auto px-4 sm:px-6 lg:px-8 py-3 flex items-center justify-between">
            <span className="text-[11px] text-stone-400">
              ReliefOS v0.1 — Operations Intelligence Workspace
            </span>
            <span className="text-[11px] text-stone-400">
              Sivasagar District, Assam, India
            </span>
          </div>
        </footer>
      </div>
    </BrowserRouter>
  );
}
