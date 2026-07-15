# Inference API (deploy summary)

Full contract lives in the **dev repo** at `inference/API_CONTRACT.md`. This page covers what
operators need for the pull-only stack.

## Endpoints

| URL | Purpose |
| --- | --- |
| `GET /healthz` | Liveness + `embedding_backend`, `retrieval_kinds`, CXAS status |
| `GET /metadata` | Artifact profile, model dirs, retrieval options |
| `POST /predict` | DICOM or PNG → heads + neighbors |
| `GET /docs` | OpenAPI / Swagger |

## `POST /predict`

**Content-Type:** `multipart/form-data`

| Field | Required | Default | Notes |
| --- | --- | --- | --- |
| `file` | yes | — | PNG or DICOM |
| `top_k` | no | 3 | Neighbor count (1–10 in UI) |
| `retrieval_embedding` | no | `ark-1376` | `ark-1376`, `elixr-768`, or `elixr-contrastive-img` |
| `include_neighbor_thumbnails` | no | false | Base64 JPEG per neighbor (Orthanc PDF uses this) |

**Classifier heads** (always Ark 1376-D embeddings):

| Key | Summary label |
| --- | --- |
| `q2a` | Q2A — any small opacity |
| `q3a` | Q3A — any pleural abnormality |
| `normal_vs_not` | Strict normal vs not-normal |
| `pleural_calc_any` | Pleural calc — screen (any site) |
| `pleural_calc_face` | Pleural calc (face) |
| `profusion_0_3` | Small opacity profusion (0–3) |
| `profusion_full_category` | Full ILO small-opacity category |
| `small_opacities_multiclass` | Small opacity type (pure cohort) |
| `large_opacity_stage` | Large opacity stage |

Neighbor search uses the selected **retrieval** space (default Ark). Google spaces load
TensorFlow on first use and need extra RAM.

## Example

```bash
curl -s -X POST http://127.0.0.1:7860/predict \
  -F "file=@study.dcm" \
  -F "top_k=3" \
  -F "retrieval_embedding=ark-1376" | jq .
```
