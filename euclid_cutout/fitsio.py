"""Fine-grained FITS inspect / WCS / sky↔pixel helpers."""
from __future__ import annotations
from pathlib import Path
from typing import Optional
import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from astropy.coordinates import SkyCoord
import warnings

warnings.filterwarnings("ignore", category=fits.verify.VerifyWarning)


def _open(path: str, **kw):
    # ignore_missing_end: allow prefix downloads of multi-ext mirrors
    return fits.open(path, ignore_missing_end=True, **kw)


def list_hdus(path: str) -> dict:
    """Summarize HDUs in a local FITS file (path from fetch_fits)."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(path)
    rows = []
    with _open(str(p), memmap=True) as hdul:
        for i, hdu in enumerate(hdul):
            hdr = hdu.header
            shape = getattr(hdu, "shape", None)
            rows.append(
                {
                    "index": i,
                    "name": hdu.name,
                    "type": type(hdu).__name__,
                    "shape": list(shape) if shape else None,
                    "naxis": int(hdr.get("NAXIS", 0) or 0),
                    "naxis1": hdr.get("NAXIS1"),
                    "naxis2": hdr.get("NAXIS2"),
                    "bitpix": hdr.get("BITPIX"),
                    "has_wcs": ("CTYPE1" in hdr) or ("CD1_1" in hdr) or ("PC1_1" in hdr) or ("CRVAL1" in hdr),
                }
            )
    return {"ok": True, "path": str(p), "n_hdus": len(rows), "hdus": rows}


def _pick_image_hdu(hdul, hdu_index: Optional[int] = None) -> tuple[int, fits.ImageHDU]:
    if hdu_index is not None:
        hdu = hdul[hdu_index]
        if getattr(hdu, "data", None) is None and hdu.header.get("NAXIS", 0) < 2:
            raise ValueError(f"HDU {hdu_index} has no 2D image")
        return int(hdu_index), hdu
    for i, hdu in enumerate(hdul):
        naxis = int(hdu.header.get("NAXIS", 0) or 0)
        if naxis >= 2 and hdu.header.get("NAXIS1") and hdu.header.get("NAXIS2"):
            # prefer first non-primary with data, else primary
            return i, hdu
    raise ValueError("no 2D image HDU found")


def read_wcs_header(path: str, hdu_index: Optional[int] = None) -> dict:
    """Read WCS-related header cards and basic sky center for an image HDU."""
    with _open(path, memmap=True) as hdul:
        idx, hdu = _pick_image_hdu(hdul, hdu_index)
        hdr = hdu.header
        w = WCS(hdr)
        naxis1 = int(hdr.get("NAXIS1") or 0)
        naxis2 = int(hdr.get("NAXIS2") or 0)
        center = None
        if naxis1 and naxis2:
            ra, dec = w.pixel_to_world_values(naxis1 / 2.0 - 0.5, naxis2 / 2.0 - 0.5)
            center = {"ra": float(ra), "dec": float(dec)}
        keys = [
            "CTYPE1", "CTYPE2", "CRVAL1", "CRVAL2", "CRPIX1", "CRPIX2",
            "CD1_1", "CD1_2", "CD2_1", "CD2_2", "CDELT1", "CDELT2",
            "PC1_1", "PC1_2", "PC2_1", "PC2_2", "CUNIT1", "CUNIT2",
            "NAXIS1", "NAXIS2", "BITPIX", "BUNIT", "INSTRUME", "FILTER", "EXTNAME",
        ]
        header = {k: (None if hdr.get(k) is None else (float(hdr[k]) if isinstance(hdr[k], (int, float, np.floating)) else str(hdr[k]))) for k in keys if k in hdr}
        return {
            "ok": True,
            "path": path,
            "hdu_index": idx,
            "hdu_name": hdu.name,
            "shape": [naxis2, naxis1],
            "center": center,
            "wcs_type": [str(hdr.get("CTYPE1", "")), str(hdr.get("CTYPE2", ""))],
            "header": header,
        }


def sky_to_pixel(path: str, ra: float, dec: float, hdu_index: Optional[int] = None) -> dict:
    """Convert sky (ra,dec deg) to 0-based pixel (x,y) using the HDU WCS."""
    with _open(path, memmap=True) as hdul:
        idx, hdu = _pick_image_hdu(hdul, hdu_index)
        hdr = hdu.header
        w = WCS(hdr)
        x, y = w.world_to_pixel(SkyCoord(ra, dec, unit="deg"))
        x_f, y_f = float(x), float(y)
        naxis1 = int(hdr.get("NAXIS1") or 0)
        naxis2 = int(hdr.get("NAXIS2") or 0)
        inside = (0 <= x_f < naxis1) and (0 <= y_f < naxis2)
        return {
            "ok": True,
            "path": path,
            "hdu_index": idx,
            "ra": ra,
            "dec": dec,
            "x": x_f,
            "y": y_f,
            "inside": inside,
            "naxis1": naxis1,
            "naxis2": naxis2,
        }


def pixel_to_sky(path: str, x: float, y: float, hdu_index: Optional[int] = None) -> dict:
    """Convert 0-based pixel (x,y) to sky (ra,dec deg)."""
    with _open(path, memmap=True) as hdul:
        idx, hdu = _pick_image_hdu(hdul, hdu_index)
        w = WCS(hdu.header)
        ra, dec = w.pixel_to_world_values(x, y)
        return {
            "ok": True,
            "path": path,
            "hdu_index": idx,
            "x": float(x),
            "y": float(y),
            "ra": float(ra),
            "dec": float(dec),
        }
