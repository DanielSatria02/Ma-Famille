"""Which API routes has the frontend never called?

Compares the OpenAPI paths against the strings in frontend/src, treating a
`{param}` segment as a wildcard. Run from the repo root:

    curl -s http://localhost:8000/openapi.json > /tmp/openapi.json
    .venv/bin/python backend/scripts/coverage_scan.py
"""

import json
import pathlib
import re

spec = json.load(open("/tmp/openapi.json"))
frontend = "".join(
    path.read_text()
    for path in pathlib.Path("frontend/src").rglob("*")
    if path.suffix in (".js", ".vue")
)

routes = [
    (method.upper(), path)
    for path, operations in spec["paths"].items()
    for method in operations
    if method in ("get", "post", "patch", "put", "delete")
]


def pattern_for(path: str) -> str:
    parts = [r"[^/]*" if part.startswith("{") else re.escape(part) for part in path.split("/")]
    return "/".join(parts)


missing = [
    f"{method:6} {path}"
    for method, path in sorted(routes, key=lambda route: route[1])
    if not re.search(pattern_for(path), frontend)
]

print(f"endpoints: {len(routes)}")
print(f"no frontend caller: {len(missing)}")
for row in missing:
    print(" ", row)
