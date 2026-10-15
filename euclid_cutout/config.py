"""Runtime paths from environment."""
from __future__ import annotations
import os
from pathlib import Path
from typing import Any


def _p(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def get_config() -> dict[str, Any]:
    """Return effective Euclid cutout paths and whether they exist on disk."""
    mer = _p("EUCLID_MER_ROOT")
    tile = _p("EUCLID_TILE_INDEX")
    out = _p("EUCLID_OUTPUT_DIR", str(Path.cwd() / "euclid_cutouts"))
    mer_p, tile_p, out_p = Path(mer) if mer else None, Path(tile) if tile else None, Path(out)
    return {
        "mer_root": mer or None,
        "tile_index": tile or None,
        "output_dir": str(out_p),
        "mer_root_exists": bool(mer_p and mer_p.is_dir()),
        "tile_index_exists": bool(tile_p and tile_p.is_file()),
        "hint": (
            "Set EUCLID_MER_ROOT to the MER directory (parent of <TILE_ID>/) "
            "and EUCLID_TILE_INDEX to a FITS tile index "
            "(TILE_ID, RA_MIN, RA_MAX, DEC_MIN, DEC_MAX, RA_CENTER, DEC_CENTER)."
        ),
    }


def require_mer_root(override: str | None = None) -> Path:
    root = (override or _p("EUCLID_MER_ROOT") or "").strip()
    if not root:
        raise ValueError("EUCLID_MER_ROOT is not set (and mer_root was not passed)")
    p = Path(root)
    if not p.is_dir():
        raise FileNotFoundError(f"EUCLID_MER_ROOT does not exist or is not a directory: {p}")
    return p


def require_tile_index(override: str | None = None) -> Path:
    path = (override or _p("EUCLID_TILE_INDEX") or "").strip()
    if not path:
        raise ValueError("EUCLID_TILE_INDEX is not set (and tile_index was not passed)")
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"EUCLID_TILE_INDEX not found: {p}")
    return p


def default_output_dir(override: str | None = None) -> Path:
    p = Path((override or _p("EUCLID_OUTPUT_DIR") or str(Path.cwd() / "euclid_cutouts")).strip())
    p.mkdir(parents=True, exist_ok=True)
    return p
