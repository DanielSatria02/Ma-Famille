#!/usr/bin/env bash
# Make the edge proxy pass a websocket through.
#
# The API has a websocket route — the payment page is told the moment a
# booking settles — but the shared edge config proxies without the upgrade
# headers, so the request arrived as a plain GET and the API answered 404.
# The page then sat there saying "reconnecting" for a socket that could
# never open.
#
# The edge file is shared by every app on this host, so this only touches
# the ma-famille API block and only adds to it. The file is backed up
# first, and the change is skipped when it is already there.
#
# Usage: bash scripts/patch-edge-websocket.sh [path/to/nginx.conf]
set -euo pipefail

CONF="${1:-/home/deploy/edge/nginx.conf}"
CONTAINER="${EDGE_CONTAINER:-ma-famille_edge_1}"
LOCATION_MARKER='location ^~ /ma-famille/v1/ {'

if [ ! -f "$CONF" ]; then
  echo "edge config not found at $CONF" >&2
  exit 1
fi

if grep -q 'maf_connection_upgrade' "$CONF"; then
  echo "edge already passes websockets through"
else
  BACKUP="$CONF.bak-$(date +%Y%m%d-%H%M%S)"
  cp "$CONF" "$BACKUP"
  echo "==> edge config backed up to $BACKUP"

  # The map has to sit outside a server block, so it goes at the top of the
  # file. `Connection` is only "upgrade" when the client asked for it —
  # sending it on every request would confuse the upstream.
  TMP="$CONF.tmp"
  {
    cat <<'MAP'
map $http_upgrade $maf_connection_upgrade {
    default upgrade;
    ''      close;
}

MAP
    awk -v marker="$LOCATION_MARKER" '
      $0 == marker {
        print
        print "        proxy_http_version 1.1;"
        print "        proxy_set_header Upgrade $http_upgrade;"
        print "        proxy_set_header Connection $maf_connection_upgrade;"
        print "        proxy_read_timeout 3600s;"
        print "        proxy_send_timeout 3600s;"
        next
      }
      { print }
    ' "$CONF"
  } > "$TMP"

  if ! grep -q 'proxy_set_header Upgrade' "$TMP"; then
    echo "the ma-famille API location was not found in $CONF — nothing changed" >&2
    rm -f "$TMP"
    exit 1
  fi

  mv "$TMP" "$CONF"
  echo "==> edge config now passes websockets through"
fi

# The running container has the file mounted, so it only needs the reload.
if podman exec "$CONTAINER" nginx -t 2>/dev/null; then
  podman exec "$CONTAINER" nginx -s reload
  echo "==> edge reloaded"
else
  echo "WARNING: nginx did not like the new config — the file is unchanged for now" >&2
  exit 1
fi
