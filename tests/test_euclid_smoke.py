"""Smoke: library chain + HTTP /euclid tools without real Q1 data."""
from __future__ import annotations
import json, os, subprocess, sys, time, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
PY = sys.executable
FIX = REPO / "fixtures" / "euclid_mock"
RA0, DEC0 = 150.0, 2.0


def _post(url, body):
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def _get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode())


def test_library():
    subprocess.check_call([PY, str(HERE / "make_euclid_fixtures.py")], cwd=str(REPO))
    os.environ["EUCLID_MER_ROOT"] = str(FIX / "MER")
    os.environ["EUCLID_TILE_INDEX"] = str(FIX / "tile_index.fits")
    os.environ["EUCLID_OUTPUT_DIR"] = str(FIX / "out")
    sys.path.insert(0, str(REPO))
    import euclid_cutout as ec

    cfg = ec.get_config()
    assert cfg["mer_root_exists"] and cfg["tile_index_exists"], cfg
    v = ec.validate_catalog(str(FIX / "catalog.fits"))
    assert v["ok"] and v["n_rows"] == 2, v
    q = ec.query_tile_id(RA0, DEC0)
    assert q["found"] and q["tile_id"] == "999000001", q
    loc = ec.locate_products(q["tile_id"], file_type="BGSUB", instruments=["VIS"])
    assert loc["found"] and loc["n_products"] >= 1, loc
    r = ec.cutout_single(RA0, DEC0, size=16, file_types=["BGSUB"], instruments=["VIS"], obj_id="smoke1")
    assert r["success"] and r["n_files"] >= 1, r
    assert Path(r["files"][0]["path"]).is_file(), r
    b = ec.cutout_batch(str(FIX / "catalog.fits"), size=16, file_types=["BGSUB"], instruments=["VIS"], max_sources=2)
    assert b["n_success"] >= 1, b
    print("library OK", {"tile": q["tile_id"], "files": r["n_files"], "batch_ok": b["n_success"]})


def test_http():
    env = os.environ.copy()
    env["EUCLID_MER_ROOT"] = str(FIX / "MER")
    env["EUCLID_TILE_INDEX"] = str(FIX / "tile_index.fits")
    env["EUCLID_OUTPUT_DIR"] = str(FIX / "out_http")
    env["PYTHONPATH"] = str(REPO)
    env["MEM_LIMIT_GB"] = "2"
    # only start euclid sdk (faster than all)
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
        need = {
            "euclid_get_config",
            "euclid_validate_catalog",
            "euclid_query_tile_id",
            "euclid_locate_products",
            "euclid_cutout_single",
            "euclid_cutout_batch",
        }
        assert need <= names, names
        assert _get(f"{base}/euclid/health")["tools"] == 6

        cfg = _post(f"{base}/euclid/invoke", {"function_name": "euclid_get_config", "arguments": {}})
        assert cfg["ok"] and cfg["result"]["mer_root_exists"], cfg

        q = _post(
            f"{base}/euclid/invoke",
            {"function_name": "euclid_query_tile_id", "arguments": {"ra": RA0, "dec": DEC0}},
        )
        assert q["ok"] and q["result"]["found"], q
        tid = q["result"]["tile_id"]

        loc = _post(
            f"{base}/euclid/invoke",
            {
                "function_name": "euclid_locate_products",
                "arguments": {"tile_id": tid, "file_type": "BGSUB", "instruments": ["VIS"]},
            },
        )
        assert loc["ok"] and loc["result"]["found"], loc

        cut = _post(
            f"{base}/euclid/invoke",
            {
                "function_name": "euclid_cutout_single",
                "arguments": {
                    "ra": RA0,
                    "dec": DEC0,
                    "size": 16,
                    "file_types": ["BGSUB"],
                    "instruments": ["VIS"],
                    "obj_id": "http_smoke",
                },
            },
        )
        assert cut["ok"] and cut["result"]["success"], cut
        print("http OK", {"tools": len(names), "tile": tid, "cutout_files": cut["result"]["n_files"]})
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    test_library()
    test_http()
    print("ALL SMOKE PASSED")
