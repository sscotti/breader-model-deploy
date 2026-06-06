# B-reader model deploy (pull-only)

Self-contained folder to run the **B-reader CXR stack** from pre-built Docker Hub images — no
clone of the full training repo required.

| Service | Image | Visibility |
| --- | --- | --- |
| CXAS preprocess API | `sdscotti/cxr-preprocess-api` | Public |
| Ark inference + Gradio | `sdscotti/breader-inference` | **Private** (Hub login required) |
| Orthanc + ILO plugin | `sdscotti/orthanc-breader` | Public |

## What ships in this folder

```text
breader-model-deploy/
  docker-compose.yml      # pull + run (no build:)
  .env.sample             # copy → .env
  cxas/weights/           # optional UNet seed (see README there)
  orthanc/
    config/               # orthanc.json, ohif.js
    python/               # ILO PDF plugin (mounted into Orthanc container)
    data/worklists/       # DICOM worklist drop folder
```

Models, neighbor PNGs, and Ark weights are **inside** the inference image. CXAS segmentation
weights download on first start (or seed via `cxas/weights/`).

## Requirements

- Docker Engine 24+ and Docker Compose v2
- ~12–15 GB free disk (images + CXAS weights + Orthanc data)
- **Read access** to private repo `sdscotti/breader-inference` (ask maintainer for a Hub read token)

## Quick start

```bash
cd breader-model-deploy
cp .env.sample .env
# Edit .env: set DOCKER_HUB_TOKEN (read-only PAT from sdscotti)

echo "$DOCKER_HUB_TOKEN" | docker login -u sdscotti --password-stdin

docker compose pull
docker compose up -d
```

Open:

- **Inference UI / API:** http://127.0.0.1:7860/
- **Orthanc:** http://127.0.0.1:8042/

First CXAS start may take several minutes while UNet weights download (unless seeded).

## Verify

```bash
docker compose ps
curl -sS http://127.0.0.1:8081/health
curl -sS http://127.0.0.1:7860/healthz
curl -sS http://127.0.0.1:8042/system
```

Upload a DICOM in the Gradio UI or POST to `/predict` (see upstream `inference/API_CONTRACT.md`
in the dev repo if needed).

## Inference-only (no Orthanc)

```bash
docker compose up -d cxas-api inference
```

## Orthanc ILO PDF button

The Python plugin under `orthanc/python/` calls `ILO_PREDICT_BASE_URL` (default
`http://inference:7860` on the compose network). In Orthanc Explorer2, expand a study →
instance list → **ILO Inference** button.

Optional plugin defaults: `orthanc/python/ilo_plugin.json` (env vars override at runtime).

## Pin a release

Set tagged images in `.env`:

```bash
INFER_IMAGE=sdscotti/breader-inference:2026-06-03
CXAS_API_IMAGE=sdscotti/cxr-preprocess-api:2026-06-03
ORTHANC_IMAGE=sdscotti/orthanc-breader:2026-06-03
```

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `pull access denied` on inference | `docker login` with read token; confirm access to private repo |
| Inference starts before CXAS ready | Wait for `cxas-api` healthy; restart inference |
| CXAS slow first boot | Normal; or add `UNet_ResNet50_default.pth` under `cxas/weights/` |
| Old model after maintainer push | `docker compose pull && docker compose up -d --force-recreate` |
| Port in use | Change `*_HOST_PORT` in `.env` |

## Maintainers (build + push from dev repo)

From repository root, with Hub names in `.env`:

```bash
CXAS_API_IMAGE=sdscotti/cxr-preprocess-api:latest
INFER_IMAGE=sdscotti/breader-inference:latest
ORTHANC_IMAGE=sdscotti/orthanc-breader:latest

docker compose build
# push via Docker Desktop or: docker push sdscotti/...
```

Zip or share this `breader-model-deploy/` folder with collaborators; they only need Docker + Hub token.
