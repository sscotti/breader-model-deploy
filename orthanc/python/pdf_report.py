"""
ILO / inference PDF reports and Orthanc encapsulated-PDF attach.

Built by the Orthanc Python plugin after ``POST /predict``: multi-page layout (query
image, predictions and timing, per-neighbor pages), optional letterhead, then attach
via encapsulated PDF SOP.

Letterhead (optional): same keys as the old ``Reports`` block — ``Phone``, ``Email``,
``Website``, ``Address``, optional ``Logo`` path. If ``Logo`` is missing, ``logo.png``
next to this module is used when present.
"""

from __future__ import annotations

import base64
import json
import logging
import textwrap
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PLUGIN_DIR = Path(__file__).resolve().parent

ILO_PDF_DOCUMENT_TITLE = "ILO inference report"
SOP_CLASS_ENCAPSULATED_PDF = "1.2.840.10008.5.1.4.1.1.104.1"
ILO_PDF_RESEARCH_NOTICE_DEFAULT = (
    "For research and investigational use only. "
    "Not for clinical diagnosis, patient care, or treatment decisions."
)


def _generated_timestamp_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _decode_orthanc_rest_bytes(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def _street_address_lines(reports: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    addr = reports.get("Address")
    if isinstance(addr, str) and addr.strip():
        t = addr.replace("<br/>", "\n").replace("<br>", "\n")
        for ln in t.splitlines():
            s = ln.strip()
            if s:
                lines.append(s)
    return lines


def _contact_left_lines(reports: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    phone = reports.get("Phone")
    if isinstance(phone, str) and phone.strip():
        lines.append(f"Tel: {phone.strip()}")
    email = reports.get("Email")
    if isinstance(email, str) and email.strip():
        lines.append(f"Email: {email.strip()}")
    website = reports.get("Website")
    if isinstance(website, str) and website.strip():
        lines.append(f"URL: {website.strip()}")
    return lines


def _wrap_left_column_lines(raw: List[str], max_chars: int) -> List[str]:
    out: List[str] = []
    for line in raw:
        s = line.strip()
        if not s:
            continue
        if len(s) <= max_chars:
            out.append(s)
        else:
            out.extend(textwrap.wrap(s, width=max_chars) or [s])
    return out


def _resolve_logo_path(reports: Dict[str, Any], plugin_dir: Path) -> Optional[Path]:
    raw = reports.get("Logo")
    if isinstance(raw, str) and raw.strip():
        raw = raw.strip()
        p = Path(raw)
        if p.is_absolute() and p.is_file():
            return p
        cand = plugin_dir / raw
        if cand.is_file():
            return cand
        if p.expanduser().is_file():
            return p.expanduser().resolve()
        logging.warning("pdf_report: logo file not found (%r); tried %s", raw, cand)
    default = plugin_dir / "logo.png"
    if default.is_file():
        return default
    return None


def _draw_research_use_notice(c: Any, w: float, h: float, margin: float, text: str) -> float:
    """
    Centered disclaimer at the top of page 1. Returns a y coordinate suitable as ``y_top``
    for ``draw_letterhead`` (everything below the notice).
    """
    c.setFont("Helvetica-Oblique", 7.5)
    c.setFillGray(0.38)
    wrap_w = max(42, int((w - 2 * margin) / 3.85))
    lines = textwrap.wrap(text.strip(), width=wrap_w)[:4]
    line_h = 9.0
    y = h - 26.0
    for line in lines:
        c.drawCentredString(w / 2, y, line[:200])
        y -= line_h
    c.setFillGray(0)
    return y - 8.0


def draw_letterhead(
    c: Any,
    w: float,
    h: float,
    reports: Optional[Dict[str, Any]],
    plugin_dir: Path,
    *,
    y_top: float | None = None,
) -> float:
    margin = 72
    anchor = float(y_top) if y_top is not None else (h - 56)
    if reports is None:
        reports = {}
    right_lines = _street_address_lines(reports)
    logo_path = _resolve_logo_path(reports, plugin_dir)
    left_raw = _contact_left_lines(reports)

    iw, ih = 118, 50
    logo_left_x = w / 2 - iw / 2
    left_col_max_chars = max(18, int((logo_left_x - margin - 10) / 5.2))
    line_leading = 11

    if logo_path:
        try:
            from reportlab.lib.utils import ImageReader

            img_bottom = anchor - ih
            c.drawImage(
                ImageReader(str(logo_path)),
                logo_left_x,
                img_bottom,
                width=iw,
                height=ih,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception as e:
            logging.warning("pdf_report: could not draw logo: %s", e)
            ih = 0
    else:
        ih = 0

    c.setFont("Helvetica", 8)
    c.setFillGray(0)
    left_lines = _wrap_left_column_lines(left_raw, left_col_max_chars)
    ly = anchor
    for line in left_lines[:22]:
        c.drawString(margin, ly, line[:120])
        ly -= line_leading

    right_x = w - margin
    ry = anchor
    for line in right_lines[:22]:
        c.drawRightString(right_x, ry, line[:95])
        ry -= line_leading

    n_left = len(left_lines)
    n_right = len(right_lines)
    text_h_left = n_left * line_leading if n_left else 0
    text_h_right = n_right * line_leading if n_right else 0
    col_h = max(text_h_left, text_h_right, ih)
    band_bottom = anchor - col_h - 6
    c.setStrokeGray(0.72)
    c.setLineWidth(0.75)
    c.line(margin, band_bottom, w - margin, band_bottom)
    return band_bottom - 12


def draw_report_title_and_timestamp(c: Any, w: float, y: float, document_title: str) -> float:
    margin = 72
    title_y = y
    c.setFont("Helvetica-Bold", 15)
    c.drawString(margin, title_y, document_title[:72])
    c.setFont("Helvetica", 10)
    c.setFillGray(0.35)
    c.drawRightString(w - margin, title_y - 2, f"Generated {_generated_timestamp_str()}")
    c.setFillGray(0)
    y = title_y - 20
    c.setStrokeGray(0.82)
    c.setLineWidth(0.5)
    c.line(margin, y, w - margin, y)
    y -= 11
    return y


def _fmt_prob(v: object) -> str:
    """Format a probability for PDF: avoid ``0.000`` masking tiny positive values."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return str(v)
    if x == 0.0:
        return "0"
    # Enough precision for multiclass; compact for values near 1
    return format(x, ".6g")


# ``small_opacities_multiclass`` head (3-class pure model): class index → PDF label
_SMALL_OPAC_MULTICLASS_NAMES: Dict[int, str] = {
    0: "None",
    1: "round",
    2: "interstitial or irregular",
}


def _small_opac_multiclass_display_name(cls_key: object) -> str:
    try:
        i = int(float(str(cls_key).strip()))
    except (TypeError, ValueError):
        return str(cls_key)
    return _SMALL_OPAC_MULTICLASS_NAMES.get(i, str(cls_key))


def _draw_b64_raster_in_box(
    c: Any,
    *,
    left: float,
    bottom: float,
    box_w: float,
    box_h: float,
    b64_ascii: str,
) -> bool:
    """Decode base64 PNG or JPEG (or other raster via PIL) and draw letterboxed into the box."""
    try:
        from reportlab.lib.utils import ImageReader

        raw = base64.b64decode(b64_ascii.strip(), validate=False)
        if not raw:
            return False
        img_io: BytesIO | None = None
        if raw.startswith(b"\x89PNG\r\n\x1a\n") or raw.startswith(b"\xff\xd8\xff"):
            img_io = BytesIO(raw)
        else:
            try:
                from PIL import Image

                pimg = Image.open(BytesIO(raw)).convert("RGB")
                pout = BytesIO()
                pimg.save(pout, format="PNG")
                pout.seek(0)
                img_io = pout
            except Exception:
                return False
        if img_io is None:
            return False
        img = ImageReader(img_io)
        iw, ih = img.getSize()
        scale = min(box_w / float(iw), box_h / float(ih), 1.0)
        dw, dh = iw * scale, ih * scale
        x0 = left + (box_w - dw) / 2
        y_img = bottom + (box_h - dh) / 2
        c.drawImage(img, x0, y_img, width=dw, height=dh, preserveAspectRatio=True, mask="auto")
        return True
    except Exception as e:
        logging.warning("pdf_report: raster decode failed: %s", e)
        return False


def _coerce_head_prediction_dict(pred: Any) -> dict[str, Any]:
    """
    Normalize a single head payload from JSON (or a stray Pydantic model) for PDF rendering.
    Ensures ``probabilities`` values are plain floats and keys are strings.
    """
    if pred is None:
        return {}
    if hasattr(pred, "model_dump"):
        try:
            pred = pred.model_dump()
        except Exception:
            pass
    if not isinstance(pred, dict):
        return {}
    out = dict(pred)
    pr = out.get("probabilities")
    if isinstance(pr, dict):
        coerced: dict[str, float] = {}
        for k, v in pr.items():
            try:
                coerced[str(k)] = float(v)
            except (TypeError, ValueError):
                continue
        out["probabilities"] = coerced
    return out


def _emit_prediction_block_pdf(
    c: Any,
    y: float,
    *,
    margin: float,
    page_w: float,
    page_h: float,
    head_key: str,
    pred: Any,
) -> float:
    """One prediction head: title, label row, optional binary P, then each multiclass class on its own row."""
    pred = _coerce_head_prediction_dict(pred)
    bottom_margin = 72
    # Slightly compact so predictions + timing fit on one page when possible
    line_skip = 9
    fs_head = 9
    fs_row = 8
    fs_sum = 7

    def cls_disp(cls: object) -> str:
        if head_key == "small_opacities_multiclass":
            return _small_opac_multiclass_display_name(cls)
        return str(cls)

    def ensure_y(need: float) -> None:
        nonlocal y
        if y < bottom_margin + need:
            c.showPage()
            y = page_h - bottom_margin

    ensure_y(44)
    c.setFont("Helvetica-Bold", fs_head)
    c.drawString(margin, y, str(head_key))
    y -= line_skip + 3

    if not isinstance(pred, dict):
        c.setFont("Helvetica", fs_row)
        c.drawString(margin + 12, y, str(pred)[:500])
        return y - line_skip - 8

    if pred.get("label") is not None:
        ensure_y(line_skip)
        c.setFont("Helvetica-Bold", fs_row)
        c.drawString(margin + 12, y, "Predicted label")
        c.setFont("Helvetica", fs_row)
        lbl = pred.get("label")
        c.drawString(margin + 122, y, cls_disp(lbl))
        y -= line_skip + 1

    if pred.get("probability") is not None:
        ensure_y(line_skip)
        c.setFont("Helvetica-Bold", fs_row)
        c.drawString(margin + 12, y, "Probability")
        c.setFont("Helvetica", fs_row)
        c.drawString(margin + 122, y, _fmt_prob(pred.get("probability")))
        y -= line_skip + 1

    probs = pred.get("probabilities")
    if isinstance(probs, dict) and len(probs) > 0:
        ensure_y(line_skip + 3)
        c.setFont("Helvetica-Bold", fs_row)
        c.drawString(margin + 12, y, "Class probabilities")
        y -= line_skip + 1
        items = sorted(
            probs.items(),
            key=lambda kv: float(kv[1]) if kv[1] is not None else 0.0,
            reverse=True,
        )
        for cls, val in items:
            ensure_y(line_skip)
            c.setFont("Helvetica", fs_row)
            c.drawString(margin + 18, y, f"P({cls_disp(cls)}) = {_fmt_prob(val)}")
            y -= line_skip
        s = sum(float(v) for v in probs.values() if v is not None)
        ensure_y(line_skip)
        c.setFont("Helvetica-Oblique", fs_sum)
        c.setFillGray(0.4)
        c.drawString(margin + 18, y, f"(sum of above = {_fmt_prob(s)})")
        c.setFillGray(0)
        y -= line_skip + 1
    elif isinstance(probs, dict) and len(probs) == 0:
        ensure_y(line_skip)
        c.setFont("Helvetica-Oblique", fs_row)
        c.drawString(margin + 12, y, "Class probabilities: {} (empty dict in response)")
        y -= line_skip + 1
    elif pred.get("probabilities") is not None:
        ensure_y(line_skip)
        c.setFont("Helvetica-Oblique", fs_sum)
        c.drawString(margin + 12, y, str(pred.get("probabilities"))[:200])
        y -= line_skip + 1

    return y - 6


def _draw_query_image_panel(
    c: Any,
    *,
    margin: float,
    top_y: float,
    content_width: float,
    predict: Dict[str, Any],
    placeholder_note: Optional[str] = None,
    box_w: Optional[float] = None,
    box_h: Optional[float] = None,
) -> float:
    """
    Draw optional raster from ``_preview_png_b64`` or ``_preview_jpeg_b64`` (ASCII base64, no data: prefix),
    else a labeled placeholder box. Panel size defaults to 256×256 pt; pass ``box_w`` / ``box_h`` to override.
    Image is letterboxed inside the panel. Returns y coordinate below the panel.
    """
    default_note = (
        "Query image preview not embedded in this response. "
        "When inference returns _preview_png_b64 (e.g. DICOM decode) or _preview_jpeg_b64, it will appear here."
    )
    note = (placeholder_note or default_note).strip()

    bw = 256.0 if box_w is None else float(box_w)
    bh = 256.0 if box_h is None else float(box_h)
    box_w, box_h = bw, bh
    left = margin + max(0.0, (content_width - box_w) / 2.0)
    bottom = top_y - box_h

    drawn = False
    for b64 in (predict.get("_preview_png_b64"), predict.get("_preview_jpeg_b64")):
        if isinstance(b64, str) and b64.strip():
            drawn = _draw_b64_raster_in_box(
                c,
                left=left,
                bottom=bottom,
                box_w=box_w,
                box_h=box_h,
                b64_ascii=b64,
            )
            if drawn:
                break

    if not drawn:
        c.setStrokeGray(0.55)
        c.setFillGray(0.94)
        c.setLineWidth(1)
        c.rect(left, bottom, box_w, box_h, fill=1, stroke=1)
        c.setFillGray(0.35)
        c.setFont("Helvetica-Oblique", 9)
        wrap_w = max(16, int((box_w - 24) / 5.2))
        for i, line in enumerate(textwrap.wrap(note, width=wrap_w)):
            c.drawString(left + 12, bottom + box_h - 22 - i * 11, line)

    c.setFillGray(0)
    return bottom - 14


def build_ilo_inference_pdf_bytes(
    predict: Dict[str, Any],
    *,
    instance_id: str = "",
    document_title: str = ILO_PDF_DOCUMENT_TITLE,
    letterhead: Optional[Dict[str, Any]] = None,
    research_notice: Optional[str] = None,
    plugin_dir: Optional[Path] = None,
) -> bytes:
    """
    Multi-page PDF from inference ``POST /predict`` JSON:

    - **Page 1:** optional research disclaimer (top), letterhead, title, instance id (if any), query image.
      Text defaults to ``ILO_PDF_RESEARCH_NOTICE_DEFAULT``; pass ``research_notice=""`` to omit, or a custom string.
      When built from the Orthanc plugin, ``_preview_png_b64`` is usually replaced with Orthanc's own
      ``/instances/{uuid}/preview`` PNG so the PDF matches the viewer; otherwise inference's DICOM decode preview is used.
    - **Page 2:** input metadata, predictions, timing.
    - **Following pages:** one page per nearest neighbor (rank, similarity, paths, labels, legacy portrait thumb).
    """
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
    except ImportError as e:
        raise RuntimeError("reportlab is required (pip install reportlab)") from e

    pdir = plugin_dir if plugin_dir is not None else PLUGIN_DIR
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    w, h = letter
    margin = 72
    content_w = w - 2 * margin
    c.setTitle(document_title)

    if research_notice is None:
        notice_text: Optional[str] = ILO_PDF_RESEARCH_NOTICE_DEFAULT
    else:
        s = research_notice.strip()
        notice_text = s if s else None

    def emit_kv(y: float, label: str, value: str, value_size: int = 9) -> float:
        value_x = margin + 152
        wrap_chars = max(24, int((w - margin - 8 - value_x) / 4.85))
        val_lines = textwrap.wrap(str(value), width=wrap_chars) or [""]
        c.setFont("Helvetica-Bold", 9)
        c.drawString(margin, y, label)
        c.setFont("Helvetica", value_size)
        c.drawString(value_x, y, val_lines[0][:800])
        y -= value_size + 3
        for line in val_lines[1:]:
            c.drawString(value_x, y, line[:800])
            y -= value_size + 2
        return y - 6

    def emit_heading(y: float, text: str) -> float:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(margin, y, text[:100])
        return y - 14

    def start_page(page_subtitle: str, *, full_title: bool = False) -> float:
        letter_y_top: float | None = None
        if full_title and notice_text:
            letter_y_top = _draw_research_use_notice(c, w, h, margin, notice_text)
        y0 = draw_letterhead(c, w, h, letterhead, pdir, y_top=letter_y_top)
        if full_title:
            y0 = draw_report_title_and_timestamp(c, w, y0, document_title)
        else:
            c.setFont("Helvetica-Bold", 13)
            c.drawString(margin, y0 - 4, document_title[:64])
            c.setFont("Helvetica", 10)
            c.setFillGray(0.35)
            c.drawRightString(w - margin, y0 - 6, page_subtitle[:120])
            c.setFillGray(0)
            y0 -= 22
            c.setStrokeGray(0.82)
            c.setLineWidth(0.5)
            c.line(margin, y0, w - margin, y0)
            y0 -= 14
        return y0

    # ----- Page 1: query image only (large panel) -----
    y = start_page("", full_title=True)
    if instance_id:
        y = emit_kv(y, "Orthanc instance", instance_id)

    y = emit_heading(y, "Query image (inference input)")
    bottom_safe = margin + 72
    avail_h = max(0.0, y - bottom_safe)
    target = 512.0
    side = min(target, content_w, max(160.0, avail_h))
    y = _draw_query_image_panel(
        c,
        margin=margin,
        top_y=y,
        content_width=content_w,
        predict=predict,
        box_w=side,
        box_h=side,
    )

    # ----- Page 2: input, predictions, timing -----
    preds = predict.get("predictions") or {}
    timing = predict.get("timing_ms")
    inp = predict.get("input") or {}

    c.showPage()
    y = start_page("Predictions & input", full_title=False)
    y = emit_heading(y, "Input")
    y = emit_kv(y, "Filename", str(inp.get("filename", "—")))
    if inp.get("image_size"):
        y = emit_kv(y, "Image size", str(inp.get("image_size")))

    if isinstance(preds, dict) and preds:
        y = emit_heading(y, "Predictions")
        for k in sorted(preds.keys()):
            y = _emit_prediction_block_pdf(
                c,
                y,
                margin=margin,
                page_w=w,
                page_h=h,
                head_key=str(k),
                pred=preds.get(k),
            )

    if isinstance(timing, dict) and timing:
        timing_lines = json.dumps(timing, indent=2).splitlines()
        line_lead = 8.5
        heading_drop = 14.0
        need_y = margin + heading_drop + len(timing_lines) * line_lead + 8.0

        def open_timing_continuation_page() -> None:
            nonlocal y
            c.showPage()
            y = start_page("Predictions & input (cont.)", full_title=False)
            c.setFont("Helvetica-Bold", 9)
            c.drawString(margin, y, "Timing (ms) (cont.)")
            y -= 12

        if y < need_y:
            c.showPage()
            y = start_page("Predictions & input (cont.)", full_title=False)

        y = emit_heading(y, "Timing (ms)")
        c.setFont("Helvetica", 7)
        for line in timing_lines:
            if y < margin + line_lead + 4:
                open_timing_continuation_page()
                c.setFont("Helvetica", 7)
            c.drawString(margin, y, line[:140])
            y -= line_lead

    # ----- One page per neighbor -----
    neighbors = predict.get("neighbors") or []
    if isinstance(neighbors, list):
        for nb in neighbors:
            if not isinstance(nb, dict):
                continue
            rank = nb.get("rank", "?")
            c.showPage()
            y = start_page(f"Nearest neighbor (rank {rank})", full_title=False)

            y = emit_kv(y, "Rank", str(rank))
            y = emit_kv(y, "image_id", str(nb.get("image_id", "—")))
            y = emit_kv(y, "similarity_cosine", str(nb.get("similarity_cosine", "—")))
            sf = nb.get("source_filepath")
            if sf:
                y = emit_kv(y, "source_filepath", str(sf))
            tp = nb.get("thumbnail_path")
            if tp:
                y = emit_kv(y, "thumbnail_path", str(tp))

            y = emit_heading(y, "Labels")
            lbls = nb.get("labels")
            if isinstance(lbls, dict) and lbls:
                for lk in sorted(lbls.keys()):
                    val = lbls[lk]
                    if val is None:
                        s = "—"
                    else:
                        s = str(val)
                    y = emit_kv(y, str(lk), s)
            else:
                c.setFont("Helvetica-Oblique", 9)
                c.drawString(margin, y, "(no labels in neighbor payload)")
                y -= 14

            y = emit_heading(y, "Thumbnail")
            nb_jpg = nb.get("thumbnail_jpeg_b64")
            nb_predict: Dict[str, Any] = {}
            if isinstance(nb_jpg, str) and nb_jpg.strip():
                nb_predict["_preview_jpeg_b64"] = nb_jpg.strip()
            # Neighbor thumbnail: original portrait panel (not the page-1 query size).
            nb_box_w = min(240.0, content_w * 0.42)
            nb_box_h = 320.0
            y = _draw_query_image_panel(
                c,
                margin=margin,
                top_y=y,
                content_width=content_w,
                predict=nb_predict,
                box_w=nb_box_w,
                box_h=nb_box_h,
                placeholder_note=(
                    "No neighbor thumbnail in response. "
                    "Call /predict with include_neighbor_thumbnails=true (Orthanc plugin does this) "
                    "so inference can embed a JPEG from source_filepath."
                ),
            )

    c.save()
    return buf.getvalue()


def _orthanc_simplified_scalar(tag_entry: Any) -> Optional[str]:
    if tag_entry is None:
        return None
    if isinstance(tag_entry, dict):
        v = tag_entry.get("Value")
    else:
        v = tag_entry
    if v is None:
        return None
    if isinstance(v, list):
        if not v:
            return None
        first = v[0]
        if isinstance(first, dict):
            return first.get("Alphabetic") or first.get("Value") or str(first)
        return str(first)
    if isinstance(v, dict):
        return v.get("Alphabetic") or v.get("Value") or str(v)
    s = str(v).strip()
    return s if s else None


def _strip_sop_and_identity_uids(tags: Dict[str, str]) -> None:
    for k in ("SOPClassUID", "SOPInstanceUID", "StudyInstanceUID", "SeriesInstanceUID"):
        tags.pop(k, None)


_TAGS_TO_INHERIT_FROM_SOURCE: Tuple[str, ...] = (
    "PatientName",
    "PatientID",
    "PatientBirthDate",
    "PatientSex",
    "StudyDate",
    "StudyTime",
)


def _tags_from_source_instance(source_instance_id: str) -> Dict[str, str]:
    import orthanc

    out: Dict[str, str] = {}
    try:
        raw = orthanc.RestApiGet(f"/instances/{source_instance_id}/simplified-tags")
        if isinstance(raw, bytes):
            tags = json.loads(_decode_orthanc_rest_bytes(raw))
        else:
            tags = json.loads(raw)
    except (json.JSONDecodeError, OSError, TypeError) as e:
        logging.warning("pdf_report: could not read simplified-tags: %s", e)
        return out

    for name in _TAGS_TO_INHERIT_FROM_SOURCE:
        val = _orthanc_simplified_scalar(tags.get(name))
        if val:
            out[name] = val
    return out


def _parse_rest_json(response: Any) -> Any:
    if isinstance(response, bytes):
        return json.loads(_decode_orthanc_rest_bytes(response))
    if isinstance(response, str):
        return json.loads(response)
    return json.loads(str(response))


def _resolve_orthanc_instance_id(raw: str) -> Optional[str]:
    import orthanc

    s = (raw or "").strip()
    if not s:
        return None
    try:
        orthanc.RestApiGet(f"/instances/{s}")
        return s
    except Exception:
        pass
    try:
        payload = json.dumps({"Level": "Instance", "Query": {"SOPInstanceUID": s}})
        r = orthanc.RestApiPost("/tools/find", payload)
        found = _parse_rest_json(r)
        if not isinstance(found, list) or len(found) == 0:
            return None
        if len(found) > 1:
            logging.warning("pdf_report: SOPInstanceUID matched %s instances; using first", len(found))
        return found[0]
    except Exception as e:
        logging.warning("pdf_report: find by SOPInstanceUID failed: %s", e)
        return None


def _verify_encapsulated_pdf_stream(instance_id: str) -> Dict[str, Any]:
    import orthanc

    try:
        data = orthanc.RestApiGet(f"/instances/{instance_id}/pdf")
    except Exception as e:
        return {"ok": False, "detail": str(e)}
    if isinstance(data, str):
        data = data.encode("latin-1")
    if not data or len(data) < 5:
        return {"ok": False, "detail": "EncapsulatedDocument empty or too small"}
    if data[:4] != b"%PDF":
        return {"ok": False, "detail": "EncapsulatedDocument does not look like a PDF stream"}
    return {"ok": True, "encapsulated_pdf_byte_length": len(data)}


def attach_pdf_to_study_create_dicom(
    source_instance_id: str,
    pdf_bytes: bytes,
    *,
    document_title: str = ILO_PDF_DOCUMENT_TITLE,
) -> Dict[str, Any]:
    """
    POST ``/tools/create-dicom`` with ``data:application/pdf;base64,...``.
    Parent = **study** of ``source_instance_id`` so the PDF lands in its own series.
    """
    import orthanc

    instance_json_str = orthanc.RestApiGet(f"/instances/{source_instance_id}")
    instance_json = json.loads(instance_json_str)
    source_series_id = instance_json.get("ParentSeries")
    parent_study_id = instance_json.get("ParentStudy")
    if not parent_study_id and source_series_id:
        try:
            series_json = json.loads(orthanc.RestApiGet(f"/series/{source_series_id}"))
            parent_study_id = series_json.get("ParentStudy")
        except (json.JSONDecodeError, OSError, TypeError, Exception) as e:
            logging.warning("pdf_report: could not resolve ParentStudy from series: %s", e)
    if not parent_study_id:
        return {"ok": False, "error": "Could not resolve ParentStudy for instance"}

    b64 = base64.b64encode(pdf_bytes).decode("ascii")
    tags: Dict[str, str] = _tags_from_source_instance(source_instance_id)
    _strip_sop_and_identity_uids(tags)
    tags["Modality"] = "DOC"
    tags["ConversionType"] = "SYN"
    tags["BurnedInAnnotation"] = "YES"
    tags["DocumentTitle"] = document_title
    tags["SeriesDescription"] = document_title
    tags["SOPClassUID"] = SOP_CLASS_ENCAPSULATED_PDF
    payload = {
        "Parent": parent_study_id,
        "Tags": tags,
        "Content": f"data:application/pdf;base64,{b64}",
        "Force": True,
    }
    response_str = orthanc.RestApiPost("/tools/create-dicom", json.dumps(payload))
    response = json.loads(response_str)
    new_id = response.get("ID")
    if not new_id:
        return {"ok": False, "error": "create-dicom failed", "response": response}

    verify = _verify_encapsulated_pdf_stream(new_id)
    pdf_inst = json.loads(orthanc.RestApiGet(f"/instances/{new_id}"))
    pdf_series_id = pdf_inst.get("ParentSeries")
    out: Dict[str, Any] = {
        "ok": True,
        "new_instance_id": new_id,
        "path": response.get("Path"),
        "parent_study_id": parent_study_id,
        "source_series_id": source_series_id,
        "pdf_series_id": pdf_series_id,
        "sop_class_uid": SOP_CLASS_ENCAPSULATED_PDF,
        "encapsulated_pdf_verified": verify.get("ok", False),
        "encapsulated_pdf_verify": verify,
    }
    if not verify.get("ok"):
        logging.error(
            "pdf_report: EncapsulatedDocument verify failed for %s: %s",
            new_id,
            verify.get("detail", verify),
        )
        out["warning"] = "Encapsulated PDF stream check failed; instance was still stored"
    return out


__all__ = [
    "PLUGIN_DIR",
    "ILO_PDF_DOCUMENT_TITLE",
    "ILO_PDF_RESEARCH_NOTICE_DEFAULT",
    "build_ilo_inference_pdf_bytes",
    "attach_pdf_to_study_create_dicom",
    "draw_letterhead",
    "draw_report_title_and_timestamp",
    "_resolve_orthanc_instance_id",
]
