# OSRM Routing Setup for ReliefOS

## Overview

This directory contains the OSRM (Open Source Routing Machine) setup for ReliefOS, providing real road-network routing for the disaster response system.

## Infrastructure Setup

### Prerequisites

- Docker and Docker Compose installed
- ~500 MB disk space for OSM data and OSRM processing
- ~1 GB RAM for OSRM server

### Setup Steps

1. **Download OSM Data**
   ```bash
   cd osrm
   ./setup.sh
   ```
   
   This downloads the North-Eastern Zone OSM extract (104 MB) from Geofabrik, which covers Assam and surrounding states.

2. **Process OSM Data**
   
   The setup script automatically runs:
   - `osrm-extract` - Extracts routing data from OSM
   - `osrm-partition` - Partitions the graph for multi-level Dijkstra
   - `osrm-contract` - Contracts the graph for fast queries
   
   Processing takes 5-10 minutes depending on hardware.

3. **Start OSRM Server**
   ```bash
   docker-compose up -d
   ```
   
   OSRM will be available at `http://localhost:5001`

4. **Verify OSRM is Running**
   ```bash
   curl http://localhost:5001/health
   ```
   
   Should return: `{"status": "ok"}`

## API Usage

### Single Route

```bash
curl "http://localhost:5001/route/v1/driving/94.66,26.98;94.7,27.0?overview=full&geometries=geojson"
```

### Response Format

```json
{
  "code": "Ok",
  "routes": [{
    "distance": 15000,        // meters
    "duration": 1800,         // seconds
    "geometry": {
      "coordinates": [[lon, lat], ...],
      "type": "LineString"
    }
  }]
}
```

## Integration with ReliefOS

### Backend

- `agent/tools/routing_tool.py` - Main routing interface
- `agent/api.py` - Flask endpoints for routing
  - `GET /api/route` - Single route query
  - `POST /api/routes` - Multiple routes query
  - `POST /api/recommend-destination` - Route-aware destination recommendation

### Frontend

- `frontend/src/components/SituationMap.jsx` - Renders route geometry on map
- `frontend/src/App.jsx` - Fetches and passes route data

## Graceful Degradation

When OSRM is unavailable (not running, unreachable, etc.):

1. `check_osrm_health()` returns `False`
2. `get_route()` automatically falls back to haversine (straight-line) distance
3. Response explicitly labels the method used:
   - `"distance_method": "OSRM road routing"` - Real road distance
   - `"distance_method": "straight-line (haversine) — routing unavailable"` - Approximation

**Critical**: The system never silently pretends a straight-line approximation is a real route.

## Performance Notes

- OSRM processes ~100k queries/second on typical hardware
- Query response time: typically < 10ms
- Memory usage: ~500 MB for North-Eastern Zone dataset
- Processing time: ~5-10 minutes for initial setup

## Troubleshooting

### OSRM Won't Start

1. Check Docker is running: `docker ps`
2. Check logs: `docker-compose logs osrm-backend`
3. Ensure data files exist: `ls -la data/`

### Route Queries Return NoRoute

1. Verify points are on road network
2. Check if coordinates are in correct order (lon,lat)
3. Ensure OSRM health check passes

### High Memory Usage

OSRM loads the entire road graph into memory. For the North-Eastern Zone:
- Expected: ~500 MB
- If higher, check for memory leaks or restart container

## Future Enhancements

### Phase 2: Flood-Aware Routing

Planned improvements:
1. Detect route-flood polygon intersections
2. Report flood-crossing warnings
3. Attempt alternative routes (if OSRM version supports avoid areas)

### Custom Profiles

Consider creating a custom OSRM profile for relief vehicles:
- Higher weight for flooded roads
- Avoidance of low-water crossings
- Different speed assumptions for emergency vehicles

## References

- [OSRM Documentation](http://project-osrm.org/docs/v5.24.0/)
- [Geofabrik Downloads](https://download.geofabrik.de/)
- [OpenStreetMap](https://www.openstreetmap.org/)
