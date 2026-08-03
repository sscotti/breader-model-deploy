#!/bin/sh
# Fail fast with a clear message if TLS certs or basic-auth users are missing.
set -eu

CERT=/etc/caddy/certs/localhost.crt
KEY=/etc/caddy/certs/localhost.key
USERS=/etc/caddy/auth/users.basicauth

if [ ! -f "$CERT" ] || [ ! -f "$KEY" ]; then
  echo "ERROR: missing TLS cert/key at $CERT / $KEY" >&2
  echo "On the host, from breader-model-deploy/:  ./scripts/gen_localhost_certs.sh" >&2
  exit 1
fi

if [ ! -f "$USERS" ] || [ ! -s "$USERS" ]; then
  echo "ERROR: missing or empty basic-auth users file at $USERS" >&2
  echo "On the host, from breader-model-deploy/:  ./scripts/gen_basicauth_users.sh breader 'your-long-password'" >&2
  exit 1
fi

exec caddy run --config /etc/caddy/Caddyfile --adapter caddyfile
