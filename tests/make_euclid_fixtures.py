"""Build a tiny fake Euclid MER tree + tile index + catalog for smoke tests."""
from __future__ import annotations
import os
from pathlib import Path
import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from astropy.table import Table

ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "euclid_mock"
TILE = "999000001"
RA0, DEC0 = 150.0, 2.0


def _wcs(n=64):
    w = WCS(naxis=2)
    w.wcs.crpix = [n / 2, n / 2]
    w.wcs.cdelt = [-0.001, 0.001]  # deg/pix ~ 3.6"
    w.wcs.crval = [RA0, DEC0]
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    return w


def main():
    if ROOT.exists():
        import shutil
        shutil.rmtree(ROOT)
    mer = ROOT / "MER" / TILE / "VIS"
    mer.mkdir(parents=True)
    n = 64
    data = np.random.default_rng(0).normal(100, 5, (n, n)).astype(np.float32)
    # bright source at center
    data[n // 2 - 2 : n // 2 + 3, n // 2 - 2 : n // 2 + 3] += 50
    hdr = _wcs(n).to_header()
    fname = f"EUC_MER_BGSUB-MOSAIC-VIS_TILE{TILE}_mock.fits"
    fits.PrimaryHDU(data=data, header=hdr).writeto(mer / fname, overwrite=True)

    # FLAG product (same WCS)
    flag = (data > 110).astype(np.float32)
    fname_f = f"EUC_MER_MOSAIC-VIS-FLAG_TILE{TILE}_mock.fits"
    fits.PrimaryHDU(data=flag, header=hdr).writeto(mer / fname_f, overwrite=True)

    # tile index covering the mock pointing
    idx = Table(
        rows=[
            {
                "TILE_ID": TILE,
                "RA_MIN": RA0 - 0.5,
                "RA_MAX": RA0 + 0.5,
                "DEC_MIN": DEC0 - 0.5,
                "DEC_MAX": DEC0 + 0.5,
                "RA_CENTER": RA0,
                "DEC_CENTER": DEC0,
                "N_OBJECTS": 1,
            }
        ]
    )
    idx_path = ROOT / "tile_index.fits"
    idx.write(idx_path, format="fits", overwrite=True)

    cat = Table(rows=[{"TARGETID": "mock1", "RA": RA0, "DEC": DEC0},
                      {"TARGETID": "mock2", "RA": RA0 + 0.01, "DEC": DEC0 - 0.01}])
    cat_path = ROOT / "catalog.fits"
    cat.write(cat_path, format="fits", overwrite=True)

    print(f"wrote {ROOT}")
    print(f"  MER_ROOT={ROOT / 'MER'}")
    print(f"  TILE_INDEX={idx_path}")
    print(f"  CATALOG={cat_path}")
    print(f"  center=({RA0},{DEC0}) tile={TILE}")


if __name__ == "__main__":
    main()
