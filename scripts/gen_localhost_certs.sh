#!/usr/bin/env bash
# Generate self-signed TLS cert + key for local / LAN HTTPS (Caddy).
#
# Usage (from breader-model-deploy/):
#   ./scripts/gen_localhost_certs.sh
#   EXTRA_IP=192.168.1.50 ./scripts/gen_localhost_certs.sh
#   EXTRA_DNS=breader.medinformatics.eu ./scripts/gen_localhost_certs.sh
#
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CERT_DIR="${ROOT}/certs"
CRT="${CERT_DIR}/localhost.crt"
KEY="${CERT_DIR}/localhost.key"
DAYS="${CERT_DAYS:-825}"

mkdir -p "${CERT_DIR}"

if ! command -v openssl >/dev/null 2>&1; then
  echo "ERROR: openssl is required." >&2
  exit 1
fi

SAN="DNS:localhost,IP:127.0.0.1"
if [[ -n "${EXTRA_IP:-}" ]]; then
  SAN="${SAN},IP:${EXTRA_IP}"
fi
if [[ -n "${EXTRA_DNS:-}" ]]; then
  SAN="${SAN},DNS:${EXTRA_DNS}"
fi
if [[ -n "${EXTRA_DNS:-}" ]]; then
  CN_NAME="${EXTRA_DNS}"
else
  CN_NAME="localhost"
fi

TMP="$(mktemp)"
trap 'rm -f "${TMP}"' EXIT
cat >"${TMP}" <<EOF
[req]
default_bits = 2048
prompt = no
default_md = sha256
distinguished_name = dn
x509_extensions = v3_req

[dn]
CN = ${CN_NAME}
O = B-reader local deploy
OU = self-signed

[v3_req]
subjectAltName = ${SAN}
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
basicConstraints = CA:FALSE
EOF

openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout "${KEY}" \
  -out "${CRT}" \
  -days "${DAYS}" \
  -config "${TMP}"

chmod 600 "${KEY}"
chmod 644 "${CRT}"
echo "Wrote ${CRT}"
echo "Wrote ${KEY}"
echo "SAN: ${SAN}"
echo "Browser will warn until you trust this cert (expected for self-signed)."
