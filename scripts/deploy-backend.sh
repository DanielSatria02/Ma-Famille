#!/usr/bin/env bash
# Deploy the backend over SSH. Used both locally and by GitHub Actions
# (deploy.yml).
# In CI, DEPLOY_HOST=prod is an ssh alias via cloudflared, plus TUNNEL_* env.
#
# Usage:
#   DEPLOY_HOST=be-ssh.rzidinc.com DEPLOY_USER=deploy DEPLOY_APP_DIR=/home/deploy/ma-famille \
#     bash scripts/deploy-backend.sh
# Env: DEPLOY_HOST, DEPLOY_USER, DEPLOY_APP_DIR, SSH_OPTS,
#      DOKU_CLIENT_ID, DOKU_SECRET_KEY, DOKU_BASE_URL, MANAGER_PASSWORD
set -euo pipefail

DEPLOY_HOST="${DEPLOY_HOST:-be-ssh.rzidinc.com}"
DEPLOY_USER="${DEPLOY_USER:-deploy}"
DEPLOY_APP_DIR="${DEPLOY_APP_DIR:-/home/deploy/ma-famille}"
SSH_OPTS="${SSH_OPTS:-}"

SSH="ssh $SSH_OPTS $DEPLOY_USER@$DEPLOY_HOST"
SCP="scp $SSH_OPTS"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARBALL="/tmp/mafamille-app.tgz"

echo "==> pack HEAD -> $TARBALL"
git -C "$REPO_ROOT" archive --format=tar.gz -o "$TARBALL" HEAD

# The DOKU keys live in the server's backend/.env, not in the repository. When
# CI has them (as secrets) they are written into that file before the stack
# starts, so the checkout on the server is never the place a key has to be
# typed. The file is rewritten in place: the rest of the server's settings
# (database URL, manager token) live there too and must not be lost.
#
# Nothing is written when the secrets are absent, so a local deploy with no
# DOKU keys leaves the server's file exactly as it was.
if [ -n "${DOKU_CLIENT_ID:-}${DOKU_SECRET_KEY:-}${MANAGER_PASSWORD:-}" ]; then
  echo "==> write the secrets into backend/.env on the server"
  # The values travel base64-encoded over stdin, together with the script
  # that writes them. A secret pasted into the ssh command line shows up in
  # the process list of every user on the machine, and a stray quote in it
  # would break the command it is embedded in.
  PAYLOAD="$(mktemp)"
  {
    printf "export APP_DIR='%s'\n" "$DEPLOY_APP_DIR"
    if [ -n "${DOKU_CLIENT_ID:-}" ] && [ -n "${DOKU_SECRET_KEY:-}" ]; then
      printf 'export DOKU_CLIENT_ID=%s\n' "$(printf '%s' "$DOKU_CLIENT_ID" | base64 | tr -d '\n')"
      printf 'export DOKU_SECRET_KEY=%s\n' "$(printf '%s' "$DOKU_SECRET_KEY" | base64 | tr -d '\n')"
      printf 'export DOKU_BASE_URL=%s\n' "$(printf '%s' "${DOKU_BASE_URL:-https://api-sandbox.doku.com}" | base64 | tr -d '\n')"
    fi
    if [ -n "${MANAGER_PASSWORD:-}" ]; then
      printf 'export MANAGER_PASSWORD=%s\n' "$(printf '%s' "$MANAGER_PASSWORD" | base64 | tr -d '\n')"
    fi
    cat <<'REMOTE'
set -e
ENV_FILE="$APP_DIR/backend/.env"
touch "$ENV_FILE"
decode() { printf '%s' "$1" | base64 -d; }
set_key() {
  KEY="$1"
  VALUE="$2"
  if grep -q "^${KEY}=" "$ENV_FILE"; then
    # sed cannot hold an arbitrary value safely, so the line is replaced by
    # rewriting the file around it.
    TMP_FILE="$ENV_FILE.tmp"
    while IFS= read -r line; do
      case "$line" in
        "${KEY}="*) printf '%s=%s\n' "$KEY" "$VALUE" >> "$TMP_FILE" ;;
        *) printf '%s\n' "$line" >> "$TMP_FILE" ;;
      esac
    done < "$ENV_FILE" > "$TMP_FILE"
    mv "$TMP_FILE" "$ENV_FILE"
  else
    printf '%s=%s\n' "$KEY" "$VALUE" >> "$ENV_FILE"
  fi
}
if [ -n "${DOKU_CLIENT_ID:-}" ] && [ -n "${DOKU_SECRET_KEY:-}" ]; then
  set_key DOKU_CLIENT_ID "$(decode "$DOKU_CLIENT_ID")"
  set_key DOKU_SECRET_KEY "$(decode "$DOKU_SECRET_KEY")"
  set_key DOKU_BASE_URL "$(decode "$DOKU_BASE_URL")"
fi
if [ -n "${MANAGER_PASSWORD:-}" ]; then
  set_key MANAGER_PASSWORD "$(decode "$MANAGER_PASSWORD")"
fi
chmod 600 "$ENV_FILE"
echo "DOKU keys written to backend/.env"
REMOTE
  } > "$PAYLOAD"
  # shellcheck disable=SC2086
  $SSH "sh -s" < "$PAYLOAD"
  rm -f "$PAYLOAD"
fi

echo "==> deliver ke $DEPLOY_USER@$DEPLOY_HOST:$DEPLOY_APP_DIR"
# shellcheck disable=SC2086
$SSH "mkdir -p '$DEPLOY_APP_DIR'"
# shellcheck disable=SC2086
$SCP "$TARBALL" "$DEPLOY_USER@$DEPLOY_HOST:$DEPLOY_APP_DIR/app.tgz"

echo "==> deploy di server (podman compose up -d --build)"
# shellcheck disable=SC2086
$SSH "DEPLOY_APP_DIR='$DEPLOY_APP_DIR' sh -s" <<'EOF'
set -e
cd "$DEPLOY_APP_DIR"
tar xzf app.tgz && rm app.tgz
if podman compose version >/dev/null 2>&1; then COMPOSE="podman compose"; else COMPOSE="podman-compose"; fi
# Down dulu: compose lama kadang keep container stale.
$COMPOSE -f docker-compose.yml -f compose.prod.yml down 2>/dev/null || true
$COMPOSE -f docker-compose.yml -f compose.prod.yml up -d --build
if command -v curl >/dev/null; then FETCH="curl -fsS"; else FETCH="wget -q -O /dev/null"; fi
i=0
while [ $i -lt 30 ]; do
  if $FETCH http://127.0.0.1:8000/ma-famille/v1/health >/dev/null; then
    echo "prod api healthy"
    break
  fi
  sleep 2
  i=$((i + 1))
done
if [ "$i" -ge 30 ]; then
  echo "prod stack never became healthy" >&2
  $COMPOSE -f docker-compose.yml -f compose.prod.yml logs --tail=50 api
  exit 1
fi

# Seed demo data so a fresh prod DB isn't an empty venue list. Idempotent:
# app.db.seed exits quietly ("already seeded") if the demo venue exists, so a
# repeat deploy never duplicates rows. Set SEED_DB=0 to skip on a deploy.
if [ "${SEED_DB:-1}" != "0" ]; then
  echo "==> seed demo data (SEED_DB=${SEED_DB:-1})"
  $COMPOSE -f docker-compose.yml -f compose.prod.yml exec -T api python -m app.db.seed
fi
EOF

echo "==> prune old images"
# shellcheck disable=SC2086
$SSH 'podman image prune -f' || true

echo "OK: backend live. Cek: curl http://127.0.0.1:8000/ma-famille/v1/health (di server)"
