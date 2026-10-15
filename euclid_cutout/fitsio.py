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


def _pick_image_hdu(hdul, hdu_index: Optional[int] = None):
    """Pick a 2D image HDU. Skip empty PRIMARY (NAXIS=0) — common in Euclid VIS MEF."""
    if hdu_index is not None:
        hdu = hdul[hdu_index]
        naxis = int(hdu.header.get("NAXIS", 0) or 0)
        if naxis < 2:
            raise ValueError(
                f"HDU {hdu_index} is not a 2D image (NAXIS={naxis}). "
                f"For Euclid VIS MEF files use hdu_index=1 (e.g. EXTNAME 1-1.E), not 0."
            )
        return int(hdu_index), hdu
    # Prefer first extension with 2D data + WCS (skip empty primary)
    for i, hdu in enumerate(hdul):
        naxis = int(hdu.header.get("NAXIS", 0) or 0)
        if naxis >= 2 and hdu.header.get("NAXIS1") and hdu.header.get("NAXIS2"):
            return i, hdu
    raise ValueError("no 2D image HDU found")


def read_wcs_header(path: str, hdu_index: Optional[int] = None) -> dict:
    """Read WCS cards. Exposes fov_center AND crval — do NOT use these as catalog sources
    unless you intentionally want a mosaic-centre stamp (usually empty background).
    """
    with _open(path, memmap=True) as hdul:
        idx, hdu = _pick_image_hdu(hdul, hdu_index)
        hdr = hdu.header
        w = WCS(hdr)  # same as upstream cutout_image
        naxis1 = int(hdr.get("NAXIS1") or 0)
        naxis2 = int(hdr.get("NAXIS2") or 0)
        fov_center = None
        if naxis1 and naxis2:
            ra, dec = w.pixel_to_world_values(naxis1 / 2.0 - 0.5, naxis2 / 2.0 - 0.5)
            fov_center = {"ra": float(ra), "dec": float(dec)}
        crval = None
        if "CRVAL1" in hdr and "CRVAL2" in hdr:
            crval = {"ra": float(hdr["CRVAL1"]), "dec": float(hdr["CRVAL2"])}
        keys = [
            "CTYPE1", "CTYPE2", "CRVAL1", "CRVAL2", "CRPIX1", "CRPIX2",
            "CD1_1", "CD1_2", "CD2_1", "CD2_2", "CDELT1", "CDELT2",
            "PC1_1", "PC1_2", "PC2_1", "PC2_2", "CUNIT1", "CUNIT2",
            "NAXIS1", "NAXIS2", "BITPIX", "BUNIT", "INSTRUME", "FILTER", "EXTNAME",
        ]
        header = {
            k: (
                None
                if hdr.get(k) is None
                else (
                    float(hdr[k])
                    if isinstance(hdr[k], (int, float, np.floating))
                    else str(hdr[k])
                )
            )
            for k in keys
            if k in hdr
        }
        return {
            "ok": True,
            "path": path,
            "hdu_index": idx,
            "hdu_name": hdu.name,
            "shape": [naxis2, naxis1],
            "fov_center": fov_center,
            "crval": crval,
            # backward-compatible alias — marked as FOV, not a source
            "center": fov_center,
            "center_meaning": "mosaic/detector FOV centre — NOT a catalog source; pass source ra/dec into cutout2d",
            "wcs_type": [str(hdr.get("CTYPE1", "")), str(hdr.get("CTYPE2", ""))],
            "header": header,
        }


def sky_to_pixel(path: str, ra: float, dec: float, hdu_index: Optional[int] = None) -> dict:
    """Convert sky (ra,dec deg) to 0-based pixel (x,y) using the HDU WCS."""
    with _open(path, memmap=True) as hdul:
        idx, hdu = _pick_image_hdu(hdul, hdu_index)
        hdr = hdu.header
        w = WCS(hdr)
        x, y = w.world_to_pixel(SkyCoord(float(ra), float(dec), unit="deg"))
        x_f, y_f = float(x), float(y)
        naxis1 = int(hdr.get("NAXIS1") or 0)
        naxis2 = int(hdr.get("NAXIS2") or 0)
        inside = (0 <= x_f < naxis1) and (0 <= y_f < naxis2)
        return {
            "ok": True,
            "path": path,
            "hdu_index": idx,
            "ra": float(ra),
            "dec": float(dec),
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


def find_peak_sky(
    path: str,
    hdu_index: Optional[int] = None,
    box_size: Optional[int] = None,
) -> dict:
    """Find the brightest finite pixel and return its sky position.

    Use this for URL demos when you have no catalog — NOT fov_center from read_wcs_header.
    Optional box_size restricts the search to a central box (pixels).
    """
    with _open(path, memmap=True) as hdul:
        idx, hdu = _pick_image_hdu(hdul, hdu_index)
        data = np.asarray(hdu.data, dtype=np.float64)
        if data.ndim != 2:
            raise ValueError("image HDU must be 2D")
        w = WCS(hdu.header)
        work = data
        y0 = x0 = 0
        if box_size:
            cy, cx = data.shape[0] // 2, data.shape[1] // 2
            half = int(box_size) // 2
            y0 = max(0, cy - half)
            x0 = max(0, cx - half)
            y1 = min(data.shape[0], cy + half)
            x1 = min(data.shape[1], cx + half)
            work = data[y0:y1, x0:x1]
        if not np.isfinite(work).any():
            raise ValueError("no finite pixels to find a peak")
        # mask non-finite
        masked = np.where(np.isfinite(work), work, -np.inf)
        iy, ix = np.unravel_index(int(np.argmax(masked)), work.shape)
        y, x = int(iy + y0), int(ix + x0)
        ra, dec = w.pixel_to_world_values(x, y)
        return {
            "ok": True,
            "path": path,
            "hdu_index": idx,
            "x": x,
            "y": y,
            "ra": float(ra),
            "dec": float(dec),
            "value": float(data[y, x]),
            "note": "brightest-pixel sky position for cutout2d; prefer a real catalog RA/DEC when available",
        }
