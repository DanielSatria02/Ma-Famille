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

  python3 - "$CONF" <<'PY'
  import re
  import sys

  path = sys.argv[1]
  with open(path, encoding="utf-8") as handle:
      text = handle.read()

  # The `map` has to sit outside a server block, so it goes at the top of
  # the file. `Connection` is only "upgrade" when the client asked for it —
  # sending it on every request confuses the upstream.
  text = (
      "map $http_upgrade $maf_connection_upgrade {\n"
      "    default upgrade;\n"
      "    ''      close;\n"
      "}\n\n" + text
  )

  # The ma-famille API location, matched on what it says rather than on how
  # it is spaced: the shared file is written by hand and the indentation is
  # not a promise.
  pattern = re.compile(r"(location\s+\^~\s+/ma-famille/v1/\s*\{)")
  match = pattern.search(text)
  if not match:
      print("the ma-famille API location was not found — nothing changed", file=sys.stderr)
      raise SystemExit(1)

  added = (
      "\n        proxy_http_version 1.1;"
      "\n        proxy_set_header Upgrade $http_upgrade;"
      "\n        proxy_set_header Connection $maf_connection_upgrade;"
      "\n        proxy_read_timeout 3600s;"
      "\n        proxy_send_timeout 3600s;"
  )
  text = text[: match.end()] + added + text[match.end() :]

  with open(path, "w", encoding="utf-8") as handle:
      handle.write(text)
  print("==> the ma-famille API location now passes websockets through")
  PY

  echo "==> edge config written"
fi

# The running container has the file mounted, so it only needs the reload.
if podman exec "$CONTAINER" nginx -t 2>/dev/null; then
  podman exec "$CONTAINER" nginx -s reload
  echo "==> edge reloaded"
else
  echo "WARNING: nginx did not like the new config — the file is unchanged for now" >&2
  exit 1
fi
