"""Quicklook PNG/JPG from a cutout FITS."""
from __future__ import annotations
from pathlib import Path
from typing import Optional
import numpy as np
from astropy.io import fits
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import os
from .config import default_output_dir


def _env_flag(name: str, default: bool) -> bool:
    v = (os.environ.get(name) or "").strip().lower()
    if not v:
        return default
    return v not in ("0", "false", "no", "off")


def _base64_default(uploaded: bool) -> bool:
    """EUCLID_PREVIEW_BASE64: on / off / auto (default). auto = embed base64 unless the preview was uploaded to OSS
    (then the download_url replaces it). Without OSS configured, auto behaves like on."""
    v = (os.environ.get("EUCLID_PREVIEW_BASE64") or "").strip().lower()
    if v in ("0", "false", "no", "off"):
        return False
    if v in ("1", "true", "yes", "on"):
        return True
    return not uploaded


def _b64_cap() -> int:
    try:
        return int((os.environ.get("EUCLID_PREVIEW_BASE64_MAX_BYTES") or "").strip() or 300000)
    except ValueError:
        return 300000


def _b64_target() -> int:
    """Preferred raw size of the embedded image (LLM agents must copy the base64 text out, so keep it small)."""
    try:
        return int((os.environ.get("EUCLID_PREVIEW_BASE64_TARGET_BYTES") or "").strip() or 30000)
    except ValueError:
        return 30000


def _base64_payload(out: Path, mime: str) -> dict:
    """image_base64 for a written preview. The file itself when it is <= EUCLID_PREVIEW_BASE64_TARGET_BYTES
    (default 30000); otherwise a downscaled JPEG thumbnail of it that fits the target (the file on the server is
    unchanged). Never more than EUCLID_PREVIEW_BASE64_MAX_BYTES (default 300000) raw bytes: if even the smallest
    thumbnail would exceed that, the field is omitted and image_base64_omitted says why."""
    import base64
    import io
    cap = _b64_cap()
    target = min(_b64_target(), cap)
    size = out.stat().st_size
    if size <= target:
        return {"image_base64": base64.b64encode(out.read_bytes()).decode("ascii"),
                "image_base64_mime": mime, "image_base64_size_bytes": size}
    from PIL import Image
    best = None
    with Image.open(out) as im:
        im = im.convert("RGB")
        for side in (320, 256, 192, 128, 96, 64):
            t = im.copy()
            t.thumbnail((side, side), Image.LANCZOS)
            buf = io.BytesIO()
            t.save(buf, format="JPEG", quality=70, optimize=True)
            best = (buf.getvalue(), t.size)
            if len(best[0]) <= target:
                break
    data, (w, h) = best
    if len(data) > cap:
        return {"image_base64_omitted": f"too large ({len(data)} bytes > cap {cap}); lower max_side"}
    return {"image_base64": base64.b64encode(data).decode("ascii"), "image_base64_mime": "image/jpeg",
            "image_base64_size_bytes": len(data),
            "image_base64_note": f"downscaled {w}x{h} JPEG thumbnail of the preview (the preview file is {size} bytes); "
                                 "set EUCLID_PREVIEW_BASE64_TARGET_BYTES higher on the server for the full file"}


def _valid_mask(arr: np.ndarray) -> np.ndarray:
    """Finite pixels; drop exact-zero pad when it dominates a high-floor image.

    Cutout2D(mode='partial', fill_value=0) leaves large zero pads. Including
    those zeros in percentiles makes lo≈0 and sky≈white. Exclude them when
    they look like fill (many zeros + remaining values clustered well above 0).
    """
    finite = np.isfinite(arr)
    if not finite.any():
        return finite
    zeros = finite & (arr == 0)
    frac_zero = float(zeros.sum()) / float(finite.sum())
    if frac_zero >= 0.05:
        nonzero = finite & (arr != 0)
        if nonzero.any():
            med = float(np.median(arr[nonzero]))
            # high floor relative to zero → zeros are pad, not real sky
            if med > 1e-3 * max(abs(float(np.nanmax(arr[nonzero]))), 1e-6) and med != 0:
                return nonzero
    return finite


def _stretch(
    data: np.ndarray,
    p_low: float = 1.0,
    p_high: float = 99.0,
    soft: float = 10.0,
) -> tuple[np.ndarray, dict]:
    """Robust asinh stretch on science pixels; NaN/inf/pad → 0 (black)."""
    arr = np.asarray(data, dtype=np.float64)
    out = np.zeros_like(arr, dtype=np.float64)
    mask = _valid_mask(arr)
    if not mask.any():
        return out, {"lo": None, "hi": None, "n_valid": 0, "n_total": int(arr.size)}

    sample = arr[mask]
    lo, hi = np.percentile(sample, [p_low, p_high])
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        # fall back to min/max of valid
        lo = float(np.min(sample))
        hi = float(np.max(sample))
        if hi <= lo:
            hi = lo + 1e-6

    # linear normalize then soft asinh (highlights without blowing out)
    x = np.clip((arr - lo) / (hi - lo), 0.0, 1.0)
    x = np.where(mask, x, 0.0)
    # non-finite → 0
    x = np.where(np.isfinite(arr), x, 0.0)
    out = np.arcsinh(soft * x) / np.arcsinh(soft)
    meta = {
        "lo": float(lo),
        "hi": float(hi),
        "p_low": float(p_low),
        "p_high": float(p_high),
        "n_valid": int(mask.sum()),
        "n_total": int(arr.size),
        "frac_valid": float(mask.sum()) / float(arr.size),
    }
    return out, meta


def write_preview(
    fits_path: str,
    output_path: Optional[str] = None,
    hdu_index: Optional[int] = None,
    format: Optional[str] = None,
    p_low: float = 1.0,
    p_high: float = 99.0,
    dpi: int = 120,
    max_side: int = 1024,
    inline_image: Optional[bool] = None,
    overwrite: bool = False,
    return_base64: Optional[bool] = None,
) -> dict:
    """Write a quicklook PNG or JPG from an image FITS (cutout or full).

    Scaling: ignore NaN/inf; ignore zero-pad from partial cutouts when it would
    collapse the stretch; use percentiles (default 1–99) + asinh, then clip.

    The PNG/JPG is capped at `max_side` pixels (default 1024). Over MCP the image is also
    returned inline as an image content block unless inline_image=False (or env
    EUCLID_INLINE_IMAGE=0).

    return_base64: also return the PNG/JPG bytes as `image_base64` in the JSON result (for clients that drop MCP
    image blocks and for servers that cannot write into the caller's project: the caller decodes and saves it
    itself). Default None -> env EUCLID_PREVIEW_BASE64: on | off | auto (default; = on, except omitted when the
    preview was uploaded to OSS and a download_url is returned). Skipped, with `image_base64_omitted`, when
    the file exceeds EUCLID_PREVIEW_BASE64_MAX_BYTES (default 300000 raw bytes).

    output_path (optional): absolute file (.png/.jpg/.jpeg) or directory (ends with '/' or exists; default
    name <fits stem>.<format>) under EUCLID_WRITE_ROOTS (default /home/scientist, e.g. a 021 project's
    ResearchSpace) or EUCLID_OUTPUT_DIR. format defaults to the output_path extension, else png.
    Existing files are not overwritten unless overwrite=True (a _1, _2, ... suffix is added; the actual
    path is returned as saved_path / preview_path). Omitted: EUCLID_OUTPUT_DIR/previews/<stem>.<format>.
    """
    explicit = bool(output_path and str(output_path).strip())
    if not format and explicit and str(output_path).lower().endswith((".jpg", ".jpeg")):
        format = "jpg"
    fmt = (format or "png").lower().lstrip(".")
    if fmt in ("jpg", "jpeg"):
        fmt = "jpg"
    elif fmt != "png":
        raise ValueError("format must be png or jpg")

    from .safety import check_read, resolve_output, atomic_write, describe_output, IMAGE_EXTS
    path = check_read(fits_path)

    with fits.open(str(path), ignore_missing_end=True, memmap=True) as hdul:
        if hdu_index is None:
            hdu = None
            for i, cand in enumerate(hdul):
                if getattr(cand, "data", None) is not None and np.ndim(cand.data) == 2:
                    hdu = cand
                    hdu_index = i
                    break
            if hdu is None:
                from .fitsio import no_image_message
                raise ValueError(no_image_message(hdul))
        else:
            hdu = hdul[hdu_index]
        data = hdu.data
        if data is None or np.ndim(data) != 2:
            raise ValueError(f"HDU {hdu_index} is not a 2D image")
        # copy so memmap can close
        data = np.array(data, dtype=np.float64, copy=True)
        vis, stretch_meta = _stretch(data, p_low=p_low, p_high=p_high)
        title = path.name
        if "RA_OBJ" in hdu.header and "DEC_OBJ" in hdu.header:
            title = f"{path.name}\nRA={hdu.header['RA_OBJ']:.5f} DEC={hdu.header['DEC_OBJ']:.5f}"

    if explicit:
        out = resolve_output(str(output_path), f"{path.stem}.{fmt}", IMAGE_EXTS)
        want = (".png",) if fmt == "png" else (".jpg", ".jpeg")
        if not out.name.lower().endswith(want):
            raise ValueError(f"output_path extension {out.suffix} does not match format={fmt}")
    else:
        out = default_output_dir() / "previews" / f"{path.stem}.{fmt}"
        out.parent.mkdir(parents=True, exist_ok=True)

    figsize = (4.2, 4.5)
    max_side = int(max_side or 1024)
    dpi = max(20, min(int(dpi or 120), int(max_side / max(figsize))))  # keep longest side <= max_side
    fig, ax = plt.subplots(figsize=figsize)
    ax.imshow(vis, origin="lower", cmap="gray", interpolation="nearest", vmin=0, vmax=1)
    ax.set_xticks([]); ax.set_yticks([])
    ax.set_title(title, fontsize=7)
    ax.plot(data.shape[1] / 2 - 0.5, data.shape[0] / 2 - 0.5, "r+", markersize=10, markeredgewidth=1.5)
    fig.tight_layout(pad=0.3)
    try:
        if explicit:
            out = atomic_write(out, lambda t: fig.savefig(str(t), dpi=dpi, format="png" if fmt == "png" else "jpeg"),
                               overwrite=bool(overwrite))
        else:
            fig.savefig(str(out), dpi=dpi, format="png" if fmt == "png" else "jpeg")
    finally:
        plt.close(fig)

    if inline_image is None:
        inline_image = (os.environ.get("EUCLID_INLINE_IMAGE") or "1").strip().lower() not in ("0", "false", "no", "off")
    mime = "image/png" if fmt == "png" else "image/jpeg"
    res = {
        "ok": True,
        "fits_path": str(path),
        "hdu_index": int(hdu_index),
        "preview_path": str(out.resolve()),
        **describe_output(out),
        "mime_type": mime,
        "inline_image": bool(inline_image),
        "format": fmt,
        "shape": list(data.shape),
        "size_bytes": out.stat().st_size,
        "stretch": stretch_meta,
    }
    from .oss import upload_result
    res.update(upload_result(str(out), filename=out.name, content_type=mime))  # {} unless EUCLID_OSS_* configured
    if return_base64 is None:
        return_base64 = _base64_default(uploaded="download_url" in res)
    if return_base64:
        res.update(_base64_payload(out, mime))
    if inline_image:
        res["_mcp_images"] = [{"path": str(out), "mimeType": mime}]  # MCP layer -> image content block
    return res
