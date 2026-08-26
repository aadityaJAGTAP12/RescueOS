import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs) {
  return twMerge(clsx(inputs));
}

/**
 * Format a priority category to a human-readable label with color class.
 */
export function getCategoryStyle(category) {
  switch (category) {
    case "HIGH PRIORITY":
      return { color: "text-red-700", bg: "bg-red-50", border: "border-red-200", dot: "bg-red-600", label: "HIGH PRIORITY" };
    case "PRIORITY":
      return { color: "text-red-600", bg: "bg-red-50", border: "border-red-200", dot: "bg-red-500", label: "PRIORITY" };
    case "EXPOSED":
      return { color: "text-amber-600", bg: "bg-amber-50", border: "border-amber-200", dot: "bg-amber-500", label: "EXPOSED" };
    case "SAFE":
      return { color: "text-green-600", bg: "bg-green-50", border: "border-green-200", dot: "bg-green-500", label: "SAFE" };
    case "NONE":
      return { color: "text-stone-500", bg: "bg-stone-50", border: "border-stone-200", dot: "bg-stone-400", label: "NONE" };
    default:
      return { color: "text-stone-600", bg: "bg-stone-50", border: "border-stone-200", dot: "bg-stone-400", label: category };
  }
}

/**
 * Get Leaflet marker color for a priority category.
 */
export function getMarkerColor(category) {
  switch (category) {
    case "HIGH PRIORITY": return "#991b1b";
    case "PRIORITY": return "#dc2626";
    case "EXPOSED": return "#d97706";
    case "SAFE": return "#16a34a";
    case "NONE": return "#78716c";
    default: return "#78716c";
  }
}

/**
 * Humanize an evidence key to a display title.
 */
export function humanizeKey(key) {
  const map = {
    flood: "Flood Status",
    exposure: "Building Exposure",
    accessibility: "Medical Accessibility",
    field_reports: "Field Reports",
    road_status: "Road Status",
    sustainment: "Sustainment",
  };
  return map[key] || key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Format a number for display.
 */
export function formatValue(key, value) {
  if (value === null || value === undefined) return "—";
  if (key === "exposure_ratio" && typeof value === "number") {
    return `${(value * 100).toFixed(1)}%`;
  }
  if (key === "medical_distance_km" && typeof value === "number") {
    return value < 0 ? "Unknown" : `${value.toFixed(1)} km`;
  }
  if (key === "nearest_flood_polygon_km2" && typeof value === "number") {
    return `${value.toFixed(2)} km²`;
  }
  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }
  if (typeof value === "number") {
    return value.toLocaleString();
  }
  return String(value);
}

/**
 * Fields to hide from generic evidence display (handled specially).
 */
export const HIDDEN_FIELDS = new Set([
  "status", "source", "last_updated", "location", "detail",
  "data_available", "error", "total_flood_polygons",
]);

/**
 * Get the relevant fields for a specific evidence type.
 */
export function getEvidenceFields(evidenceKey, evidenceData) {
  if (evidenceKey === "field_reports") return null; // handled specially
  return Object.entries(evidenceData).filter(
    ([k, v]) => !HIDDEN_FIELDS.has(k) && v !== null && v !== undefined
  );
}
