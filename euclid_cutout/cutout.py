"""Cutout2D pipeline: tile → locate → cut → write FITS (JSON-safe returns)."""
from __future__ import annotations
from pathlib import Path
from typing import Optional, Union
import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from astropy.nddata import Cutout2D
from astropy.coordinates import SkyCoord

from .config import default_output_dir, require_mer_root
from .tiles import query_tile_id
from .locate import locate_products
from .catalog import load_catalog_table


def _cutout_image(fits_path: str, ra: float, dec: float, size: int, hdu_index: int = 0) -> dict:
    from .safety import check_read
    with fits.open(str(check_read(fits_path))) as hdul:
        data = hdul[hdu_index].data
        header = hdul[hdu_index].header
        if data is None:
            return {"success": False, "error": "empty image HDU", "contains_nan": False}
        wcs = WCS(header)
        center = SkyCoord(ra, dec, unit="deg")
        cut = Cutout2D(data, center, size, wcs=wcs, mode="partial", fill_value=0)
        return {
            "success": True,
            "data": cut.data,
            "wcs": cut.wcs,
            "contains_nan": bool(np.isnan(cut.data).any()),
            "error": None,
        }


def _write_multi(path: Path, obj_id: str, pieces: dict[str, dict], explicit: bool = False, overwrite: bool = False) -> str:
    primary = fits.PrimaryHDU()
    primary.header["OBJID"] = str(obj_id)
    hdul = fits.HDUList([primary])
    for i, (key, info) in enumerate(pieces.items(), start=1):
        hdu = fits.ImageHDU(data=info["data"])
        if info.get("wcs") is not None:
            for k, v in info["wcs"].to_header().items():
                hdu.header[k] = v
        hdu.header["INSTRUME"] = info.get("instrument", "")
        hdu.header["BAND"] = info.get("band", "")
        hdu.header["PRODUCT"] = info.get("file_type", "")
        primary.header[f"HDU{i}"] = key
        hdul.append(hdu)
    if explicit:  # external output_dir: atomic, 0644, no clobber unless overwrite
        from .safety import atomic_write
        path.parent.mkdir(parents=True, exist_ok=True)
        return str(atomic_write(path, lambda t: hdul.writeto(str(t)), overwrite=overwrite))
    path.parent.mkdir(parents=True, exist_ok=True)
    hdul.writeto(str(path), overwrite=True)
    return str(path)


def cutout_single(
    ra: float,
    dec: float,
    size: int = 64,
    file_types: Optional[list] = None,
    instruments: Optional[list] = None,
    bands: Optional[list] = None,
    obj_id: Optional[str] = None,
    output_dir: Optional[str] = None,
    mer_root: Optional[str] = None,
    tile_index: Optional[str] = None,
    skip_nan: bool = True,
    overwrite: bool = False,
) -> dict:
    """Full chain for one sky position: query tile → locate → Cutout2D → write FITS.

    Returns JSON-safe metadata and output paths (no raw arrays).
    output_dir: omitted -> EUCLID_OUTPUT_DIR; relative -> sub-dir of it; absolute -> a dir under
    EUCLID_WRITE_ROOTS (e.g. /home/scientist/project<id>/ResearchSpace/cutouts/) or EUCLID_OUTPUT_DIR.
    Files go to <output_dir>/<file_type>/<obj_id>.fits; with an explicit output_dir existing files are kept
    (auto-suffix _1, _2, ...) unless overwrite=True.
    """
    file_types = file_types or ["BGSUB"]
    obj_id = obj_id or f"obj_{ra:.5f}_{dec:.5f}"
    explicit = bool(output_dir and str(output_dir).strip())
    if explicit:
        from .safety import resolve_output_dir
        out_root = resolve_output_dir(str(output_dir))
    else:
        out_root = default_output_dir()
    # ensure mer configured early
    require_mer_root(mer_root)

    q = query_tile_id(ra, dec, tile_index=tile_index)
    if not q["found"]:
        return {
            "success": False,
            "ra": ra,
            "dec": dec,
            "tile_id": None,
            "files": [],
            "error": "coordinate not covered by tile index (outside Euclid Q1 footprint or wrong index)",
        }
    tile_id = q["tile_id"]
    files_meta = []
    errors = []

    for ft in file_types:
        located = locate_products(
            tile_id, file_type=ft, instruments=instruments, bands=bands, mer_root=mer_root
        )
        if not located["found"]:
            errors.append(located.get("error") or f"no products for {ft}")
            continue
        pieces: dict[str, dict] = {}
        for key, fpath in located["products"].items():
            try:
                instrument, band = key.split("_", 1)
            except ValueError:
                instrument, band = key, key
            try:
                cut = _cutout_image(fpath, ra, dec, int(size))
            except Exception as e:  # noqa: BLE001
                errors.append(f"{key}: {type(e).__name__}: {e}")
                continue
            if not cut["success"]:
                errors.append(f"{key}: {cut.get('error')}")
                continue
            if cut["contains_nan"] and skip_nan:
                errors.append(f"{key}: skipped (contains NaN)")
                continue
            pieces[key] = {
                "data": cut["data"],
                "wcs": cut["wcs"],
                "instrument": instrument,
                "band": band,
                "file_type": ft,
                "source": fpath,
            }
        if not pieces:
            continue
        safe_id = "".join(c if c.isalnum() or c in "._-" else "_" for c in str(obj_id))[:100] or "obj"
        out_path = out_root / "".join(c if c.isalnum() or c in "._-" else "_" for c in str(ft)) / f"{safe_id}.fits"
        if explicit:
            from .safety import resolve_output_dir
            resolve_output_dir(str(out_path.parent))  # validates + creates the <file_type> sub-dir
        written = _write_multi(out_path, obj_id, pieces, explicit=explicit, overwrite=bool(overwrite))
        from .safety import describe_output
        saved = describe_output(Path(written))
        for key, info in pieces.items():
            files_meta.append(
                {
                    "key": key,
                    "file_type": ft,
                    "path": written,
                    **saved,
                    "source": info["source"],
                    "shape": list(info["data"].shape),
                }
            )

    return {
        "success": bool(files_meta),
        "ra": ra,
        "dec": dec,
        "tile_id": tile_id,
        "obj_id": obj_id,
        "output_dir": str(out_root),
        "n_files": len(files_meta),
        "files": files_meta,
        "errors": errors,
        "error": None if files_meta else ("; ".join(errors) or "cutout failed"),
    }


def cutout_batch(
    catalog_path: str,
    size: int = 64,
    file_types: Optional[list] = None,
    instruments: Optional[list] = None,
    bands: Optional[list] = None,
    ra_col: Optional[str] = None,
    dec_col: Optional[str] = None,
    id_col: Optional[str] = None,
    output_dir: Optional[str] = None,
    mer_root: Optional[str] = None,
    tile_index: Optional[str] = None,
    skip_nan: bool = True,
    max_sources: int = 50,
    overwrite: bool = False,
) -> dict:
    """Batch cutouts from a catalog file. Caps at max_sources (default 50) for safety.
    output_dir: same rules as cutout_single (absolute dir under EUCLID_WRITE_ROOTS allowed)."""
    cat, ra_c, dec_c, id_c = load_catalog_table(catalog_path, ra_col, dec_col, id_col)
    n = min(len(cat), int(max_sources))
    results = []
    n_ok = 0
    for i in range(n):
        row = cat[i]
        ra = float(row[ra_c])
        dec = float(row[dec_c])
        oid = str(row[id_c]) if id_c else f"row_{i}"
        r = cutout_single(
            ra=ra,
            dec=dec,
            size=size,
            file_types=file_types,
            instruments=instruments,
            bands=bands,
            obj_id=oid,
            output_dir=output_dir,
            mer_root=mer_root,
            tile_index=tile_index,
            skip_nan=skip_nan,
            overwrite=overwrite,
        )
        results.append(
            {
                "index": i,
                "obj_id": oid,
                "ra": ra,
                "dec": dec,
                "success": r["success"],
                "tile_id": r.get("tile_id"),
                "n_files": r.get("n_files", 0),
                "files": r.get("files", []),
                "error": r.get("error"),
            }
        )
        if r["success"]:
            n_ok += 1
    return {
        "success": n_ok > 0,
        "catalog_path": catalog_path,
        "n_requested": n,
        "n_catalog": int(len(cat)),
        "n_success": n_ok,
        "n_failed": n - n_ok,
        "truncated": True if len(cat) > n else False,
        "results": results,
    }
