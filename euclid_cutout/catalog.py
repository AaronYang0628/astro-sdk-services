"""Catalog load / validate (FITS or CSV)."""
from __future__ import annotations
from pathlib import Path
from typing import Optional
import numpy as np
from astropy.table import Table


def _load(path: str) -> Table:
    from .safety import check_read
    p = check_read(path)
    suf = p.suffix.lower()
    if suf in (".fits", ".fit"):
        return Table.read(str(p), format="fits")
    if suf in (".csv", ".txt"):
        return Table.read(str(p), format="csv")
    raise ValueError(f"unsupported catalog format: {suf}")


def _pick(colnames, candidates):
    upper = [c.upper() for c in colnames]
    for cand in candidates:
        if cand in upper:
            return colnames[upper.index(cand)]
    return None


def validate_catalog(
    catalog_path: str,
    ra_col: Optional[str] = None,
    dec_col: Optional[str] = None,
    id_col: Optional[str] = None,
    max_rows: int = 10000,
) -> dict:
    """Validate a catalog file and report detected columns / bounds."""
    cat = _load(catalog_path)
    ra_col = ra_col or _pick(cat.colnames, ["RA", "RA_DEG", "RIGHT_ASCENSION", "ALPHA_J2000", "ALPHAWIN_J2000"])
    dec_col = dec_col or _pick(cat.colnames, ["DEC", "DEC_DEG", "DECLINATION", "DELTA_J2000", "DELTAWIN_J2000"])
    id_col = id_col or _pick(cat.colnames, ["TARGETID", "TARGET_ID", "OBJECT_ID", "ID", "SOURCE_ID", "NUMBER"])
    ok = ra_col is not None and dec_col is not None
    out = {
        "ok": ok,
        "path": str(catalog_path),
        "n_rows": int(len(cat)),
        "columns": list(cat.colnames),
        "ra_col": ra_col,
        "dec_col": dec_col,
        "id_col": id_col,
        "within_limit": len(cat) <= max_rows,
        "max_rows": max_rows,
        "error": None if ok else "could not detect RA/DEC columns; pass ra_col/dec_col",
    }
    if ok:
        ra = np.asarray(cat[ra_col], dtype=float)
        dec = np.asarray(cat[dec_col], dtype=float)
        out["ra_range"] = [float(np.nanmin(ra)), float(np.nanmax(ra))]
        out["dec_range"] = [float(np.nanmin(dec)), float(np.nanmax(dec))]
    return out


def load_catalog_table(
    catalog_path: str,
    ra_col: Optional[str] = None,
    dec_col: Optional[str] = None,
    id_col: Optional[str] = None,
) -> tuple[Table, str, str, Optional[str]]:
    info = validate_catalog(catalog_path, ra_col, dec_col, id_col)
    if not info["ok"]:
        raise ValueError(info["error"])
    return _load(catalog_path), info["ra_col"], info["dec_col"], info["id_col"]
