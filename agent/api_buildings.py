"""
Phase 7I-B: Buildings API endpoints

Viewport-bounded building queries using PostGIS spatial filtering.
Returns buildings within a bounding box with zoom-dependent limiting
to prevent catastrophic browser performance with 214K+ buildings.
"""

from flask import request, jsonify


def register_building_routes(app):
    """Register building-related routes on the Flask app."""

    @app.route("/api/districts/<district_id>/buildings", methods=["GET"])
    def api_district_buildings(district_id):
        """
        Return buildings for a district, viewport-bounded.

        Query parameters:
            west, south, east, north: bounding box in lon/lat (optional)
            zoom: current map zoom level (used to cap response size)
            limit: max buildings to return (default varies by zoom)

        At zoom < 13: return only point centroids (fast).
        At zoom >= 13: return buildings within viewport, capped.

        Returns: FeatureCollection of building point features.
        """
        try:
            from agent.data.repository import get_repository
            repo = get_repository()

            # Parse optional bounding box
            west = request.args.get("west", type=float)
            south = request.args.get("south", type=float)
            east = request.args.get("east", type=float)
            north = request.args.get("north", type=float)
            zoom = request.args.get("zoom", type=int, default=10)
            limit = request.args.get("limit", type=int)

            # Zoom-dependent limits: prevent browser overload
            if limit is None:
                if zoom >= 15:
                    limit = 5000
                elif zoom >= 13:
                    limit = 2000
                elif zoom >= 11:
                    limit = 500
                else:
                    limit = 200

            buildings = repo.get_buildings(
                district_id,
                lat=(south + north) / 2 if south is not None and north is not None else None,
                lon=(west + east) / 2 if west is not None and east is not None else None,
                radius_km=_bbox_radius_km(west, south, east, north),
            )

            # Apply bounding box filter in Python (for InMemoryRepository compatibility)
            if west is not None and south is not None and east is not None and north is not None:
                # Handle wrap-around (west > east means crossing antimeridian, unlikely here)
                if west <= east:
                    buildings = [
                        b for b in buildings
                        if west <= b.lon <= east and south <= b.lat <= north
                    ]
                else:
                    buildings = [
                        b for b in buildings
                        if (b.lon >= west or b.lon <= east) and south <= b.lat <= north
                    ]

            # Cap response size
            total_available = len(buildings)
            buildings = buildings[:limit]

            features = []
            for b in buildings:
                feature = {
                    "type": "Feature",
                    "properties": {
                        "id": b.id,
                        "district_id": b.district_id,
                        "in_flood_zone": b.in_flood_zone,
                        "tags": b.tags,
                    },
                    "geometry": {
                        "type": "Point",
                        "coordinates": [b.lon, b.lat],
                    },
                }
                features.append(feature)

            return jsonify({
                "type": "FeatureCollection",
                "features": features,
                "meta": {
                    "total_available": total_available,
                    "returned": len(features),
                    "limit": limit,
                    "zoom": zoom,
                    "truncated": total_available > limit,
                },
            })
        except Exception as e:
            import logging
            logging.getLogger("reliefos.api").warning("buildings endpoint error (%s)", type(e).__name__, exc_info=True)
            return jsonify({"error": "InternalError: internal error"}), 500

    @app.route("/api/districts/<district_id>/buildings/count", methods=["GET"])
    def api_district_buildings_count(district_id):
        """Return the count of buildings in a district (fast, no geometry transfer)."""
        try:
            from agent.data.repository import get_repository
            repo = get_repository()
            buildings = repo.get_buildings(district_id)
            return jsonify({
                "count": len(buildings),
                "district_id": district_id,
            })
        except Exception as e:
            import logging
            logging.getLogger("reliefos.api").warning("buildings endpoint error (%s)", type(e).__name__, exc_info=True)
            return jsonify({"error": "InternalError: internal error"}), 500


def _bbox_radius_km(west, south, east, north):
    """Estimate the radius in km from a bounding box center to its edge."""
    if west is None or south is None or east is None or north is None:
        return None
    import math
    # Approximate center-to-corner distance
    center_lon = (west + east) / 2
    center_lat = (south + north) / 2
    dlat = abs(north - south) / 2
    dlon = abs(east - west) / 2
    # Convert degrees to km (rough)
    lat_km = dlat * 111.0
    lon_km = dlon * 111.0 * math.cos(math.radians(center_lat))
    return math.sqrt(lat_km**2 + lon_km**2) + 1.0  # +1km buffer
