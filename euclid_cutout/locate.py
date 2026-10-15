"""Locate Euclid MER product FITS under MER_ROOT/<TILE_ID>/<INSTRUMENT>/."""
from __future__ import annotations
import os
from typing import Optional
from .config import require_mer_root
from .naming import pattern_for, parse_instrument_band, matches_file_type


def locate_products(
    tile_id: str,
    file_type: str = "BGSUB",
    instruments: Optional[list] = None,
    bands: Optional[list] = None,
    mer_root: Optional[str] = None,
) -> dict:
    """Find product FITS paths for one TILE.

    file_type: BGSUB|SCI|FLAG|WHT|RMS|BGMOD|CATALOG-PSF
    instruments: directory names e.g. ['VIS','NISP']; None = all
    bands: full band ids e.g. ['VIS','NIR-Y','DES-G']; None = all
    """
    root = require_mer_root(mer_root)
    mer_dir = root / str(tile_id)
    if not mer_dir.is_dir():
        return {
            "tile_id": str(tile_id),
            "file_type": file_type,
            "found": False,
            "products": {},
            "error": f"tile directory not found: {mer_dir}",
        }

    pat = pattern_for(file_type)
    products: dict[str, str] = {}
    for instrument_dir in sorted(os.listdir(mer_dir)):
        inst_path = mer_dir / instrument_dir
        if not inst_path.is_dir():
            continue
        if instruments is not None and instrument_dir not in instruments:
            continue
        for name in os.listdir(inst_path):
            if not name.endswith(".fits"):
                continue
            if f"EUC_MER_{pat}" not in name:
                continue
            if not matches_file_type(name, file_type):
                continue
            parsed = parse_instrument_band(name, file_type)
            if parsed is None:
                continue
            file_instrument, file_band = parsed
            full_band = (
                f"{file_instrument}-{file_band}"
                if file_instrument != file_band
                else file_band
            )
            if bands is not None and full_band not in bands:
                continue
            key = (
                f"{instrument_dir}_{file_instrument}-{file_band}"
                if file_instrument != file_band
                else f"{instrument_dir}_{file_band}"
            )
            products[key] = str(inst_path / name)

    return {
        "tile_id": str(tile_id),
        "file_type": file_type,
        "found": bool(products),
        "n_products": len(products),
        "products": products,
        "error": None if products else f"no {file_type} products under {mer_dir}",
    }
