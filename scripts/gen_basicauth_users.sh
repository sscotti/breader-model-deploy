#!/usr/bin/env bash
# Add or update a Caddy basic_auth user (bcrypt hash).
#
# Usage (from breader-model-deploy/):
#   ./scripts/gen_basicauth_users.sh breader 'your-long-password'
#   ./scripts/gen_basicauth_users.sh alice 'other-secret'   # append / replace same user
#
# Writes auth/users.basicauth — one "username bcrypt_hash" per line.
# Never commit this file or plaintext passwords.
#
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AUTH_DIR="${ROOT}/auth"
OUT="${AUTH_DIR}/users.basicauth"
CADDY_IMAGE="${CADDY_IMAGE:-caddy:2-alpine}"

USER_NAME="${1:-}"
PASSWORD="${2:-}"

if [[ -z "${USER_NAME}" || -z "${PASSWORD}" ]]; then
  echo "Usage: $0 <username> '<password>'" >&2
  exit 1
fi

if [[ "${#PASSWORD}" -lt 12 ]]; then
  echo "WARNING: password is shorter than 12 characters; prefer a longer secret." >&2
fi

mkdir -p "${AUTH_DIR}"

hash_password() {
  local plain="$1"
  if command -v caddy >/dev/null 2>&1; then
    caddy hash-password --plaintext "${plain}"
    return
  fi
  # Prefer project venv, then PATH python3 (passlib or bcrypt).
  local py=""
  if [[ -x "${ROOT}/../.venv/bin/python" ]]; then
    py="${ROOT}/../.venv/bin/python"
  elif [[ -x "${ROOT}/.venv/bin/python" ]]; then
    py="${ROOT}/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    py="$(command -v python3)"
  fi
  if [[ -n "${py}" ]]; then
    local py_hash
    py_hash="$(
      PASSWORD_PLAIN="${plain}" "${py}" - <<'PY'
import os, sys
pw = os.environ["PASSWORD_PLAIN"]
try:
    from passlib.hash import bcrypt as passlib_bcrypt
    print(passlib_bcrypt.using(rounds=14).hash(pw))
    sys.exit(0)
except Exception:
    pass
try:
    import bcrypt
    print(bcrypt.hashpw(pw.encode(), bcrypt.gensalt(rounds=14)).decode())
    sys.exit(0)
except Exception as e:
    print(f"python-bcrypt-failed: {e}", file=sys.stderr)
    sys.exit(1)
PY
    )" && [[ -n "${py_hash}" ]] && { echo "${py_hash}"; return; }
  fi
  if command -v docker >/dev/null 2>&1; then
    docker run --rm "${CADDY_IMAGE}" caddy hash-password --plaintext "${plain}"
    return
  fi
  echo "ERROR: need local 'caddy', Python bcrypt/passlib, or Docker for: caddy hash-password" >&2
  exit 1
}

echo "Hashing password for user '${USER_NAME}'..."
HASH="$(hash_password "${PASSWORD}" | tr -d '\r\n')"
if [[ -z "${HASH}" || "${HASH}" != \$2* ]]; then
  echo "ERROR: unexpected hash output (expected bcrypt \$2a/\$2b): ${HASH}" >&2
  exit 1
fi

touch "${OUT}"
TMP="$(mktemp)"
trap 'rm -f "${TMP}"' EXIT
# Drop existing line for this user, then append.
awk -v u="${USER_NAME}" '$1 != u { print }' "${OUT}" >"${TMP}" || true
printf '%s %s\n' "${USER_NAME}" "${HASH}" >>"${TMP}"
mv "${TMP}" "${OUT}"
chmod 600 "${OUT}"
trap - EXIT

echo "Updated ${OUT}"
echo "Users now:"
awk '{ print "  - " $1 }' "${OUT}"
echo "Restart Caddy after changes: docker compose up -d --force-recreate caddy"
