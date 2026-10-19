#!/usr/bin/env bash
# Put the manager dashboard password into the repository's Actions secrets.
#
# The password is read from backend/.env so it is never typed here and never
# printed. It is the one password that opens the manager door.
#
# Usage: bash scripts/set-manager-secret.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$REPO_ROOT/backend/.env"

if [ ! -f "$ENV_FILE" ]; then
  echo "no $ENV_FILE — nothing to read" >&2
  exit 1
fi

PASSWORD=$(grep '^MANAGER_PASSWORD=' "$ENV_FILE" | head -1 | cut -d= -f2-)

if [ -z "$PASSWORD" ]; then
  echo "MANAGER_PASSWORD is missing in $ENV_FILE" >&2
  exit 1
fi

printf '%s' "$PASSWORD" | gh secret set MANAGER_PASSWORD
echo "==> MANAGER_PASSWORD"
gh secret list | grep MANAGER_PASSWORD
