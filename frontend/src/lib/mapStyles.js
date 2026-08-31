/**
 * Single source of truth for all map object colors, widths, and dash patterns.
 *
 * Every component that renders map features MUST import from here.
 * Do not define these values inline — drift is a known failure mode.
 */

export const MAP_STYLES = {
  road: {
    open:     { color: '#16a34a', width: 2, dash: null },
    blocked:  { color: '#dc2626', width: 3, dash: [6, 3] },
    uncertain:{ color: '#d97706', width: 2, dash: null },
  },
  bridge: {
    open:     { color: '#16a34a', width: 3, dash: null },
    blocked:  { color: '#dc2626', width: 4, dash: [6, 3] },
    uncertain:{ color: '#d97706', width: 3, dash: null },
  },
  route: {
    normal:          { color: '#2563eb', width: 4, dash: null },
    floodCrossing:   { color: '#d97706', width: 5, dash: null },    // probabilistic risk — proximity to flood extent
    overrideBlocked: { color: '#dc2626', width: 5, dash: [6, 3] }, // confirmed hazard — route crosses an actively overridden-blocked road/bridge
  },
  routeCasing: {
    // Slightly wider dark line rendered underneath the main route line for basemap contrast.
    // Width = main route width + 2. Applied to ALL route states.
    color: '#001014',
    extraWidth: 2,
  },
  overrideIndicator: { color: '#f59e0b' },
};

/**
 * Convert a MAP_STYLES entry into a Leaflet polyline style object.
 * Adds the route casing (dark underline) for route-layer lines.
 *
 * @param {object} style  One of the values from MAP_STYLES.road/bridge/route
 * @param {boolean} withCasing  Whether to add casing info (used by route layer only)
 * @returns {object} Leaflet-compatible style
 */
export function toLeafletStyle(style, withCasing = false) {
  const result = {
    color: style.color,
    weight: style.width,
    opacity: 0.85,
    dashArray: style.dash ? style.dash.join(', ') : null,
  };
  if (withCasing) {
    // Casing is applied via a separate GeoJSON layer rendered underneath.
    // This helper returns the casing style.
    result._casing = {
      color: MAP_STYLES.routeCasing.color,
      weight: style.width + MAP_STYLES.routeCasing.extraWidth,
      opacity: 0.9,
      dashArray: style.dash ? style.dash.join(', ') : null,
    };
  }
  return result;
}

/**
 * Compute the effective route style key from backend response fields.
 *
 * @param {object} route  The route response from /api/route
 * @returns {'normal'|'floodCrossing'|'overrideBlocked'}
 */
export function getRouteStyleKey(route) {
  if (route.crosses_overridden_road) return 'overrideBlocked';
  if (route.crosses_flood_zone) return 'floodCrossing';
  return 'normal';
}
