#!/bin/bash
set -e

echo "=== OSRM Setup for ReliefOS ==="
echo "Downloading North-Eastern Zone OSM extract..."

mkdir -p data
cd data

# Download the latest North-Eastern Zone extract from Geofabrik
OSM_FILE="north-eastern-zone-latest.osm.pbf"
if [ ! -f "$OSM_FILE" ]; then
    echo "Downloading OSM extract (104 MB)..."
    wget -q "https://download.geofabrik.de/asia/india/$OSM_FILE"
    echo "Download complete."
else
    echo "OSM file already exists."
fi

echo ""
echo "=== Processing OSM data for OSRM ==="
echo "This may take 5-10 minutes..."

# Extract OSM data for OSRM
echo "Step 1: osrm-extract..."
docker run --rm -v "$(pwd):/data" osrm/osrm-backend osrm-extract \
    -p /opt/car.lua \
    /data/$OSM_FILE

# Partition for multi-level Dijkstra
echo "Step 2: osrm-partition..."
docker run --rm -v "$(pwd):/data" osrm/osrm-backend osrm-partition \
    /data/north-eastern-zone-latest.osrm

# Contract the graph
echo "Step 3: osrm-contract..."
docker run --rm -v "$(pwd):/data" osrm/osrm-backend osrm-contract \
    /data/north-eastern-zone-latest.osrm

echo ""
echo "=== Setup Complete ==="
echo "OSRM files created:"
ls -lh north-eastern-zone-latest.osrm*
echo ""
echo "To start OSRM:"
echo "  cd osrm && docker-compose up -d"
echo ""
echo "OSRM will be available at http://localhost:5001"
