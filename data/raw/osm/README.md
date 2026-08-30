# OSM Data

## Regional OSM PBF

`north-eastern-zone-latest.osm.pbf` is a regional OpenStreetMap extract
covering Assam and surrounding North-Eastern Indian states.

**Source:** Geofabrik North-Eastern India extract
**Size:** ~104 MB
**Used by:** OSRM routing server (`osrm/setup.sh`), infrastructure ingestion

This file is an external source dataset and is **intentionally not
committed to GitHub** (exceeds 100 MB file limit). It is listed in
`.gitignore` and must be acquired locally:

```bash
cd osrm
./setup.sh
```

The setup script downloads the PBF from Geofabrik automatically.

See also: `osrm/README.md` for full OSRM setup instructions.
