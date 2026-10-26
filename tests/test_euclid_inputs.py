"""Input handling: presigned URLs (query preserved + redacted), Range / no-Range fallback,
expiry error, FITS magic detection, and the path sandbox. Run: python tests/test_euclid_inputs.py"""
from __future__ import annotations
import json, os, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(HERE))
TMP = Path(tempfile.mkdtemp(prefix="euclid_inputs_", dir=str(REPO / "fixtures" / "euclid_mock")))
os.environ["EUCLID_CACHE_DIR"] = str(TMP / "cache")
os.environ["EUCLID_OUTPUT_DIR"] = str(TMP / "out")
for k in ("EUCLID_MER_ROOT", "EUCLID_TILE_INDEX"):
    os.environ.pop(k, None)

import euclid_cutout as ec  # noqa: E402
from euclid_cutout.cache import FetchError  # noqa: E402
import fits_http_server  # noqa: E402

MOCK = REPO / "fixtures/euclid_mock/MER/999000001/VIS/EUC_MER_BGSUB-MOSAIC-VIS_TILE999000001_mock.fits"
DATA = MOCK.read_bytes()


def _raises(fn, exc, needle=""):
    try:
        fn()
    except exc as e:
        assert needle.lower() in str(e).lower(), str(e)
        return str(e)
    raise AssertionError(f"{fn} did not raise {exc}")


def _no_secret(obj, query):
    s = json.dumps(obj) if not isinstance(obj, str) else obj
    assert "Signature" not in s and "ab%2Bcd" not in s and query not in s, s


def main():
    srv, base, query, seen = fits_http_server.start(DATA)
    try:
        signed = f"{base}/signed/upload/8f3a2c?{query}"  # no extension, octet-stream
        # 1) missing query -> 403 access denied (no signature leaked either way)
        e = _raises(lambda: ec.fetch_fits(f"{base}/signed/upload/8f3a2c"), FetchError, "access denied")
        # 2) presigned prefix via Range
        r = ec.fetch_fits(signed, max_bytes=5760)
        _no_secret(r, query)
        assert r["size_bytes"] == 5760 and r["range_honored"] is True and r["remote_size_bytes"] == len(DATA), r
        assert r["format"] == "fits" and r["source"].endswith("/signed/upload/8f3a2c?<redacted>"), r
        name = Path(r["path"]).name
        assert name.endswith("_8f3a2c.fits") and "Signature" not in name, name
        assert seen[-1]["query"] == query and seen[-1]["range"] == "bytes=0-5759", seen[-1]
        meta = Path(r["path"] + ".meta").read_text()
        _no_secret(meta, query)
        # 3) resume to full via Range, then cache hit; same object with a *different* signature -> same cache file
        full = ec.fetch_fits(signed)
        assert full["complete"] and full["size_bytes"] == len(DATA) and seen[-1]["range"] == "bytes=5760-", (full, seen[-1])
        assert Path(full["path"]).read_bytes() == DATA
        again = ec.fetch_fits(f"{base}/signed/upload/8f3a2c?OSSAccessKeyId=x&Expires=9999999999&Signature=other")
        assert again["from_cache"] and again["path"] == full["path"], again
        # 4) server ignores Range -> stream from 0, truncate at max_bytes; resume on 200 rewrites (no duplication)
        nr = f"{base}/norange/obj.fits?{query}"
        p = ec.fetch_fits(nr, max_bytes=5760)
        assert p["size_bytes"] == 5760 and p["range_honored"] is False, p
        f2 = ec.fetch_fits(nr)
        assert f2["size_bytes"] == len(DATA) and Path(f2["path"]).read_bytes() == DATA, f2
        # 5) expired signature -> clear message, redacted
        e = _raises(lambda: ec.fetch_fits(f"{base}/expired/x?{query}"), FetchError, "expired")
        _no_secret(e, query); assert "fresh" in e
        e = _raises(lambda: ec.fetch_fits(f"{base}/signed/y?OSSAccessKeyId=a&Expires=1000&Signature=zz"), FetchError, "expired")
        # 6) not FITS (e.g. login page) rejected by magic
        _raises(lambda: ec.fetch_fits(f"{base}/notfits/page"), FetchError, "not FITS")
        # 7) connection error never echoes the signed URL
        e = _raises(lambda: ec.fetch_fits(f"http://127.0.0.1:1/a.fits?{query}", timeout=3), FetchError, "download failed")
        _no_secret(e, query)
        # 8) downstream chain on the downloaded file
        peak = ec.find_peak_sky(full["path"]); assert peak["ok"], peak
        cut = ec.cutout2d(full["path"], peak["ra"], peak["dec"], size=64, obj_id="../../evil")
        assert cut["success"] and Path(cut["fits_path"]).resolve().is_relative_to(Path(os.environ["EUCLID_OUTPUT_DIR"]).resolve()), cut
        prev = ec.write_preview(cut["fits_path"], inline_image=False); assert Path(prev["preview_path"]).is_file()
        # 9) tile-compressed .fz (served without extension) is detected and readable
        from astropy.io import fits
        import io, numpy as np
        with fits.open(MOCK) as h:
            img = h[0].data.astype("float32"); hdr = h[0].header
        buf = io.BytesIO(); fits.HDUList([fits.PrimaryHDU(), fits.CompImageHDU(img, header=hdr)]).writeto(buf)
        srv2, base2, q2, _ = fits_http_server.start(buf.getvalue())
        try:
            fz = ec.fetch_fits(f"{base2}/signed/fzobj?{q2}")
            hd = ec.list_hdus(fz["path"])
            pk = ec.find_peak_sky(fz["path"], hdu_index=1)
            assert fz["format"] == "fits" and pk["ok"], (fz, hd, pk)
        finally:
            srv2.shutdown()
        # 10) sandbox
        _raises(lambda: ec.fetch_fits("/etc/passwd"), ValueError, "http")
        _raises(lambda: ec.fetch_fits("file:///etc/passwd"), ValueError, "http")
        for fn in (ec.list_hdus, ec.read_wcs_header, ec.find_peak_sky, ec.validate_catalog):
            _raises(lambda fn=fn: fn("/etc/passwd"), PermissionError, "not allowed")
        _raises(lambda: ec.list_hdus(os.environ["EUCLID_CACHE_DIR"] + "/../../../../../../etc/passwd"), PermissionError)
        link = TMP / "cache" / "link.fits"; link.symlink_to("/etc/passwd")
        _raises(lambda: ec.list_hdus(str(link)), PermissionError)
        _raises(lambda: ec.write_preview(cut["fits_path"], output_path="/tmp/evil.png"), PermissionError)
        _raises(lambda: ec.cutout2d(full["path"], peak["ra"], peak["dec"], output_path="/etc/x.fits"), PermissionError)
        _raises(lambda: ec.locate_products(1, mer_root="/"), ValueError, "EUCLID_MER_ROOT")
        os.environ["EUCLID_MER_ROOT"] = str(REPO / "fixtures/euclid_mock/MER")
        _raises(lambda: ec.locate_products(1, mer_root="/etc"), PermissionError, "mer_root")
        _raises(lambda: ec.query_tile_id(150, 2, tile_index="/etc/passwd"), PermissionError)
        print("INPUT TESTS PASSED", {"cache_file": name, "source": r["source"], "requests": len(seen)})
    finally:
        srv.shutdown()
        import shutil; shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    main()
