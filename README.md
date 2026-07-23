# B-reader model deploy (pull-only)

Self-contained folder to run the **B-reader CXR stack** from pre-built Docker Hub images — no
clone of the full training repo required.

**GitHub:** [github.com/sscotti/breader-model-deploy](https://github.com/sscotti/breader-model-deploy)


| Service                | Image                         | Visibility                       |
| ---------------------- | ----------------------------- | -------------------------------- |
| CXAS preprocess API    | `sdscotti/cxr-preprocess-api` | Public                           |
| Ark inference + Gradio | `sdscotti/breader-inference`  | **Private** (Hub login required) |
| Orthanc + ILO plugin   | `sdscotti/orthanc-breader`    | Public                           |




## What you get (current stack)

- **DICOM or PNG** upload → CXAS anatomy-aware preprocessing → **Ark** embedding
- **Ten classifier heads** (Q2A, Q3A, normal vs not, pleural screen/face/diaphragm, profusion 0–3,
full ILO category, small-opacity type, large-opacity stage)
- **Neighbor retrieval** from training dataset .png images.  Default **Ark (1376-D)**; optional Google ELIXR / contrastive spaces in the UI (see [API.md](API.md))
- **Orthanc** ILO plugin → multi-page PDF report attached to the study

Although the GitHub repo is public, you will need a  DOCKER_HUB_TOKEN from the developer to pull the inference image from Docker Hub.

Models, neighbor PNGs, Ark weights, and bundled heads ship **inside** the inference image.
CXAS UNet weights download on first start (or seed via `cxas/weights/`).

## What ships in this folder

```text
breader-model-deploy/
  docker-compose.yml      # pull + run (no build:)
  .env.sample             # copy → .env
  pull.sh                 # docker login + compose pull
  API.md                  # predict / heads summary for operators
  cxas/weights/           # optional UNet seed (see README there)
  orthanc/
    config/               # orthanc.json, ohif.js
    python/               # ILO PDF plugin (mounted into Orthanc container)
    data/worklists/       # DICOM worklist drop folder
```



## Requirements

- Docker Engine 24+ and Docker Compose v2
- **Docker Desktop → Settings → Resources → Memory: 12 GB+** (inference + CXAS on CPU)
- ~15 GB free disk (images + CXAS weights + Orthanc data)
- **Read access** to private repo `sdscotti/breader-inference` (Hub read token DOCKER_HUB_TOKEN  from maintainer)



## Quick start

```bash
cd breader-model-deploy
cp .env.sample .env
# Edit .env: set DOCKER_HUB_TOKEN (read-only PAT)

./pull.sh
docker compose up -d
```

Open:

- **Inference UI / API:** [http://127.0.0.1:7860/](http://127.0.0.1:7860/)
- **Orthanc:** [http://127.0.0.1:8042/](http://127.0.0.1:8042/)

First CXAS start may take several minutes while UNet weights download (unless seeded).

## Verify

```bash
docker compose ps
curl -sS http://127.0.0.1:8081/health
curl -sS http://127.0.0.1:7860/healthz | jq '{status, embedding_backend, retrieval_kinds}'
curl -sS http://127.0.0.1:8042/system
```

Upload a DICOM in the Gradio UI or see [API.md](API.md) for `curl` examples.

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
INFER_IMAGE=sdscotti/breader-inference:2026-06-17
CXAS_API_IMAGE=sdscotti/cxr-preprocess-api:2026-06-17
ORTHANC_IMAGE=sdscotti/orthanc-breader:2026-06-17
```

Then `./pull.sh && docker compose up -d --force-recreate`.

## Troubleshooting


| Symptom                                                         | Fix                                                                                                                                                 |
| --------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `pull access denied` on inference                               | `docker login` with read token; confirm access to private repo                                                                                      |
| Gradio **“Connection to the server was lost”** on Run Inference | Usually **OOM** (exit 137). Raise Docker Desktop memory to **12 GB+**; keep retrieval on **Ark**; `docker compose up -d --force-recreate inference` |
| Inference restarts in a loop                                    | `docker compose logs inference --tail 50`; check OOM in `docker events`                                                                             |
| Inference starts before CXAS ready                              | Wait for `cxas-api` healthy; restart inference                                                                                                      |
| CXAS slow first boot                                            | Normal; or add `UNet_ResNet50_default.pth` under `cxas/weights/`                                                                                    |
| Old model after maintainer push                                 | `./pull.sh && docker compose up -d --force-recreate`                                                                                                |
| Port in use                                                     | Change `*_HOST_PORT` in `.env`                                                                                                                      |
| `orthanc-ilo` name already in use                               | `docker rm -f orthanc-ilo` then `docker compose up -d`                                                                                              |



## Upstream resources

This stack builds on the following public models and tools (weights and packaging are separate; see each project’s license / access terms):

| Resource | Role in this deploy |
| -------- | ------------------- |
| [Ark / Ark+](https://github.com/jlianglab/Ark) (jlianglab) | Swin-Large CXR foundation encoder used for **1376-D embeddings** and the primary classifier / neighbor space |
| [Google CXR Foundation (ELIXR)](https://huggingface.co/google/cxr-foundation/tree/main) | Optional **ELIXR** embedding backends and retrieval spaces in the Gradio UI ([Health AI Developer Foundations](https://developers.google.com/health-ai-developer-foundations) terms apply on Hugging Face) |
| [Chest X-Ray Anatomy Segmentation (CXAS)](https://github.com/ConstantinSeibold/ChestXRayAnatomySegmentation) | Anatomy segmentation used by the **preprocess API** (crop / lung-aware normalization before embed) |

Ark checkpoint used here: `Ark6_swinLarge768_ep50` (request / download via the Ark project’s published channels). CXAS UNet weights are fetched on first container start or seeded under `cxas/weights/`.

### Training data

Labeled chest radiographs used to train the classifier heads were obtained through the
[NIOSH B Reader Program](https://www.cdc.gov/niosh/chestradiography/php/about/), including images
associated with the NIOSH [Chest Image Reposiory](https://archive.cdc.gov/www_cdc_gov/niosh/topics/chestradiography/repository.html). NIOSH does not endorse this software; any classification outputs are
research / decision-support only and are not a substitute for a certified B Reader.

## Maintainers (build + push from dev repo)

From the **full HuggingFaceCXR** repository root (not this folder):

```bash
# 1. Refresh bundled heads + neighbor indices
python inference/scripts/prepare_artifacts.py --profile ark_1376_8bit

# 2. Build all three images
docker compose build

# 3. Tag + push (example)
docker push sdscotti/cxr-preprocess-api:latest
docker push sdscotti/breader-inference:latest
docker push sdscotti/orthanc-breader:latest

# 4. Sync this deploy folder if orthanc plugin or compose changed, then:
cd breader-model-deploy && git add -A && git commit && git push
```

Inference image uses `inference/Dockerfile` (unified Ark + ELIXR embed backends).
Collaborators only need **this** folder + Docker + Hub token.

Zip or share `breader-model-deploy/` with collaborators; they never need the training tree.