#!/usr/bin/env bash
# Download the Geofabrik West Midlands extract and preprocess it for OSRM (MLD pipeline).
# Usage: scripts/prepare_osrm.sh        then: docker compose --profile osrm up -d osrm
# Output goes to osrm/ (gitignored). Takes a few minutes and ~2 GB RAM on an M1 Pro.
set -euo pipefail

IMAGE="ghcr.io/project-osrm/osrm-backend:v26.4.0"  # pinned; multi-arch (amd64 + arm64)
URL="https://download.geofabrik.de/europe/united-kingdom/england/west-midlands-latest.osm.pbf"
DIR="$(cd "$(dirname "$0")/.." && pwd)/osrm"
NAME="west-midlands-latest"

mkdir -p "$DIR"
if [[ ! -f "$DIR/$NAME.osm.pbf" ]]; then
  curl -fL --retry 3 -o "$DIR/$NAME.osm.pbf" "$URL"
  curl -fL --retry 3 -o "$DIR/$NAME.osm.pbf.md5" "$URL.md5"
fi
(cd "$DIR" && md5sum -c "$NAME.osm.pbf.md5" 2>/dev/null || md5 -r "$NAME.osm.pbf" | \
  awk -v want="$(cut -d' ' -f1 "$NAME.osm.pbf.md5")" '{ exit ($1 == want ? 0 : 1) }')

run() { docker run --rm -t -v "$DIR:/data" "$IMAGE" "$@"; }
run osrm-extract -p /opt/car.lua "/data/$NAME.osm.pbf"  # car profile: road speeds, turn rules
run osrm-partition "/data/$NAME.osrm"                     # multi-level graph partition
run osrm-customize "/data/$NAME.osrm"                     # edge weights per partition cell
echo "OSRM data ready in $DIR. Start it with: docker compose --profile osrm up -d osrm"
