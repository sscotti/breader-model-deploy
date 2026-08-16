# Inference API (deploy summary)

Full contract lives in the **dev repo** at `inference/API_CONTRACT.md`. This page covers what
operators need for the pull-only stack.

## Endpoints

Public entry (browser / remote): **HTTPS** via Caddy on **`https://breader.medinformatics.eu/`** (optional HTTP Basic Auth).

| URL | Purpose |
| --- | --- |
| `https://127.0.0.1:8443/healthz` | Liveness + `embedding_backend`, `retrieval_kinds`, CXAS status |
| `https://127.0.0.1:8443/metadata` | Artifact profile, model dirs, retrieval options |
| `https://127.0.0.1:8443/predict` | DICOM or PNG → heads + neighbors |
| `https://127.0.0.1:8443/docs` | OpenAPI / Swagger |
| `https://127.0.0.1:8443/` | Gradio UI |

Orthanc on the Docker network still uses plain **`http://inference:7860`** (no TLS/auth).
Host port `7860` is bound to **localhost only** for debugging.

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

## Example (through Caddy)

Use `-k` for a self-signed origin cert. Add `-u user:pass` when `CADDY_BASIC_AUTH=true`:

```bash
curl -sk -u breader:'your-long-password' \
  -X POST https://breader.medinformatics.eu/predict \
```
  -F "file=@study.dcm" \
  -F "top_k=3" \
  -F "retrieval_embedding=ark-1376" | jq .
```

Localhost debug (no auth; not published on the LAN):

```bash
curl -s -X POST http://127.0.0.1:7860/predict \
  -F "file=@study.dcm" \
  -F "top_k=3" \
  -F "retrieval_embedding=ark-1376" | jq .
```
