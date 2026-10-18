"""What product gaps are still open? Rough but evidence-based.

Run from the repo root: .venv/bin/python backend/scripts/gap_scan.py
"""

import json
import pathlib
import re

ROOTS = {
    "backend": pathlib.Path("backend/app"),
    "frontend": pathlib.Path("frontend/src"),
    "docs": pathlib.Path("docs"),
}
FILES = {
    name: [p for p in root.rglob("*") if p.suffix in (".py", ".js", ".vue", ".md", ".css")]
    for name, root in ROOTS.items()
}


def hits(needle: str, where=("backend", "frontend")) -> list[str]:
    out = []
    for name in where:
        for path in FILES[name]:
            if needle in path.read_text():
                out.append(f"{name}/{path.name}")
    return sorted(set(out))


CHECKS = {
    "refund flow": ["refund"],
    "failed-payment persistence": ['status = "failed"', "'failed'"],
    "venue/facility photo": ["image_url", "photo_url"],
    "promo / voucher": ["promo", "voucher", "discount"],
    "i18n (multi-language UI)": ["vue-i18n", "i18n"],
    "audit trail": ["audit", "created_by", "X-Actor"],
    "rate limit on login": ["slowapi", "ratelimit", "RateLimit"],
    "list pagination": ["offset", "per_page", "page_size"],
    "CSV / report export": ["csv", "export"],
    "customer accounts": ["customer_password", "customer_token"],
}

print("=== feature probes ===")
for label, needles in CHECKS.items():
    found = sorted({hit for needle in needles for hit in hits(needle)})
    print(f"{label:28} {'FOUND in ' + ', '.join(found[:4]) if found else 'not implemented'}")

package = json.loads(pathlib.Path("frontend/package.json").read_text())
dev = package.get("devDependencies", {})
print()
print("=== frontend testing ===")
RUNNERS = ("vitest", "jest", "playwright", "@playwright/test")
print("test runner:", [name for name in dev if name in RUNNERS] or "none")
print("scripts:", package.get("scripts"))

print()
print("=== python test files ===")
tests = sorted(p.name for p in pathlib.Path("backend/tests").glob("test_*.py"))
print(f"{len(tests)} files")

print()
print("=== leftover TODO markers ===")
for name in ("backend", "frontend"):
    for path in FILES[name]:
        for match in re.finditer(r"TODO|FIXME", path.read_text()):
            line = path.read_text()[: match.start()].count("\n") + 1
            print(f"{path}:{line}")
