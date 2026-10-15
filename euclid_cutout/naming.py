"""Euclid MER product naming (aligned with Euclid-Image-Cutout-Service)."""
from __future__ import annotations
from typing import Optional

# user-facing type -> filename substring under EUC_MER_
FILE_PATTERN = {
    "SCI": "BGSUB-MOSAIC",
    "BGSUB": "BGSUB-MOSAIC",
    "BGMOD": "BGMOD",
    "FLAG": "MOSAIC",
    "WHT": "MOSAIC",
    "RMS": "MOSAIC",
    "CATALOG-PSF": "CATALOG-PSF",
}

# directory name under TILE -> filename instrument prefix
INSTRUMENT_PREFIX = {
    "DECAM": "DES",
    "NISP": "NIR",
    "VIS": "VIS",
    "HSC": "WISHES",
    "GPC": "PANSTARRS",
    "MEGACAM": "CFIS",
}


def pattern_for(file_type: str) -> str:
    return FILE_PATTERN.get(file_type, file_type)


def parse_instrument_band(filename: str, file_type: str) -> Optional[tuple[str, str]]:
    try:
        notile = filename.split("_TILE")[0]
        actual = "FLAG" if file_type == "WHT" else file_type
        if actual in ("FLAG", "RMS"):
            inst_band = notile.split("EUC_MER_MOSAIC-")[-1].split(f"-{actual}")[0]
        else:
            pat = pattern_for(file_type)
            inst_band = notile.split(f"EUC_MER_{pat}-")[-1]
        parts = inst_band.split("-")
        if len(parts) == 1:
            return parts[0], parts[0]
        return parts[0], "-".join(parts[1:])
    except Exception:
        return None


def matches_file_type(filename: str, file_type: str) -> bool:
    if "FINAL-CAT" in filename:
        return False
    if file_type in ("WHT", "FLAG"):
        return "-FLAG" in filename
    if file_type == "RMS":
        return "-RMS" in filename
    if file_type in ("SCI", "BGSUB"):
        return "BGSUB" in filename
    if file_type == "BGMOD":
        return "BGMOD" in filename
    if file_type == "CATALOG-PSF":
        return "CATALOG-PSF" in filename
    return pattern_for(file_type) in filename
