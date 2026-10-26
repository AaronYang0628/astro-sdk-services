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
    format: str = "png",
    p_low: float = 1.0,
    p_high: float = 99.0,
    dpi: int = 120,
    max_side: int = 1024,
    inline_image: Optional[bool] = None,
) -> dict:
    """Write a quicklook PNG or JPG from an image FITS (cutout or full).

    Scaling: ignore NaN/inf; ignore zero-pad from partial cutouts when it would
    collapse the stretch; use percentiles (default 1–99) + asinh, then clip.

    The PNG/JPG is capped at `max_side` pixels (default 1024). Over MCP the image is also
    returned inline as an image content block unless inline_image=False (or env
    EUCLID_INLINE_IMAGE=0).
    """
    fmt = (format or "png").lower().lstrip(".")
    if fmt in ("jpg", "jpeg"):
        fmt = "jpg"
    elif fmt != "png":
        raise ValueError("format must be png or jpg")

    path = Path(fits_path)
    if not path.is_file():
        raise FileNotFoundError(fits_path)

    with fits.open(str(path), ignore_missing_end=True, memmap=True) as hdul:
        if hdu_index is None:
            hdu = None
            for i, cand in enumerate(hdul):
                if getattr(cand, "data", None) is not None and np.ndim(cand.data) == 2:
                    hdu = cand
                    hdu_index = i
                    break
            if hdu is None:
                raise ValueError("no 2D image HDU in FITS")
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

    if output_path:
        out = Path(output_path)
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
    fig.savefig(str(out), dpi=dpi, format="png" if fmt == "png" else "jpeg")
    plt.close(fig)

    if inline_image is None:
        inline_image = (os.environ.get("EUCLID_INLINE_IMAGE") or "1").strip().lower() not in ("0", "false", "no", "off")
    mime = "image/png" if fmt == "png" else "image/jpeg"
    res = {
        "ok": True,
        "fits_path": str(path),
        "hdu_index": int(hdu_index),
        "preview_path": str(out.resolve()),
        "mime_type": mime,
        "inline_image": bool(inline_image),
        "format": fmt,
        "shape": list(data.shape),
        "size_bytes": out.stat().st_size,
        "stretch": stretch_meta,
    }
    if inline_image:
        res["_mcp_images"] = [{"path": str(out), "mimeType": mime}]  # MCP layer -> image content block
    return res
