#!/bin/sh
# Make the edge proxy pass a websocket through, then reload it.
#
# The plain sh on the server is dash, so this file stays free of bashisms.
#
# See scripts/patch_edge_websocket.py for what this changes and why.
#
# Usage: sh scripts/patch-edge-websocket.sh [path/to/nginx.conf]
set -eu

CONF="${1:-/home/deploy/edge/nginx.conf}"
CONTAINER="${EDGE_CONTAINER:-ma-famille_edge_1}"
HERE=$(cd "$(dirname "$0")" && pwd)

if [ ! -f "$CONF" ]; then
  echo "edge config not found at $CONF" >&2
  exit 1
fi

python3 "$HERE/patch_edge_websocket.py" "$CONF"

# The running container has the file mounted, so it only needs the reload.
if podman exec "$CONTAINER" nginx -t 2>/dev/null; then
  podman exec "$CONTAINER" nginx -s reload
  echo "==> edge reloaded"
else
  echo "WARNING: nginx did not like the new config - the file is unchanged for now" >&2
  exit 1
fi
