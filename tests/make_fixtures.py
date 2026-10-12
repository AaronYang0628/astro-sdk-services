"""Create small deterministic fixture files under fixtures/ used by test cases."""
import numpy as np, os, warnings
warnings.filterwarnings("ignore")
from astropy.io import fits
from astropy.table import Table
from astropy.wcs import WCS
import astropy.units as u
D = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures")
os.makedirs(D, exist_ok=True); os.makedirs("/tmp/astro_out", exist_ok=True)
rng = np.random.default_rng(42)
ny = nx = 100
yy, xx = np.mgrid[:ny, :nx]
img = rng.normal(100, 5, (ny, nx))
stars = [(20, 30, 800), (50, 50, 1500), (75, 25, 600), (80, 80, 1000), (30, 70, 500)]
for x0, y0, a in stars:
    img += a * np.exp(-((xx - x0) ** 2 + (yy - y0) ** 2) / (2 * 2.0 ** 2))
w = WCS(naxis=2)
w.wcs.crpix = [50, 50]; w.wcs.crval = [10.684, 41.269]; w.wcs.cdelt = [-0.0002778, 0.0002778]; w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
w.wcs.cunit = ["deg", "deg"]
hdr = w.to_header(); hdr["EXPTIME"] = 30.0; hdr["DATE-OBS"] = "2026-10-01T12:00:00"; hdr["OBJECT"] = "M31 test"
fits.PrimaryHDU(img.astype("float32"), header=hdr).writeto(f"{D}/image.fits", overwrite=True)
t = Table({"id": [1, 2, 3, 4, 5], "ra": [10.1, 10.2, 10.3, 10.4, 10.5], "dec": [41.1, 41.2, 41.3, 41.4, 41.5],
           "mag": [12.1, 13.2, 14.3, 15.4, 16.5], "name": ["a", "b", "c", "d", "e"]})
t["ra"].unit = u.deg; t["dec"].unit = u.deg
t.write(f"{D}/table.fits", overwrite=True); t.write(f"{D}/table.ecsv", overwrite=True, format="ascii.ecsv")
t.write(f"{D}/table.csv", overwrite=True, format="ascii.csv")
t.write(f"{D}/table.xml", overwrite=True, format="votable")
# light curve with a 2.5 d period sinusoid + transit-like dips
tt = np.sort(rng.uniform(0, 30, 300)); yv = 1 + 0.05 * np.sin(2 * np.pi * tt / 2.5) + rng.normal(0, 0.005, 300)
Table({"time": tt, "flux": yv}).write(f"{D}/lightcurve.ecsv", overwrite=True, format="ascii.ecsv")
np.save(f"{D}/image.npy", img)
print("fixtures ok")
