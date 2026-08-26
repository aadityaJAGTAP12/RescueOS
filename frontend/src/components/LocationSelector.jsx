import { useState, useEffect } from "react";
import { MapPin, ChevronDown } from "lucide-react";
import { cn } from "../lib/utils";

export default function LocationSelector({ selectedId, onSelect }) {
  const [locations, setLocations] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/locations")
      .then((r) => r.json())
      .then((data) => {
        setLocations(data.locations || []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center gap-2 px-3 py-2">
        <div className="skeleton h-4 w-32 rounded" />
        <div className="skeleton h-4 w-24 rounded" />
        <div className="skeleton h-4 w-28 rounded" />
      </div>
    );
  }

  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      <MapPin className="w-4 h-4 text-stone-400 shrink-0 mr-1" />
      {locations.map((loc) => {
        const isActive = selectedId === loc.id;
        return (
          <button
            key={loc.id}
            onClick={() => onSelect(loc.id)}
            className={cn(
              "px-3 py-1.5 rounded-md text-[13px] font-medium transition-all duration-200",
              "border outline-none focus-visible:ring-2 focus-visible:ring-stone-400 focus-visible:ring-offset-1",
              isActive
                ? "bg-stone-900 text-white border-stone-900 shadow-sm"
                : "bg-white text-stone-600 border-stone-200 hover:bg-stone-50 hover:border-stone-300 hover:text-stone-800"
            )}
          >
            {loc.label}
          </button>
        );
      })}
    </div>
  );
}
