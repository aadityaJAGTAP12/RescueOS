import json
import math
from shapely.geometry import shape, Point
 
# --- Config: match your actual query point ---
QUERY_LON = 94.6698
QUERY_LAT = 26.9894
CACHE_FILE = "data/cache/buildings_sivasagar_flood_zone.json"
FLOOD_FILE = "data/sivasagar_flood.geojson"
 
def haversine_km(lon1, lat1, lon2, lat2):
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))
 
# Load flood polygons
flood_data = json.load(open(FLOOD_FILE))
polygons = [shape(f["geometry"]) for f in flood_data["features"]]
 
# Load cached buildings
data = json.load(open(CACHE_FILE))
buildings = [e for e in data.get("elements", []) if e.get("type") == "way"]
nodes_by_id = {n["id"]: n for n in data.get("elements", []) if n.get("type") == "node"}
 
print(f"Total buildings in cache: {len(buildings)}")
 
close_count = 0
missing_node_count = 0
exposed_count = 0
distances = []
 
for building in buildings:
    node_ids = building.get("nodes", [])
    coords = [(nodes_by_id[nid]["lon"], nodes_by_id[nid]["lat"]) for nid in node_ids if nid in nodes_by_id]
 
    if not coords:
        missing_node_count += 1
        continue
 
    if len(coords) < len(node_ids):
        # partial node data — centroid may be skewed
        pass
 
    centroid_lon = sum(c[0] for c in coords) / len(coords)
    centroid_lat = sum(c[1] for c in coords) / len(coords)
 
    dist_km = haversine_km(QUERY_LON, QUERY_LAT, centroid_lon, centroid_lat)
    distances.append(dist_km)
 
    if dist_km < 0.5:
        close_count += 1
 
    b_point = Point(centroid_lon, centroid_lat)
    if any(poly.contains(b_point) for poly in polygons):
        exposed_count += 1
 
print(f"Buildings with missing node data (skipped): {missing_node_count}")
print(f"Buildings within 500m of query point: {close_count}")
print(f"Buildings flagged as flood-exposed: {exposed_count}")
if distances:
    print(f"Nearest building distance: {min(distances):.3f} km")
    print(f"Farthest building distance: {max(distances):.3f} km")
    print(f"Average building distance: {sum(distances)/len(distances):.3f} km")
 
# Also check flood polygon size for context — SUMMARY ONLY, not per-polygon
areas_km2 = [poly.area * 111 * 111 for poly in polygons]
print("\n--- Flood polygon summary ---")
print(f"Total polygons: {len(polygons)}")
print(f"Smallest polygon: {min(areas_km2):.4f} sq km")
print(f"Largest polygon: {max(areas_km2):.4f} sq km")
print(f"Average polygon size: {sum(areas_km2)/len(areas_km2):.4f} sq km")
print(f"Total flooded area (sum): {sum(areas_km2):.2f} sq km")
 
# Which polygon contains the query point, and how big is it specifically?
query_point = Point(QUERY_LON, QUERY_LAT)
for i, poly in enumerate(polygons):
    if poly.contains(query_point):
        print(f"\nQuery point falls inside polygon #{i}, size ~{areas_km2[i]:.4f} sq km, bounds={poly.bounds}")
        break
 