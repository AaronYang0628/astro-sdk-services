"""Smoke: fine-grained URL→cutout→preview chain + local MER mock."""
from __future__ import annotations
import json, os, subprocess, sys, time, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
PY = sys.executable
FIX = REPO / "fixtures" / "euclid_mock"
RA0, DEC0 = 150.0, 2.0
REAL_URL = (
    "https://casdc.china-vo.org/mirror/Euclid-Q1/VIS/2686/"
    "EUC_VIS_SWL-BKG-002686-01-1-0000000__20241017T042432.874944Z.fits"
)


def _post(url, body):
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read().decode())


def _get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode())


def test_library_mock():
    subprocess.check_call([PY, str(HERE / "make_euclid_fixtures.py")], cwd=str(REPO))
    os.environ["EUCLID_MER_ROOT"] = str(FIX / "MER")
    os.environ["EUCLID_TILE_INDEX"] = str(FIX / "tile_index.fits")
    os.environ["EUCLID_OUTPUT_DIR"] = str(FIX / "out")
    os.environ["EUCLID_CACHE_DIR"] = str(FIX / "cache")
    sys.path.insert(0, str(REPO))
    import importlib
    import euclid_cutout
    importlib.reload(euclid_cutout)
    import euclid_cutout.fitsio as fitsio
    import euclid_cutout.stamp as stamp
    importlib.reload(fitsio)
    importlib.reload(stamp)
    importlib.reload(euclid_cutout)
    ec = euclid_cutout

    fits_path = str(FIX / "MER/999000001/VIS/EUC_MER_BGSUB-MOSAIC-VIS_TILE999000001_mock.fits")
    f = ec.fetch_fits(fits_path)
    peak = ec.find_peak_sky(f["path"])
    assert peak["ok"], peak
    cut = ec.cutout2d(f["path"], peak["ra"], peak["dec"], obj_id="fine_mock")
    assert cut["success"] and cut["inside"] and Path(cut["fits_path"]).is_file(), cut
    prev = ec.write_preview(cut["fits_path"], format="png")
    assert Path(prev["preview_path"]).is_file(), prev
    # MER convenience
    q = ec.query_tile_id(RA0, DEC0)
    assert q["found"], q
    print("library mock OK", {"peak": [peak["ra"], peak["dec"]], "png": prev["preview_path"]})


def test_library_real_url():
    sys.path.insert(0, str(REPO))
    os.environ["EUCLID_CACHE_DIR"] = str(REPO / "fixtures" / "euclid_mock" / "cache")
    os.environ["EUCLID_OUTPUT_DIR"] = str(REPO / "fixtures" / "euclid_mock" / "out_url")
    import importlib
    import euclid_cutout
    importlib.reload(euclid_cutout)
    ec = euclid_cutout

    try:
        f = ec.fetch_fits(REAL_URL, max_bytes=25_000_000, timeout=180)
    except Exception as e:
        print("REAL_URL unreachable, skip:", type(e).__name__, e)
        return False
    assert f["ok"] and Path(f["path"]).is_file(), f

    wcs = ec.read_wcs_header(f["path"], hdu_index=1)
    fov = wcs["fov_center"]
    peak = ec.find_peak_sky(f["path"], hdu_index=1)
    assert peak["ok"] and peak["inside"] if "inside" in peak else True, peak

    # BEFORE bug: cutting at FOV centre → flat background
    bad = ec.cutout2d(f["path"], fov["ra"], fov["dec"], hdu_index=1, obj_id="casdc_vis_2686_FOVcenter")
    # AFTER fix: cutting at peak/source
    good = ec.cutout2d(f["path"], peak["ra"], peak["dec"], hdu_index=1, obj_id="casdc_vis_2686")
    assert good["success"] and good["inside"], good
    assert good["stats"]["max"] > bad["stats"]["max"], (good["stats"], bad["stats"])

    prev = ec.write_preview(good["fits_path"], format="png")
    prev_bad = ec.write_preview(bad["fits_path"], format="png",
                                output_path=str(Path(os.environ["EUCLID_OUTPUT_DIR"]) / "previews" / "casdc_vis_2686_FOVcenter.png"))
    assert Path(prev["preview_path"]).is_file(), prev
    print(
        "library real URL OK",
        {
            "fov_center": [fov["ra"], fov["dec"]],
            "peak_source": [peak["ra"], peak["dec"], peak["x"], peak["y"]],
            "fov_stats": bad["stats"],
            "peak_stats": good["stats"],
            "fits": good["fits_path"],
            "png": prev["preview_path"],
            "png_fov_wrong": prev_bad["preview_path"],
        },
    )
    return True


def test_http():
    env = os.environ.copy()
    env["EUCLID_MER_ROOT"] = str(FIX / "MER")
    env["EUCLID_TILE_INDEX"] = str(FIX / "tile_index.fits")
    env["EUCLID_OUTPUT_DIR"] = str(FIX / "out_http")
    env["EUCLID_CACHE_DIR"] = str(FIX / "cache")
    env["PYTHONPATH"] = str(REPO)
    env["MEM_LIMIT_GB"] = "2"
    proc = subprocess.Popen(
        [PY, "-m", "uvicorn", "sdks.euclid:app", "--host", "127.0.0.1", "--port", "9199"],
        cwd=str(REPO),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        base = "http://127.0.0.1:9199"
        for _ in range(40):
            try:
                h = _get(f"{base}/euclid/health")
                if h.get("ok"):
                    break
            except Exception:
                time.sleep(0.25)
        else:
            out = proc.stdout.read(4000).decode(errors="replace") if proc.stdout else ""
            raise RuntimeError(f"server failed to start\n{out}")

        tools = _get(f"{base}/euclid/tools")
        names = {t["name"] for t in tools}
        assert "euclid_find_peak_sky" in names and "euclid_cutout2d" in names, names
        assert h["tools"] == len(tools) == 14

        fits_path = str(FIX / "MER/999000001/VIS/EUC_MER_BGSUB-MOSAIC-VIS_TILE999000001_mock.fits")
        f = _post(f"{base}/euclid/invoke", {"function_name": "euclid_fetch_fits", "arguments": {"url_or_path": fits_path}})
        path = f["result"]["path"]
        peak = _post(f"{base}/euclid/invoke", {"function_name": "euclid_find_peak_sky", "arguments": {"path": path}})
        assert peak["ok"], peak
        cut = _post(
            f"{base}/euclid/invoke",
            {
                "function_name": "euclid_cutout2d",
                "arguments": {
                    "path": path,
                    "ra": peak["result"]["ra"],
                    "dec": peak["result"]["dec"],
                    "size": 1024,
                    "obj_id": "http_fine",
                },
            },
        )
        assert cut["ok"] and cut["result"].get("fits_path"), cut
        prev = _post(
            f"{base}/euclid/invoke",
            {"function_name": "euclid_write_preview", "arguments": {"fits_path": cut["result"]["fits_path"], "format": "png"}},
        )
        assert prev["ok"] and Path(prev["result"]["preview_path"]).is_file(), prev
        print("http OK", {"tools": len(names), "png": prev["result"]["preview_path"]})
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    test_library_mock()
    real = test_library_real_url()
    test_http()
    print("ALL SMOKE PASSED", {"real_url": bool(real)})
