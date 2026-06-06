#!/usr/bin/env bash
# Pull all stack images (logs into Docker Hub when DOCKER_HUB_TOKEN is set in .env).
set -euo pipefail
cd "$(dirname "$0")"
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi
if [[ -n "${DOCKER_HUB_TOKEN:-}" ]]; then
  echo "Logging into Docker Hub as ${DOCKER_HUB_USERNAME:-sdscotti}..."
  echo "$DOCKER_HUB_TOKEN" | docker login -u "${DOCKER_HUB_USERNAME:-sdscotti}" --password-stdin
fi
docker compose pull "$@"
