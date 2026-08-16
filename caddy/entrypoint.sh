#!/bin/sh
# Fail fast if TLS certs are missing. Basic Auth users are required only when enabled.
set -eu

CERT=/etc/caddy/certs/localhost.crt
KEY=/etc/caddy/certs/localhost.key
USERS=/etc/caddy/auth/users.basicauth

AUTH_RAW="${CADDY_BASIC_AUTH:-true}"
AUTH_ON=1
case "$(printf '%s' "$AUTH_RAW" | tr '[:upper:]' '[:lower:]')" in
  0|false|no|off) AUTH_ON=0 ;;
esac

HOST="${CADDY_HOSTNAME:-}"
if [ -n "$HOST" ]; then
  cat >/tmp/caddy-hostgate.inc <<EOF
	@foreign not host ${HOST}
	handle @foreign {
		respond "Use https://${HOST}/" 421
	}
EOF
else
  echo "	# no host lock (CADDY_HOSTNAME empty)" >/tmp/caddy-hostgate.inc
fi

if [ "$AUTH_ON" -eq 1 ]; then
  AUTH_BLOCK='
		forward_auth authgate:9090 {
			uri /verify
			header_up X-Real-IP {remote_host}
			copy_headers Remote-User
		}'
else
  AUTH_BLOCK='
		# Basic Auth disabled (CADDY_BASIC_AUTH=false)'
fi

cat >/tmp/caddy-site.inc <<EOF
	handle {
${AUTH_BLOCK}
		reverse_proxy inference:7860 {
			flush_interval -1
		}
	}
EOF

if [ ! -f "$CERT" ] || [ ! -f "$KEY" ]; then
  echo "ERROR: missing TLS cert/key at $CERT / $KEY" >&2
  echo "On the host, from breader-model-deploy/:  EXTRA_DNS=breader.medinformatics.eu ./scripts/gen_localhost_certs.sh" >&2
  exit 1
fi

if [ "$AUTH_ON" -eq 1 ]; then
  if [ ! -f "$USERS" ] || [ ! -s "$USERS" ]; then
    echo "ERROR: missing or empty basic-auth users file at $USERS" >&2
    echo "On the host, from breader-model-deploy/:  ./scripts/gen_basicauth_users.sh breader 'your-long-password'" >&2
    echo "Or set CADDY_BASIC_AUTH=false to serve without a password." >&2
    exit 1
  fi
fi

echo "Caddy host=${HOST:-*} basic_auth=$AUTH_ON listen=:8443" >&2
exec caddy run --config /etc/caddy/Caddyfile --adapter caddyfile
