"""Add the websocket headers to one location of the shared edge config.

The API has a websocket route — the payment page is told the moment a
booking settles — but the shared edge config proxies without the upgrade
headers, so the request arrived as a plain GET and the API answered 404.
The page then sat there saying "reconnecting" for a socket that could
never open.

The edge file is shared by every app on this host, so this only touches
the ma-famille API block and only adds to it.

Usage: python3 scripts/patch_edge_websocket.py /home/deploy/edge/nginx.conf
"""

import re
import shutil
import sys
import time

LOCATION = re.compile(r"(location\s+\^~\s+/ma-famille/v1/\s*\{)")

MAP = (
    "map $http_upgrade $maf_connection_upgrade {\n"
    "    default upgrade;\n"
    "    ''      close;\n"
    "}\n\n"
)

HEADERS = (
    "\n        proxy_http_version 1.1;"
    "\n        proxy_set_header Upgrade $http_upgrade;"
    "\n        proxy_set_header Connection $maf_connection_upgrade;"
    "\n        proxy_read_timeout 3600s;"
    "\n        proxy_send_timeout 3600s;"
)


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: patch_edge_websocket.py <nginx.conf>", file=sys.stderr)
        return 2

    path = sys.argv[1]

    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    if "maf_connection_upgrade" in text:
        print("edge already passes websockets through")
        return 0

    backup = f"{path}.bak-{time.strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(path, backup)
    print(f"==> edge config backed up to {backup}")

    # The `map` has to sit outside a server block, so it goes at the top of
    # the file. `Connection` is only "upgrade" when the client asked for it —
    # sending it on every request confuses the upstream.
    text = MAP + text

    # The ma-famille API location, matched on what it says rather than on
    # how it is spaced: the shared file is written by hand and the
    # indentation is not a promise.
    match = LOCATION.search(text)
    if not match:
        print("the ma-famille API location was not found — nothing changed", file=sys.stderr)
        return 1

    text = text[: match.end()] + HEADERS + text[match.end() :]

    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)

    print("==> the ma-famille API location now passes websockets through")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
