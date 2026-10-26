"""Euclid / generic FITS cutout helpers for MCP chaining.

Fine-grained URL→image chain (use a **source** ra/dec, not FOV centre):
  fetch_fits → list_hdus → read_wcs_header → find_peak_sky|sky_to_pixel
  → cutout2d → write_preview

Input: fetch_fits(url) takes
  * an absolute local path or file:// inside EUCLID_INPUT_ROOTS (e.g. a 021 project file
    /home/scientist/project<id>/Data/x.fits on a read-only mount) — validated, used in place, no copy;
  * any http(s) FITS URL — public or presigned; query sent verbatim and redacted in outputs/errors;
    cache names use host+path only.
All other tools only read files inside EUCLID_INPUT_ROOTS / EUCLID_CACHE_DIR / EUCLID_OUTPUT_DIR
(+ MER root / bundled fixtures / EUCLID_WRITE_ROOTS) and write inside EUCLID_OUTPUT_DIR by default, or —
with an explicit output_path/output_dir — inside EUCLID_WRITE_ROOTS (e.g. a 021 project's ResearchSpace on a
read-write mount; atomic, 0644, auto-suffix unless overwrite=True). See safety.py.

Optional local MER helpers: query_tile_id, locate_products, cutout_single/batch.

Env:
  EUCLID_INPUT_ROOTS    ':'/',' separated dirs allowed as local inputs
                        (unset = /home/scientist; "" = local inputs disabled)
  EUCLID_WRITE_ROOTS    ':'/',' separated dirs allowed for explicit output_path/output_dir
                        (unset = /home/scientist; "" = only EUCLID_OUTPUT_DIR)
  EUCLID_CACHE_DIR      HTTP(S) download cache (default ./euclid_cache)
  EUCLID_OUTPUT_DIR     cutout / preview output (default ./euclid_cutouts)
  EUCLID_MER_ROOT       local MER root for tile/locate pipeline
  EUCLID_TILE_INDEX     tile index FITS for local MER
"""
from .config import get_config
from .cache import fetch_fits
from .fitsio import list_hdus, read_wcs_header, sky_to_pixel, pixel_to_sky, find_peak_sky
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
    "find_peak_sky",
    "cutout2d",
    "write_preview",
    "validate_catalog",
    "query_tile_id",
    "locate_products",
    "cutout_single",
    "cutout_batch",
]
