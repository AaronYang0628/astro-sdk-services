"""TILE index query (local FITS, no network)."""
from __future__ import annotations
from typing import Optional
import numpy as np
from astropy.table import Table
from astropy.coordinates import SkyCoord
from .config import require_tile_index


def query_tile_id(
    ra: float,
    dec: float,
    tile_index: Optional[str] = None,
    tolerance: float = 0.01,
) -> dict:
    """Map (ra, dec) in degrees to a TILE_ID via the local tile index FITS.

    Index columns: TILE_ID, RA_MIN, RA_MAX, DEC_MIN, DEC_MAX, RA_CENTER, DEC_CENTER.
    On multiple bbox hits, pick the nearest tile center.
    """
    path = require_tile_index(tile_index)
    table = Table.read(str(path))
    needed = {"TILE_ID", "RA_MIN", "RA_MAX", "DEC_MIN", "DEC_MAX"}
    missing = needed - set(table.colnames)
    if missing:
        raise ValueError(f"tile index missing columns: {sorted(missing)}")

    mask = (
        (table["RA_MIN"] - tolerance <= ra)
        & (ra <= table["RA_MAX"] + tolerance)
        & (table["DEC_MIN"] - tolerance <= dec)
        & (dec <= table["DEC_MAX"] + tolerance)
    )
    matched = table[mask]
    if len(matched) == 0:
        return {"found": False, "tile_id": None, "ra": ra, "dec": dec, "n_candidates": 0}
    if len(matched) == 1:
        tid = str(matched["TILE_ID"][0])
        return {"found": True, "tile_id": tid, "ra": ra, "dec": dec, "n_candidates": 1}

    if "RA_CENTER" in matched.colnames and "DEC_CENTER" in matched.colnames:
        coord = SkyCoord(ra, dec, unit="deg")
        centers = SkyCoord(matched["RA_CENTER"], matched["DEC_CENTER"], unit="deg")
        idx = int(np.argmin(coord.separation(centers)))
    else:
        idx = 0
    tid = str(matched["TILE_ID"][idx])
    return {"found": True, "tile_id": tid, "ra": ra, "dec": dec, "n_candidates": int(len(matched))}
