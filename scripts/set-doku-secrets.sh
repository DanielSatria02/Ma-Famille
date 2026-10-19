#!/usr/bin/env bash
# Put the DOKU credentials into the repository's Actions secrets.
#
# The values are read from backend/.env so they are never typed here and never
# printed. The base URL is a variable, not a secret, because it is not a
# secret — it is the sandbox or production host.
#
# Usage: bash scripts/set-doku-secrets.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$REPO_ROOT/backend/.env"

if [ ! -f "$ENV_FILE" ]; then
  echo "no $ENV_FILE — nothing to read" >&2
  exit 1
fi

read_env() {
  grep "^$1=" "$ENV_FILE" | head -1 | cut -d= -f2-
}

CLIENT_ID=$(read_env DOKU_CLIENT_ID)
SECRET_KEY=$(read_env DOKU_SECRET_KEY)
BASE_URL=$(read_env DOKU_BASE_URL)
BASE_URL="${BASE_URL:-https://api-sandbox.doku.com}"

if [ -z "$CLIENT_ID" ] || [ -z "$SECRET_KEY" ]; then
  echo "DOKU_CLIENT_ID or DOKU_SECRET_KEY is missing in $ENV_FILE" >&2
  exit 1
fi

echo "==> DOKU_CLIENT_ID"
printf '%s' "$CLIENT_ID" | gh secret set DOKU_CLIENT_ID
echo "==> DOKU_SECRET_KEY"
printf '%s' "$SECRET_KEY" | gh secret set DOKU_SECRET_KEY
echo "==> DOKU_BASE_URL (variable)"
gh variable set DOKU_BASE_URL --body "$BASE_URL"

echo
echo "secrets now:"
gh secret list
echo
echo "variables now:"
gh variable list
