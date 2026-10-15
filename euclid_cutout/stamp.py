"""Single-step Cutout2D from a local FITS path + write cutout FITS."""
from __future__ import annotations
from pathlib import Path
from typing import Optional
import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from astropy.nddata import Cutout2D
from astropy.coordinates import SkyCoord

from .config import default_output_dir
from .fitsio import _pick_image_hdu, _open


def cutout2d(
    path: str,
    ra: float,
    dec: float,
    size: int = 64,
    hdu_index: Optional[int] = None,
    output_path: Optional[str] = None,
    obj_id: Optional[str] = None,
    mode: str = "partial",
    fill_value: float = 0.0,
) -> dict:
    """Cut out a stamp at (ra,dec) from local FITS and write a new FITS file.

    Returns JSON-safe metadata (path, shape, stats). Does not embed pixel arrays.
    """
    obj_id = obj_id or f"cutout_{ra:.5f}_{dec:.5f}_{int(size)}"
    with _open(path, memmap=True) as hdul:
        idx, hdu = _pick_image_hdu(hdul, hdu_index)
        data = hdu.data
        if data is None:
            raise ValueError(f"HDU {idx} has no data (file may be an incomplete prefix download)")
        hdr = hdu.header
        wcs = WCS(hdr)
        center = SkyCoord(ra, dec, unit="deg")
        cut = Cutout2D(data, center, int(size), wcs=wcs, mode=mode, fill_value=fill_value)
        cut_data = np.asarray(cut.data)
        cut_wcs = cut.wcs

    if output_path:
        out = Path(output_path)
    else:
        out = default_output_dir() / "cutouts" / f"{obj_id}.fits"
    out.parent.mkdir(parents=True, exist_ok=True)

    primary = fits.PrimaryHDU()
    primary.header["OBJID"] = str(obj_id)
    primary.header["ORIGFILE"] = Path(path).name
    primary.header["SRC_HDU"] = idx
    primary.header["RA_OBJ"] = float(ra)
    primary.header["DEC_OBJ"] = float(dec)

    img = fits.ImageHDU(data=cut_data)
    if cut_wcs is not None:
        for k, v in cut_wcs.to_header().items():
            img.header[k] = v
    img.header["OBJECT"] = str(obj_id)
    fits.HDUList([primary, img]).writeto(str(out), overwrite=True)

    finite = cut_data[np.isfinite(cut_data)]
    stats = {}
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
        "hdu_index": idx,
        "ra": float(ra),
        "dec": float(dec),
        "size": int(size),
        "obj_id": obj_id,
        "fits_path": str(out.resolve()),
        "shape": list(cut_data.shape),
        "stats": stats,
    }
