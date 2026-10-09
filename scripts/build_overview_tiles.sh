#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
command -v osmium >/dev/null || { echo 'Install osmium-tool first'; exit 1; }
mkdir -p tiles
if [ ! -f tiles/iran-latest.osm.pbf ]; then
  curl -fL https://download.geofabrik.de/asia/iran-latest.osm.pbf -o tiles/iran-latest.osm.pbf
fi
osmium tags-filter tiles/iran-latest.osm.pbf n/place=city,town r/boundary=administrative w/highway=motorway,trunk,primary,secondary w/natural=water r/natural=water w/waterway=river -o tiles/iran-overview.osm.pbf --overwrite
osmium renumber tiles/iran-overview.osm.pbf -o tiles/iran-overview-compact.osm.pbf --overwrite
docker run --rm --memory=800m --memory-swap=800m -e JAVA_TOOL_OPTIONS=-Xmx512m \
  -v "$PWD/tiles:/data" ghcr.io/onthegomap/planetiler:latest \
  --osm-path=/data/iran-overview-compact.osm.pbf --output=/data/iran.mbtiles --download \
  --maxzoom=8 --threads=1 --nodemap-type=sparsearray --nodemap-storage=mmap \
  --bounds=44,24,64,40 --languages=fa,en --compress-temp \
  --free-water-polygons-after-read --free-natural-earth-after-read --free-lake-centerlines-after-read --force
