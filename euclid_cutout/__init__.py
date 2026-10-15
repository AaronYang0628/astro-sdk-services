"""Euclid / generic FITS cutout helpers for MCP chaining.

Fine-grained URL→image chain:
  fetch_fits → list_hdus → read_wcs_header → sky_to_pixel → cutout2d → write_preview

Optional local MER helpers: query_tile_id, locate_products, cutout_single/batch.

Env:
  EUCLID_CACHE_DIR      HTTPS download cache (default ./euclid_cache)
  EUCLID_OUTPUT_DIR     cutout / preview output (default ./euclid_cutouts)
  EUCLID_MER_ROOT       local MER root for tile/locate pipeline
  EUCLID_TILE_INDEX     tile index FITS for local MER
"""
from .config import get_config
from .cache import fetch_fits
from .fitsio import list_hdus, read_wcs_header, sky_to_pixel, pixel_to_sky
from .stamp import cutout2d
from .preview import write_preview
from .catalog import validate_catalog
from .tiles import query_tile_id
from .locate import locate_products
from .cutout import cutout_single, cutout_batch

__all__ = [
    "get_config",
    "fetch_fits",
    "list_hdus",
    "read_wcs_header",
    "sky_to_pixel",
    "pixel_to_sky",
    "cutout2d",
    "write_preview",
    "validate_catalog",
    "query_tile_id",
    "locate_products",
    "cutout_single",
    "cutout_batch",
]
