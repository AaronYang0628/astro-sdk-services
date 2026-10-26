"""Local project-file inputs (EUCLID_INPUT_ROOTS): allowlist, traversal/symlink escape, file://,
MOC/table-only FITS error, full chain in place, and the same over HTTP /invoke + MCP.
Run: python tests/test_euclid_local_inputs.py"""
from __future__ import annotations
import base64, json, os, shutil, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))
MOCK = REPO / "fixtures/euclid_mock/MER/999000001/VIS/EUC_MER_BGSUB-MOSAIC-VIS_TILE999000001_mock.fits"

TMP = Path(tempfile.mkdtemp(prefix="euclid_local_")).resolve()
SCI = TMP / "home" / "scientist"
DATA = SCI / "project2114525713776963586" / "Data"
OUTSIDE = TMP / "outside"
for d in (DATA, OUTSIDE):
    d.mkdir(parents=True)
os.environ["EUCLID_CACHE_DIR"] = str(TMP / "srv" / "cache")
os.environ["EUCLID_OUTPUT_DIR"] = str(TMP / "srv" / "out")
os.environ["EUCLID_INPUT_ROOTS"] = f"{SCI},/nonexistent-root"
for k in ("EUCLID_MER_ROOT", "EUCLID_TILE_INDEX"):
    os.environ.pop(k, None)

import numpy as np  # noqa: E402
from astropy.io import fits  # noqa: E402
import euclid_cutout as ec  # noqa: E402


def _raises(fn, exc, *needles):
    try:
        fn()
    except exc as e:
        for n in needles:
            assert n.lower() in str(e).lower(), (n, str(e))
        return str(e)
    raise AssertionError(f"did not raise {exc.__name__}")


def make_files():
    img = DATA / "VIS_upload.fit"  # .fit, uploaded by the user
    shutil.copy(MOCK, img)
    noext = DATA / "upload_noext"
    shutil.copy(MOCK, noext)
    secret = OUTSIDE / "secret.fits"
    shutil.copy(MOCK, secret)
    (DATA / "escape.fits").symlink_to(secret)
    (DATA / "notes.txt").write_text("hello")
    # MOC-like file: empty primary + BINTABLE of NUNIQ (like euclid-...moc.fits)
    col = fits.Column(name="UNIQ", format="K", array=np.array([1024, 4100, 16400], dtype=np.int64))
    t = fits.BinTableHDU.from_columns([col])
    t.header["PIXTYPE"] = "HEALPIX"; t.header["ORDERING"] = "NUNIQ"; t.header["MOCORDER"] = 10
    moc = DATA / "euclid-q1-moc.fits"
    fits.HDUList([fits.PrimaryHDU(), t]).writeto(moc)
    return img, noext, secret, moc


def library():
    img, noext, secret, moc = make_files()
    roots = ec.get_config()["input_roots"]
    assert str(SCI) in roots, roots
    # accept: absolute path in place (no copy into cache)
    f = ec.fetch_fits(str(img))
    assert f["ok"] and f["local"] and f["path"] == str(img) and f["format"] == "fits", f
    assert not Path(os.environ["EUCLID_CACHE_DIR"]).exists() or not any(Path(os.environ["EUCLID_CACHE_DIR"]).iterdir())
    assert ec.fetch_fits(f"file://{img}")["path"] == str(img)
    assert ec.fetch_fits(url_or_path=str(noext))["format"] == "fits"
    # chain on the in-place file
    h = ec.list_hdus(f["path"]); assert h["image_hdus"] == [0] and "note" not in h, h
    pk = ec.find_peak_sky(f["path"]); assert pk["ok"], pk
    cut = ec.cutout2d(f["path"], pk["ra"], pk["dec"], size=64, obj_id="local_chain")
    assert cut["success"] and Path(cut["fits_path"]).resolve().is_relative_to(Path(os.environ["EUCLID_OUTPUT_DIR"]).resolve())
    prev = ec.write_preview(cut["fits_path"], inline_image=True)
    assert prev["_mcp_images"] and Path(prev["preview_path"]).is_file()
    assert img.read_bytes() == MOCK.read_bytes()  # untouched
    # reject: outside roots / traversal / symlink escape / not found / relative / remote file:// / non-FITS
    e = _raises(lambda: ec.fetch_fits(str(secret)), PermissionError, "outside the input roots", str(SCI), "http(s)")
    _raises(lambda: ec.fetch_fits(str(DATA / ".." / ".." / ".." / ".." / "outside" / "secret.fits")), PermissionError, "outside")
    _raises(lambda: ec.fetch_fits(str(DATA / "escape.fits")), PermissionError, "outside")
    _raises(lambda: ec.list_hdus(str(DATA / "escape.fits")), PermissionError, "not allowed")
    _raises(lambda: ec.find_peak_sky(str(secret)), PermissionError, "not allowed", str(SCI))
    _raises(lambda: ec.fetch_fits("/etc/passwd"), PermissionError, "outside", str(SCI))
    _raises(lambda: ec.fetch_fits("file:///etc/passwd"), PermissionError, "outside")
    _raises(lambda: ec.fetch_fits(str(DATA / "missing.fits")), FileNotFoundError, "not found", str(SCI))
    _raises(lambda: ec.fetch_fits("Data/VIS_upload.fit"), ValueError, "absolute")
    _raises(lambda: ec.fetch_fits(f"file://evil.example.com{img}"), ValueError, "local path")
    _raises(lambda: ec.fetch_fits("ftp://example.com/x.fits"), ValueError, "scheme")
    _raises(lambda: ec.fetch_fits(str(DATA / "notes.txt")), Exception, "not a FITS")
    # read-only: cannot write into the input root
    _raises(lambda: ec.cutout2d(f["path"], pk["ra"], pk["dec"], output_path=str(DATA / "x.fits")), PermissionError)
    _raises(lambda: ec.write_preview(cut["fits_path"], output_path=str(DATA / "x.png")), PermissionError)
    # MOC / table-only FITS
    m = ec.fetch_fits(str(moc)); assert m["ok"] and m["format"] == "fits"
    lh = ec.list_hdus(m["path"])
    assert lh["image_hdus"] == [] and "no image HDU (this looks like a MOC" in lh["note"], lh
    for fn in (lambda: ec.find_peak_sky(m["path"]), lambda: ec.read_wcs_header(m["path"]),
               lambda: ec.read_wcs_header(m["path"], hdu_index=1), lambda: ec.cutout2d(m["path"], 150, 2),
               lambda: ec.write_preview(m["path"]), lambda: ec.sky_to_pixel(m["path"], 150, 2)):
        _raises(fn, ValueError, "no image HDU (this looks like a MOC")
    # roots unset -> local inputs disabled (as before)
    os.environ["EUCLID_INPUT_ROOTS"] = ""
    _raises(lambda: ec.fetch_fits(str(img)), ValueError, "EUCLID_INPUT_ROOTS not set", "http(s)")
    _raises(lambda: ec.list_hdus(str(img)), PermissionError, "not allowed")
    os.environ["EUCLID_INPUT_ROOTS"] = f"{SCI},/nonexistent-root"
    print("library local inputs OK", {"roots": roots, "peak": [pk["ra"], pk["dec"]]})
    return img, moc


def _post(url, body, headers=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json", **(headers or {})}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def over_http(img, moc):
    env = dict(os.environ, SDK="euclid")
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "sdks.euclid:app", "--host", "127.0.0.1", "--port", "9198"],
                            cwd=str(REPO), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = "http://127.0.0.1:9198/euclid"
    try:
        for _ in range(80):
            try:
                urllib.request.urlopen(f"{base}/health", timeout=2); break
            except Exception:
                time.sleep(0.25)
        inv = lambda n, a: _post(f"{base}/invoke", {"function_name": n, "arguments": a})
        f = inv("euclid_fetch_fits", {"url": str(img)}); assert f["ok"] and f["result"]["path"] == str(img), f
        bad = inv("euclid_fetch_fits", {"url": "/etc/passwd"}); assert not bad["ok"] and str(SCI) in bad["error"], bad
        m = inv("euclid_find_peak_sky", {"path": str(moc)}); assert not m["ok"] and "MOC" in m["error"], m

        def mcp(name, args):
            r = _post(f"{base}/mcp", {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": args}},
                      {"accept": "application/json, text/event-stream"})
            return r["result"]
        pk = json.loads(mcp("euclid_find_peak_sky", {"path": f["result"]["path"]})["content"][0]["text"])["result"]
        c = json.loads(mcp("euclid_cutout2d", {"path": str(img), "ra": pk["ra"], "dec": pk["dec"], "size": 128, "obj_id": "mcp_local"})["content"][0]["text"])["result"]
        res = mcp("euclid_write_preview", {"fits_path": c["fits_path"]})
        assert [b["type"] for b in res["content"]] == ["text", "image"]
        png = base64.b64decode(res["content"][1]["data"]); assert png[:4] == b"\x89PNG"
        print("http/mcp local inputs OK", {"image_bytes": len(png)})
    finally:
        proc.terminate(); proc.wait(timeout=10)


if __name__ == "__main__":
    try:
        img, moc = library()
        over_http(img, moc)
        print("LOCAL INPUT TESTS PASSED")
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
