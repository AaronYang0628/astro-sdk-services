"""Runtime paths from environment."""
from __future__ import annotations
import os
from pathlib import Path
from typing import Any


def _p(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def cache_dir() -> Path:
    p = Path(_p("EUCLID_CACHE_DIR", str(Path.cwd() / "euclid_cache"))).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_config() -> dict[str, Any]:
    """Return effective Euclid cutout paths and whether they exist on disk."""
    mer = _p("EUCLID_MER_ROOT")
    tile = _p("EUCLID_TILE_INDEX")
    out = _p("EUCLID_OUTPUT_DIR", str(Path.cwd() / "euclid_cutouts"))
    cache = str(cache_dir())
    mer_p, tile_p, out_p = Path(mer) if mer else None, Path(tile) if tile else None, Path(out)
    return {
        "mer_root": mer or None,
        "tile_index": tile or None,
        "output_dir": str(out_p),
        "cache_dir": cache,
        "mer_root_exists": bool(mer_p and mer_p.is_dir()),
        "tile_index_exists": bool(tile_p and tile_p.is_file()),
        "cache_dir_exists": True,
        "hint": (
            "Remote URL cutouts: set EUCLID_CACHE_DIR (download cache) and EUCLID_OUTPUT_DIR. "
            "Local MER pipeline: set EUCLID_MER_ROOT + EUCLID_TILE_INDEX. "
            "Auth still optional via API_TOKEN on the HTTP/MCP wrapper."
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
