"""Local Euclid Q1 MER cutout helpers for MCP / HTTP invoke.

Env:
  EUCLID_MER_ROOT       MER root (…/MER containing <TILE_ID>/<INSTRUMENT>/EUC_MER_*.fits)
  EUCLID_TILE_INDEX     FITS tile index (cols TILE_ID, RA_MIN/MAX, DEC_MIN/MAX, RA_CENTER, DEC_CENTER)
  EUCLID_OUTPUT_DIR     default output directory for cutouts (default ./euclid_cutouts)
"""
from .config import get_config
from .catalog import validate_catalog
from .tiles import query_tile_id
from .locate import locate_products
from .cutout import cutout_single, cutout_batch

__all__ = [
    "get_config",
    "validate_catalog",
    "query_tile_id",
    "locate_products",
    "cutout_single",
    "cutout_batch",
]
