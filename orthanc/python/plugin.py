#!/usr/bin/env python3
"""
Orthanc Python plugin — ILO / inference integration.

- ``POST /ilo-inference`` — forward instance DICOM to inference ``POST /predict``, then
  build a multi-page PDF from the response and attach it to the study (encapsulated PDF).
  Returns a **short JSON summary** to the browser (not the full predict payload), unless
  ``return_full_predict: true`` is sent for debugging.
- ``POST /ilo-attach-pdf`` — optional manual path: attach a PDF built from a ``predict`` JSON
  you already have (same as the internal step above).

Optional config: ``ilo_plugin.json`` (or env vars — see ``load_config``): e.g. ``ilo_predict_base_url``,
``pdf_letterhead``, ``pdf_research_notice`` (page-1 disclaimer text; omit key for default, ``false``/``null``/``""`` to hide).
"""

from __future__ import annotations

import base64
import json
import logging
import os
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, Optional

PLUGIN_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PLUGIN_DIR))

try:
    import orthanc
    import requests
    from pdf_report import (
        ILO_PDF_DOCUMENT_TITLE,
        attach_pdf_to_study_create_dicom,
        build_ilo_inference_pdf_bytes,
        _resolve_orthanc_instance_id,
    )
except ImportError as e:
    logging.basicConfig(level=logging.INFO)
    logging.error("Failed to import required modules: %s", e)
    raise

CONFIG_FILE = PLUGIN_DIR / "ilo_plugin.json"
CONFIG: Dict[str, Any] = {}


def load_config() -> None:
    """Load ``ilo_plugin.json`` if present; otherwise ``CONFIG`` stays empty (env-only)."""
    global CONFIG
    try:
        if CONFIG_FILE.is_file():
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                CONFIG = json.load(f)
            if not isinstance(CONFIG, dict):
                CONFIG = {}
        else:
            CONFIG = {}
        logging.info("ILO plugin config loaded from %s (keys: %s)", CONFIG_FILE, list(CONFIG.keys()))
    except Exception as e:
        logging.error("Failed to load %s: %s", CONFIG_FILE, e)
        CONFIG = {}


def OnChange(changeType, level, resource):
    if changeType == orthanc.ChangeType.NEW_INSTANCE:
        logging.info("New instance received: %s", resource)


def OnRest(output, uri, **request):
    if uri == "/ilo-inference":
        return handle_ilo_inference_request(output, request)
    if uri == "/ilo-attach-pdf":
        return handle_ilo_attach_pdf_request(output, request)
    output.AnswerBuffer("Not found", "text/plain")


def _ilo_predict_base_url() -> Optional[str]:
    env = (os.environ.get("ILO_PREDICT_BASE_URL") or "").strip()
    if env:
        return env.rstrip("/")
    cfg = CONFIG.get("ilo_predict_base_url") or CONFIG.get("ILO_PREDICT_BASE_URL")
    if cfg is not None and str(cfg).strip():
        return str(cfg).strip().rstrip("/")
    return None


def _ilo_default_top_k() -> int:
    try:
        v = os.environ.get("ILO_TOP_K")
        if v is not None and str(v).strip():
            return max(1, int(v))
    except (TypeError, ValueError):
        pass
    try:
        return max(1, int(CONFIG.get("ilo_top_k", 3)))
    except (TypeError, ValueError):
        return 3


def _ilo_predict_timeout_sec() -> float:
    try:
        v = os.environ.get("ILO_PREDICT_TIMEOUT_SEC")
        if v is not None and str(v).strip():
            return max(5.0, float(v))
    except (TypeError, ValueError):
        pass
    try:
        return max(5.0, float(CONFIG.get("ilo_predict_timeout_sec", 180)))
    except (TypeError, ValueError):
        return 180.0


def _letterhead_from_config() -> Optional[Dict[str, Any]]:
    lh = CONFIG.get("pdf_letterhead")
    return lh if isinstance(lh, dict) else None


def _pdf_research_notice_for_build() -> Optional[str]:
    """
    Value passed to ``build_ilo_inference_pdf_bytes(..., research_notice=…)``.

    - Key ``pdf_research_notice`` absent from config → ``None`` (use ``ILO_PDF_RESEARCH_NOTICE_DEFAULT`` in pdf_report).
    - ``false`` / ``null`` / empty string → ``\"\"`` (omit disclaimer on page 1).
    - Non-empty string → custom notice text.
    """
    if "pdf_research_notice" not in CONFIG:
        return None
    v = CONFIG.get("pdf_research_notice")
    if v is False or v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    return str(v).strip()


def _ilo_pdf_use_orthanc_instance_preview() -> bool:
    """When true (default), PDF query panel uses Orthanc ``GET /instances/{id}/preview`` if it succeeds."""
    v = (os.environ.get("ILO_PDF_USE_ORTHANC_PREVIEW") or "").strip().lower()
    if v in ("0", "false", "no", "off"):
        return False
    if v in ("1", "true", "yes", "on"):
        return True
    cfg = CONFIG.get("ilo_pdf_use_orthanc_preview", True)
    if isinstance(cfg, bool):
        return cfg
    return str(cfg).strip().lower() not in ("0", "false", "no", "off")


def _orthanc_instance_preview_png_b64(instance_id: str) -> Optional[str]:
    """
    Same image as ``curl .../instances/<uuid>/preview``: Orthanc-rendered 8-bit PNG of the instance.
    Runs inside the Orthanc process, so ``RestApiGet`` hits the local REST API (no HTTP to self needed).
    """
    iid = (instance_id or "").strip()
    if not iid:
        return None
    try:
        raw = orthanc.RestApiGet(f"/instances/{iid}/preview")
        if raw is None:
            return None
        if isinstance(raw, str):
            raw = raw.encode("latin-1")
        if not isinstance(raw, (bytes, bytearray)) or len(raw) < 8:
            return None
        raw = bytes(raw)
        if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
            logging.warning(
                "ILO: Orthanc /instances/.../preview for %s did not look like PNG (got %d bytes)",
                iid[:20],
                len(raw),
            )
            return None
        return base64.b64encode(raw).decode("ascii")
    except Exception as e:
        logging.warning("ILO: Orthanc instance preview failed for %s: %s", iid[:20], e)
        return None


def _attach_ilo_pdf_from_predict(
    instance_id: str,
    predict: Dict[str, Any],
    *,
    letterhead: Optional[Dict[str, Any]] = None,
    document_title: Optional[str] = None,
) -> Dict[str, Any]:
    """Build PDF bytes from predict JSON and attach encapsulated PDF to the instance's study."""
    lh = letterhead if letterhead is not None else _letterhead_from_config()
    title = (document_title or ILO_PDF_DOCUMENT_TITLE).strip() or ILO_PDF_DOCUMENT_TITLE
    attach_title = title[:64]
    predict_pdf: Dict[str, Any] = dict(predict)
    if _ilo_pdf_use_orthanc_instance_preview():
        orth_b64 = _orthanc_instance_preview_png_b64(instance_id)
        if orth_b64:
            predict_pdf["_preview_png_b64"] = orth_b64
    pdf_bytes = build_ilo_inference_pdf_bytes(
        predict_pdf,
        instance_id=instance_id,
        document_title=title,
        letterhead=lh,
        research_notice=_pdf_research_notice_for_build(),
        plugin_dir=PLUGIN_DIR,
    )
    return attach_pdf_to_study_create_dicom(
        instance_id, pdf_bytes, document_title=attach_title
    )


def _predict_summary_for_client(predict: Dict[str, Any]) -> Dict[str, Any]:
    """Small, UI-safe summary derived from inference predict response."""
    inp = predict.get("input") or {}
    timing = predict.get("timing_ms") or {}
    preds = predict.get("predictions") or {}
    labels_out: Dict[str, Any] = {}
    if isinstance(preds, dict):
        for key in (
            "q2a",
            "q3a",
            "profusion_0_3",
            "small_opacities_multiclass",
            "large_opacity_stage",
            "pleural_calc_diaphragm",
        ):
            if key not in preds:
                continue
            p = preds[key]
            if isinstance(p, dict) and p.get("label") is not None:
                labels_out[key] = p.get("label")
    nbr = predict.get("neighbors")
    n_nbr = len(nbr) if isinstance(nbr, list) else 0
    return {
        "input_filename": inp.get("filename"),
        "image_size": inp.get("image_size"),
        "timing_ms_total": timing.get("total"),
        "timing_ms": timing if isinstance(timing, dict) else {},
        "prediction_labels": labels_out,
        "neighbor_count": n_nbr,
    }


def handle_ilo_inference_request(output, request) -> None:
    try:
        method = request.get("method") or "GET"
        if method == "GET":
            doc = {
                "route": "/ilo-inference",
                "description": (
                    "POST runs inference /predict, builds a multi-page PDF, attaches encapsulated PDF "
                    "to the study, and returns a short JSON summary (not the full model payload). "
                    "The PDF query image uses Orthanc GET /instances/{Instance}/preview when available "
                    "(same as curl …/preview), else inference _preview_png_b64 from DICOM decode."
                ),
                "config_file": "ilo_plugin.json beside plugin.py",
                "pdf_research_notice": "Optional string; false/null/empty omits the page-1 research banner.",
                "post_body": {
                    "Instance": "<Orthanc instance UUID>",
                    "top_k": "<optional>",
                    "return_full_predict": "<optional bool, default false — set true only for debugging>",
                },
                "upstream": {
                    "predict_url": f"{_ilo_predict_base_url() or '<not configured>'}/predict",
                    "contract": "inference/API_CONTRACT.md — POST /predict",
                },
            }
            output.AnswerBuffer(json.dumps(doc, indent=2), "application/json")
            return
        if method != "POST":
            output.AnswerBuffer("Method not allowed", "text/plain")
            return

        base = _ilo_predict_base_url()
        if not base:
            output.AnswerBuffer(
                json.dumps(
                    {
                        "Success": False,
                        "error": (
                            "ILO inference URL not set. Set ILO_PREDICT_BASE_URL or "
                            'ilo_plugin.json "ilo_predict_base_url".'
                        ),
                    }
                ),
                "application/json",
            )
            return

        request_body = request.get("body")
        if request_body is None:
            output.AnswerBuffer(
                json.dumps({"Success": False, "error": "Request body is required"}),
                "application/json",
            )
            return
        body_str = (
            request_body.decode("utf-8") if isinstance(request_body, bytes) else str(request_body)
        )
        try:
            body = json.loads(body_str)
        except json.JSONDecodeError as e:
            output.AnswerBuffer(
                json.dumps({"Success": False, "error": f"Invalid JSON body: {e}"}),
                "application/json",
            )
            return

        instance_id = body.get("Instance")
        if not instance_id or not str(instance_id).strip():
            output.AnswerBuffer(
                json.dumps({"Success": False, "error": "Instance is required."}),
                "application/json",
            )
            return
        instance_id = str(instance_id).strip()

        top_k = body.get("top_k", _ilo_default_top_k())
        try:
            top_k_i = max(1, int(top_k))
        except (TypeError, ValueError):
            top_k_i = _ilo_default_top_k()

        return_full = bool(body.get("return_full_predict", False))

        try:
            dicom_bytes = orthanc.RestApiGet(f"/instances/{instance_id}/file")
        except Exception as e:
            logging.error("ilo-inference: failed to read instance %s: %s", instance_id, e)
            output.AnswerBuffer(
                json.dumps(
                    {
                        "Success": False,
                        "Instance": instance_id,
                        "error": f"Could not load DICOM from Orthanc: {e}",
                    }
                ),
                "application/json",
            )
            return

        if not isinstance(dicom_bytes, (bytes, bytearray)) or len(dicom_bytes) < 132:
            output.AnswerBuffer(
                json.dumps(
                    {
                        "Success": False,
                        "Instance": instance_id,
                        "error": "Orthanc returned empty or invalid DICOM bytes.",
                    }
                ),
                "application/json",
            )
            return

        predict_url = f"{base}/predict"
        files = {"file": (f"{instance_id}.dcm", bytes(dicom_bytes), "application/dicom")}
        data = {
            "top_k": str(top_k_i),
            "include_neighbor_thumbnails": "true",
        }
        timeout = _ilo_predict_timeout_sec()

        try:
            r = requests.post(predict_url, files=files, data=data, timeout=timeout)
        except requests.RequestException as e:
            logging.error("ilo-inference: upstream request failed: %s", e)
            output.AnswerBuffer(
                json.dumps(
                    {
                        "Success": False,
                        "Instance": instance_id,
                        "error": f"Request to inference service failed: {e}",
                    }
                ),
                "application/json",
            )
            return

        if r.status_code == 200:
            try:
                payload = r.json()
            except json.JSONDecodeError:
                output.AnswerBuffer(
                    json.dumps(
                        {
                            "Success": False,
                            "Instance": instance_id,
                            "error": "Upstream returned 200 but body is not JSON.",
                        }
                    ),
                    "application/json",
                )
                return

            pdf_result: Dict[str, Any] = {}
            pdf_err: Optional[str] = None
            try:
                pdf_result = _attach_ilo_pdf_from_predict(instance_id, payload)
                if not pdf_result.get("ok"):
                    pdf_err = str(
                        pdf_result.get("error")
                        or pdf_result.get("response")
                        or "PDF attach failed"
                    )
            except Exception as e:
                logging.exception("ilo-inference: PDF build/attach failed: %s", e)
                pdf_err = str(e)
                pdf_result = {"ok": False, "error": pdf_err}

            out: Dict[str, Any] = {
                "Success": True,
                "Instance": instance_id,
                "inference": _predict_summary_for_client(payload),
                "pdf": pdf_result,
            }
            if pdf_err:
                out["message"] = f"Inference OK; PDF step failed: {pdf_err}"
            else:
                out["message"] = "ILO inference complete; PDF attached to study."
            if return_full:
                out["predict"] = payload
            output.AnswerBuffer(json.dumps(out), "application/json")
            return

        try:
            err_body = r.json()
        except json.JSONDecodeError:
            err_body = {"detail": (r.text or "")[:8000]}
        output.AnswerBuffer(
            json.dumps(
                {
                    "Success": False,
                    "Instance": instance_id,
                    "upstream_status": r.status_code,
                    "upstream": err_body,
                }
            ),
            "application/json",
        )
    except Exception as e:
        logging.error("ilo-inference: %s", e)
        logging.error(traceback.format_exc())
        output.AnswerBuffer(json.dumps({"Success": False, "error": str(e)}), "application/json")


def handle_ilo_attach_pdf_request(output, request) -> None:
    """
    POST JSON: ``{"Instance": "<uuid>", "predict": { ... }}`` — same shape as inference
    ``POST /predict`` response. Optional ``letterhead`` dict, optional ``document_title`` string.
    """
    try:
        method = request.get("method") or "GET"
        if method == "GET":
            out = {
                "route": "/ilo-attach-pdf",
                "post_body": {
                    "Instance": "<Orthanc instance UUID>",
                    "predict": "<object: inference /predict JSON>",
                    "letterhead": "<optional: Phone, Email, Website, Address, Logo>",
                    "document_title": "<optional string>",
                },
                "notes": "Creates PDF via pdf_report.build_ilo_inference_pdf_bytes and attaches encapsulated PDF to the instance study.",
            }
            output.AnswerBuffer(json.dumps(out, indent=2), "application/json")
            return
        if method != "POST":
            output.AnswerBuffer("Method not allowed", "text/plain")
            return

        body = request.get("body")
        if body is None:
            parsed: Dict[str, Any] = {}
        elif isinstance(body, bytes):
            parsed = json.loads(body.decode("utf-8") or "{}")
        else:
            parsed = json.loads(str(body).strip() or "{}")

        instance_ref = parsed.get("Instance")
        if not instance_ref:
            output.AnswerBuffer(
                json.dumps({"ok": False, "error": "Instance required"}),
                "application/json",
            )
            return

        instance_id = _resolve_orthanc_instance_id(str(instance_ref))
        if not instance_id:
            output.AnswerBuffer(
                json.dumps(
                    {
                        "ok": False,
                        "error": "Unknown instance (Orthanc UUID or SOP Instance UID).",
                        "requested": str(instance_ref),
                    }
                ),
                "application/json",
            )
            return

        predict = parsed.get("predict")
        if not isinstance(predict, dict):
            output.AnswerBuffer(
                json.dumps({"ok": False, "error": "predict must be the JSON object returned by POST /predict"}),
                "application/json",
            )
            return

        letterhead = parsed.get("letterhead")
        if not isinstance(letterhead, dict):
            letterhead = _letterhead_from_config()

        doc_title = parsed.get("document_title")
        if not isinstance(doc_title, str) or not doc_title.strip():
            doc_title = ILO_PDF_DOCUMENT_TITLE

        pdf_result = _attach_ilo_pdf_from_predict(
            instance_id,
            predict,
            letterhead=letterhead,
            document_title=doc_title.strip(),
        )
        out = {
            "ok": pdf_result.get("ok", False),
            "route": "/ilo-attach-pdf",
            "instance_id": instance_id,
            **pdf_result,
        }
        output.AnswerBuffer(json.dumps(out, indent=2), "application/json")
    except json.JSONDecodeError:
        output.AnswerBuffer(json.dumps({"ok": False, "error": "Invalid JSON body"}), "application/json")
    except Exception as e:
        logging.exception("ilo-attach-pdf: %s", e)
        output.AnswerBuffer(json.dumps({"ok": False, "error": str(e)}), "application/json")


def initialize_plugin() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logging.info("Initializing Orthanc ILO Python plugin")
    load_config()

    orthanc.RegisterOnChangeCallback(OnChange)
    orthanc.RegisterRestCallback("/ilo-inference", OnRest)
    orthanc.RegisterRestCallback("/ilo-attach-pdf", OnRest)
    logging.info("Orthanc ILO plugin ready (/ilo-inference, /ilo-attach-pdf)")


initialize_plugin()
