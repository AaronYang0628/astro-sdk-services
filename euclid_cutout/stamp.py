"""Single-step Cutout2D from a local FITS path + write cutout FITS.

Aligned with Euclid-Image-Cutout-Service `cutout_image`:
  SkyCoord(ra, dec, unit='deg') + Cutout2D(..., size in pixels, mode='partial').
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional, Union
import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from astropy.nddata import Cutout2D
from astropy.coordinates import SkyCoord
import astropy.units as u

from .config import default_output_dir
from .fitsio import _pick_image_hdu, _open


def _parse_size(size: Union[int, float, list, tuple], wcs: WCS) -> Union[int, tuple]:
    """Size is pixels (int) by default — same as upstream. Optional [ny, nx] or
    {'value': n, 'unit': 'arcsec'|'pixel'} dict is also accepted for LLM clarity.
    """
    if isinstance(size, dict):
        val = float(size.get("value", size.get("size", 1024)))
        unit = str(size.get("unit", "pixel")).lower()
        if unit in ("pixel", "pix", "px", ""):
            return int(round(val))
        if unit in ("arcsec", "arcsecond", "arcseconds", '"'):
            # approximate square using |CD| scale at CRPIX
            try:
                scales = wcs.proj_plane_pixel_scales()
                pixscale = float(np.mean([s.to(u.arcsec).value for s in scales]))
            except Exception:
                cd = np.abs(wcs.wcs.cd if wcs.wcs.has_cd() else np.diag(wcs.wcs.cdelt))
                pixscale = float(np.mean(cd)) * 3600.0
            if pixscale <= 0:
                raise ValueError("cannot convert arcsec size: invalid plate scale")
            return int(max(1, round(val / pixscale)))
        raise ValueError(f"unsupported size unit: {unit} (use pixel or arcsec)")
    if isinstance(size, (list, tuple)) and len(size) == 2:
        return (int(size[0]), int(size[1]))
    return int(size)


def cutout2d(
    path: str,
    ra: float,
    dec: float,
    size: Union[int, float, list, tuple, dict] = 1024,
    hdu_index: Optional[int] = None,
    output_path: Optional[str] = None,
    obj_id: Optional[str] = None,
    mode: str = "partial",
    fill_value: float = 0.0,
) -> dict:
    """Cut out a stamp at catalog/source (ra,dec deg) — NOT the mosaic FOV center.

    Matches upstream cutout_image: WCS(header), SkyCoord(ra,dec,unit='deg'),
    Cutout2D size in **pixels** (default 1024). Writes a single PrimaryHDU FITS
    (image + WCS) so viewers open the stamp directly.
    """
    obj_id = obj_id or f"cutout_{ra:.5f}_{dec:.5f}"
    with _open(path, memmap=True) as hdul:
        idx, hdu = _pick_image_hdu(hdul, hdu_index)
        data = hdu.data
        if data is None:
            raise ValueError(
                f"HDU {idx} has no data (file may be an incomplete prefix download, "
                "or you picked the empty PRIMARY — pass hdu_index of a 2D image extension)"
            )
        hdr = hdu.header
        # Same construction as Euclid-Image-Cutout-Service.cutout_image
        wcs = WCS(hdr)
        size_px = _parse_size(size, wcs)
        center = SkyCoord(float(ra), float(dec), unit="deg")
        # verify source projects onto this HDU
        x, y = wcs.world_to_pixel(center)
        naxis1 = int(hdr.get("NAXIS1") or data.shape[-1])
        naxis2 = int(hdr.get("NAXIS2") or data.shape[-2])
        inside = (0 <= float(x) < naxis1) and (0 <= float(y) < naxis2)
        cut = Cutout2D(
            data, center, size_px, wcs=wcs, mode=mode, fill_value=fill_value
        )
        cut_data = np.asarray(cut.data)
        cut_wcs = cut.wcs

    if output_path:
        out = Path(output_path)
    else:
        out = default_output_dir() / "cutouts" / f"{obj_id}.fits"
    out.parent.mkdir(parents=True, exist_ok=True)

    # Single PrimaryHDU with image+WCS (better than empty PRIMARY + ImageHDU
    # which many viewers open as a blank frame).
    img = fits.PrimaryHDU(data=cut_data)
    if cut_wcs is not None:
        img.header.update(cut_wcs.to_header())
    img.header["OBJID"] = str(obj_id)
    img.header["ORIGFILE"] = Path(path).name
    img.header["SRC_HDU"] = int(idx)
    img.header["RA_OBJ"] = float(ra)
    img.header["DEC_OBJ"] = float(dec)
    img.header["X_OBJ"] = float(x)
    img.header["Y_OBJ"] = float(y)
    img.header["SIZEPIX"] = int(size_px) if isinstance(size_px, int) else int(size_px[0])
    img.writeto(str(out), overwrite=True)

    finite = cut_data[np.isfinite(cut_data)]
    if finite.size:
        stats = {
            "min": float(np.min(finite)),
            "max": float(np.max(finite)),
            "mean": float(np.mean(finite)),
            "median": float(np.median(finite)),
            "nan_frac": float(1.0 - finite.size / cut_data.size),
        }
    else:
        stats = {"min": None, "max": None, "mean": None, "median": None, "nan_frac": 1.0}

    return {
        "ok": True,
        "success": True,
        "source_path": path,
        "hdu_index": int(idx),
        "ra": float(ra),
        "dec": float(dec),
        "x": float(x),
        "y": float(y),
        "inside": bool(inside),
        "size_pixels": size_px if isinstance(size_px, int) else list(size_px),
        "obj_id": obj_id,
        "fits_path": str(out.resolve()),
        "shape": list(cut_data.shape),
        "stats": stats,
        "warning": None
        if inside
        else "ra/dec project outside this HDU footprint — cutout may be empty/fill-valued",
    }
