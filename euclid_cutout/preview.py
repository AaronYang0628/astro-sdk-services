"""Quicklook PNG/JPG from a cutout FITS."""
from __future__ import annotations
from pathlib import Path
from typing import Optional
import numpy as np
from astropy.io import fits
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .config import default_output_dir


def _stretch(data: np.ndarray, p_low: float = 1.0, p_high: float = 99.0) -> np.ndarray:
    arr = np.asarray(data, dtype=np.float64)
    mask = np.isfinite(arr)
    if not mask.any():
        return np.zeros_like(arr, dtype=np.float64)
    lo, hi = np.percentile(arr[mask], [p_low, p_high])
    if hi <= lo:
        hi = lo + 1.0
    x = np.clip((arr - lo) / (hi - lo), 0, 1)
    # soft asinh-ish
    return np.arcsinh(5 * x) / np.arcsinh(5)


def write_preview(
    fits_path: str,
    output_path: Optional[str] = None,
    hdu_index: Optional[int] = None,
    format: str = "png",
    p_low: float = 1.0,
    p_high: float = 99.0,
    dpi: int = 120,
) -> dict:
    """Write a quicklook PNG or JPG from an image FITS (cutout or full)."""
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

        vis = _stretch(data, p_low=p_low, p_high=p_high)

    if output_path:
        out = Path(output_path)
    else:
        out = default_output_dir() / "previews" / f"{path.stem}.{fmt}"
    out.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(4, 4))
    ax.imshow(vis, origin="lower", cmap="gray", interpolation="nearest")
    ax.set_xticks([]); ax.set_yticks([])
    ax.set_title(path.name, fontsize=8)
    fig.tight_layout(pad=0.2)
    fig.savefig(str(out), dpi=dpi, format="png" if fmt == "png" else "jpeg")
    plt.close(fig)

    return {
        "ok": True,
        "fits_path": str(path),
        "hdu_index": int(hdu_index),
        "preview_path": str(out.resolve()),
        "format": fmt,
        "shape": list(data.shape),
        "size_bytes": out.stat().st_size,
    }
