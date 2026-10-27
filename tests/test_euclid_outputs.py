"""Explicit output paths (output_path / output_dir) under EUCLID_WRITE_ROOTS, e.g. a 021 project's ResearchSpace.
Covers: writes into a temp root, outside-root / '..' / symlink escapes, bad extension, no-overwrite auto-suffix,
overwrite=True, read-only root -> clear error, "" disabled, directory output_path, default unchanged,
project_relpath, 0644 + no temp leftovers, cutout_single/batch output_dir, and the same over MCP.
Run: python tests/test_euclid_outputs.py"""
from __future__ import annotations
import base64, json, os, shutil, stat, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))
MOCK_ROOT = REPO / "fixtures/euclid_mock"
MOCK = MOCK_ROOT / "MER/999000001/VIS/EUC_MER_BGSUB-MOSAIC-VIS_TILE999000001_mock.fits"

TMP = Path(tempfile.mkdtemp(prefix="euclid_out_")).resolve()
SCI = TMP / "home" / "scientist"
PROJ = SCI / "project2114525713776963586"
RS = PROJ / "ResearchSpace"
DATA = PROJ / "Data"
OUTSIDE = TMP / "outside"
SRV_OUT = TMP / "srv" / "out"
for d in (RS, DATA, OUTSIDE):
    d.mkdir(parents=True)
os.environ["EUCLID_CACHE_DIR"] = str(TMP / "srv" / "cache")
os.environ["EUCLID_OUTPUT_DIR"] = str(SRV_OUT)
os.environ["EUCLID_INPUT_ROOTS"] = str(SCI)
os.environ["EUCLID_WRITE_ROOTS"] = f"{SCI},/nonexistent-write-root"
for k in ("EUCLID_MER_ROOT", "EUCLID_TILE_INDEX"):
    os.environ.pop(k, None)

import euclid_cutout as ec  # noqa: E402
from euclid_cutout import safety  # noqa: E402


def _raises(fn, exc, *needles):
    try:
        fn()
    except exc as e:
        for n in needles:
            assert n.lower() in str(e).lower(), (n, str(e))
        return str(e)
    raise AssertionError(f"did not raise {exc.__name__}")


def _mode(p):
    return stat.S_IMODE(os.stat(p).st_mode)


def _no_tmp(d):
    left = [p.name for p in Path(d).rglob(".tmp-*")]
    assert not left, left


def library():
    img = DATA / "VIS_upload.fits"
    shutil.copy(MOCK, img)
    pk = ec.find_peak_sky(str(img))
    ra, dec = pk["ra"], pk["dec"]
    cfg = ec.get_config(); assert cfg["write_roots"][0] == str(SCI), cfg

    # --- default unchanged (no output_path): EUCLID_OUTPUT_DIR/cutouts|previews, overwritten in place
    c0 = ec.cutout2d(str(img), ra, dec, size=32, obj_id="dflt")
    assert c0["fits_path"] == str(SRV_OUT / "cutouts" / "dflt.fits") == c0["saved_path"], c0
    assert "project_relpath" not in c0
    c0b = ec.cutout2d(str(img), ra, dec, size=32, obj_id="dflt")
    assert c0b["fits_path"] == c0["fits_path"]  # default path is still overwritten, no suffix
    p0 = ec.write_preview(c0["fits_path"])
    assert p0["preview_path"] == str(SRV_OUT / "previews" / "dflt.png") and p0["_mcp_images"], p0

    # --- file output_path into ResearchSpace
    c = ec.cutout2d(str(img), ra, dec, size=32, obj_id="vis1", output_path=str(RS / "vis1.fits"))
    assert c["saved_path"] == c["fits_path"] == str(RS / "vis1.fits"), c
    assert c["project_relpath"] == "ResearchSpace/vis1.fits" and c["project_dir"] == str(PROJ), c
    assert _mode(c["saved_path"]) == 0o644
    p = ec.write_preview(c["fits_path"], output_path=str(RS / "vis1.png"))
    assert p["saved_path"] == p["preview_path"] == str(RS / "vis1.png") and p["project_relpath"] == "ResearchSpace/vis1.png"
    assert p["_mcp_images"][0]["path"] == str(RS / "vis1.png") and p["inline_image"] is True  # image block kept
    assert Path(p["saved_path"]).read_bytes()[:4] == b"\x89PNG" and _mode(p["saved_path"]) == 0o644
    # jpg inferred from extension
    j = ec.write_preview(c["fits_path"], output_path=str(RS / "vis1.jpg"))
    assert j["format"] == "jpg" and j["mime_type"] == "image/jpeg" and Path(j["saved_path"]).read_bytes()[:2] == b"\xff\xd8"
    _raises(lambda: ec.write_preview(c["fits_path"], output_path=str(RS / "x.png"), format="jpg"), ValueError, "does not match")
    # .fit and .fits.gz cutouts
    g = ec.cutout2d(str(img), ra, dec, size=32, output_path=str(RS / "gz" / "vis1.fits.gz"))
    assert g["saved_path"].endswith("vis1.fits.gz") and Path(g["saved_path"]).read_bytes()[:2] == b"\x1f\x8b"
    assert ec.list_hdus(g["saved_path"])["image_hdus"] == [0]
    f2 = ec.cutout2d(str(img), ra, dec, size=32, output_path=str(RS / "vis1.fit"))
    assert f2["saved_path"].endswith("vis1.fit")

    # --- no overwrite -> auto-suffix; overwrite=True replaces
    c2 = ec.cutout2d(str(img), ra, dec, size=32, output_path=str(RS / "vis1.fits"))
    assert c2["saved_path"] == str(RS / "vis1_1.fits"), c2
    c3 = ec.cutout2d(str(img), ra, dec, size=32, output_path=str(RS / "vis1.fits"))
    assert c3["saved_path"] == str(RS / "vis1_2.fits"), c3
    g2 = ec.cutout2d(str(img), ra, dec, size=32, output_path=str(RS / "gz" / "vis1.fits.gz"))
    assert g2["saved_path"] == str(RS / "gz" / "vis1_1.fits.gz"), g2
    p2 = ec.write_preview(c["fits_path"], output_path=str(RS / "vis1.png"))
    assert p2["saved_path"] == str(RS / "vis1_1.png") and p2["_mcp_images"][0]["path"] == p2["saved_path"]
    before = (RS / "vis1.fits").stat().st_mtime_ns
    time.sleep(0.01)
    c4 = ec.cutout2d(str(img), ra, dec, size=48, output_path=str(RS / "vis1.fits"), overwrite=True)
    assert c4["saved_path"] == str(RS / "vis1.fits") and c4["shape"] == [48, 48]
    assert (RS / "vis1.fits").stat().st_mtime_ns != before and not (RS / "vis1_3.fits").exists()

    # --- directory output_path (trailing '/' creates it below the existing project; existing dir w/o '/')
    d1 = ec.cutout2d(str(img), ra, dec, size=32, obj_id="dirobj", output_path=str(RS / "cutouts") + "/")
    assert d1["saved_path"] == str(RS / "cutouts" / "dirobj.fits") and d1["project_relpath"] == "ResearchSpace/cutouts/dirobj.fits"
    d2 = ec.write_preview(d1["fits_path"], output_path=str(RS / "cutouts"))
    assert d2["saved_path"] == str(RS / "cutouts" / "dirobj.png"), d2
    d3 = ec.write_preview(d1["fits_path"], output_path=str(RS / "cutouts"), format="jpg")
    assert d3["saved_path"] == str(RS / "cutouts" / "dirobj.jpg")
    # relative output_path keeps the old meaning (inside EUCLID_OUTPUT_DIR)
    r = ec.cutout2d(str(img), ra, dec, size=32, output_path="sub/rel.fits")
    assert r["saved_path"] == str(SRV_OUT / "sub" / "rel.fits"), r
    # a written file under the write root is readable by the next tool (chain into ResearchSpace)
    assert ec.list_hdus(c["fits_path"])["image_hdus"] == [0]

    # --- rejections
    _raises(lambda: ec.cutout2d(str(img), ra, dec, output_path=str(OUTSIDE / "x.fits")), PermissionError, "outside the output roots")
    _raises(lambda: ec.write_preview(c["fits_path"], output_path="/etc/x.png"), PermissionError, "outside")
    _raises(lambda: ec.cutout2d(str(img), ra, dec, output_path=str(RS) + "/../../../../outside/x.fits"), PermissionError, "..")
    _raises(lambda: ec.cutout2d(str(img), ra, dec, output_path="../x.fits"), PermissionError, "..")
    (RS / "link_out").symlink_to(OUTSIDE)                      # symlinked dir pointing outside
    _raises(lambda: ec.cutout2d(str(img), ra, dec, output_path=str(RS / "link_out" / "x.fits")), PermissionError, "outside")
    _raises(lambda: ec.cutout2d(str(img), ra, dec, output_path=str(RS / "link_out") + "/"), PermissionError, "outside")
    (OUTSIDE / "victim.fits").write_bytes(b"keep")
    (RS / "victim.fits").symlink_to(OUTSIDE / "victim.fits")  # symlinked file pointing outside
    _raises(lambda: ec.cutout2d(str(img), ra, dec, output_path=str(RS / "victim.fits"), overwrite=True), PermissionError, "outside")
    assert (OUTSIDE / "victim.fits").read_bytes() == b"keep"
    assert not any(OUTSIDE.glob("*.fits")) or [x.name for x in OUTSIDE.iterdir()] == ["victim.fits"]
    for bad in ("x.txt", "x.py", "x.sh", "x", "x.fits.txt"):
        _raises(lambda: ec.cutout2d(str(img), ra, dec, output_path=str(RS / bad)), ValueError, "extension not allowed")
    _raises(lambda: ec.cutout2d(str(img), ra, dec, output_path=str(RS / "x.png")), ValueError, "extension not allowed")
    _raises(lambda: ec.write_preview(c["fits_path"], output_path=str(RS / "x.fits")), ValueError, "extension not allowed")
    _raises(lambda: ec.cutout2d(str(img), ra, dec, output_path="https://example.com/x.fits"), ValueError, "not a URL")
    # no dir creation at/above the root or in a non-existent project folder
    _raises(lambda: ec.cutout2d(str(img), ra, dec, output_path=str(SCI / "x.fits")), PermissionError, "not the root")
    _raises(lambda: ec.cutout2d(str(img), ra, dec, output_path=str(SCI / "project_missing" / "ResearchSpace" / "x.fits")),
            PermissionError, "existing project folder")
    assert not (SCI / "project_missing").exists()
    _raises(lambda: ec.cutout2d(str(img), ra, dec, output_path="/nonexistent-write-root/p1/x.fits"), PermissionError, "not writable on MCP server")

    # --- read-only project storage -> clear error (simulated with chmod; box runs as non-root)
    ro = SCI / "project_ro"
    (ro / "ResearchSpace").mkdir(parents=True)
    os.chmod(ro / "ResearchSpace", 0o555); os.chmod(ro, 0o555)
    try:
        if os.access(ro / "ResearchSpace", os.W_OK):
            print("  (skip read-only check: running as root)")
        else:
            for out in (ro / "ResearchSpace" / "x.png", ro / "ResearchSpace" / "new" / "x.png"):
                e = _raises(lambda: ec.write_preview(c["fits_path"], output_path=str(out)), PermissionError,
                            "output_path not writable on MCP server", "no write permission", "read-write", "image_base64")
            e2 = _raises(lambda: ec.cutout2d(str(img), ra, dec, output_path=str(ro / "ResearchSpace") + "/"), PermissionError, "not writable")
    finally:
        os.chmod(ro, 0o755); os.chmod(ro / "ResearchSpace", 0o755)
    # writer-level EROFS/EACCES also maps to the clear error (e.g. directory writable per mode bits, fs read-only)
    import errno
    def _erofs(t):
        raise OSError(errno.EROFS, "Read-only file system", str(t))
    _raises(lambda: safety.atomic_write(RS / "erofs.png", _erofs), PermissionError, "not writable on MCP server")
    assert not (RS / "erofs.png").exists()

    # --- "" disables external writes (EUCLID_OUTPUT_DIR still fine)
    os.environ["EUCLID_WRITE_ROOTS"] = ""
    assert ec.get_config()["write_roots"] == []
    _raises(lambda: ec.cutout2d(str(img), ra, dec, output_path=str(RS / "y.fits")), PermissionError, 'EUCLID_WRITE_ROOTS=""', "disabled")
    ok = ec.cutout2d(str(img), ra, dec, size=32, output_path=str(SRV_OUT / "abs.fits"))
    assert ok["saved_path"] == str(SRV_OUT / "abs.fits")
    # unset -> default /home/scientist
    del os.environ["EUCLID_WRITE_ROOTS"]
    assert safety.DEFAULT_WRITE_ROOTS == "/home/scientist"
    assert ec.get_config()["write_roots"] == [os.path.realpath("/home/scientist")]
    _raises(lambda: ec.cutout2d(str(img), ra, dec, output_path=str(RS / "y.fits")), PermissionError, "/home/scientist")
    os.environ["EUCLID_WRITE_ROOTS"] = f"{SCI},/nonexistent-write-root"

    # --- cutout_single / cutout_batch output_dir (local MER mock)
    os.environ["EUCLID_MER_ROOT"] = str(MOCK_ROOT / "MER")
    os.environ["EUCLID_TILE_INDEX"] = str(MOCK_ROOT / "tile_index.fits")
    if Path(os.environ["EUCLID_TILE_INDEX"]).is_file():
        tra, tdec = ra, dec  # peak of the same mock VIS mosaic (tile 999000001)
        s1 = ec.cutout_single(tra, tdec, size=16, obj_id="s1", output_dir=str(RS / "mer") + "/")
        assert s1["success"], s1
        f0 = s1["files"][0]
        assert f0["path"].startswith(str(RS / "mer")) and f0["project_relpath"].startswith("ResearchSpace/mer/"), f0
        s2 = ec.cutout_single(tra, tdec, size=16, obj_id="s1", output_dir=str(RS / "mer"))
        assert s2["files"][0]["path"].endswith("s1_1.fits"), s2["files"][0]
        sd = ec.cutout_single(tra, tdec, size=16, obj_id="s1")  # default unchanged
        assert sd["files"][0]["path"].startswith(str(SRV_OUT)), sd
        _raises(lambda: ec.cutout_single(tra, tdec, size=16, output_dir=str(OUTSIDE)), PermissionError, "outside")
        b = ec.cutout_batch(str(MOCK_ROOT / "catalog.fits"), size=16, output_dir=str(RS / "batch") + "/", max_sources=3)
        okr = [r for r in b["results"] if r["success"]]
        assert okr and all(f["path"].startswith(str(RS / "batch")) for r in okr for f in r["files"]), b
        print("  cutout_single/batch output_dir OK", f0["project_relpath"], okr[0]["files"][0]["project_relpath"])
    else:
        print("  (no mock tile index; skip cutout_single)")
    os.environ.pop("EUCLID_MER_ROOT"); os.environ.pop("EUCLID_TILE_INDEX")

    _no_tmp(SCI); _no_tmp(SRV_OUT)
    print("library outputs OK")
    return img, ra, dec


def _post(url, body, headers=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json", **(headers or {})}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def over_mcp(img, ra, dec):
    env = dict(os.environ, SDK="euclid")
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "sdks.euclid:app", "--host", "127.0.0.1", "--port", "9197"],
                            cwd=str(REPO), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = "http://127.0.0.1:9197/euclid"
    try:
        for _ in range(80):
            try:
                urllib.request.urlopen(f"{base}/health", timeout=2); break
            except Exception:
                time.sleep(0.25)

        def mcp(name, args):
            r = _post(f"{base}/mcp", {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": args}},
                      {"accept": "application/json, text/event-stream"})
            return r["result"]
        tl = _post(f"{base}/mcp", {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, {"accept": "application/json, text/event-stream"})
        tools = {t["name"]: t for t in tl["result"]["tools"]}
        for n in ("euclid_cutout2d", "euclid_write_preview"):
            props = tools[n]["inputSchema"]["properties"]
            assert "ResearchSpace" in props["output_path"]["description"] and "overwrite" in props, props
        c = json.loads(mcp("euclid_cutout2d", {"path": str(img), "ra": ra, "dec": dec, "size": 32,
                                                "output_path": str(RS / "mcp" / "m.fits")})["content"][0]["text"])
        assert c["ok"] and c["result"]["project_relpath"] == "ResearchSpace/mcp/m.fits", c
        res = mcp("euclid_write_preview", {"fits_path": c["result"]["saved_path"], "output_path": str(RS / "mcp") + "/"})
        assert [b["type"] for b in res["content"]] == ["text", "image"], res
        out = json.loads(res["content"][0]["text"])["result"]
        assert out["project_relpath"] == "ResearchSpace/mcp/m.png" and "_mcp_images" not in res["content"][0]["text"]
        assert (RS / "mcp" / "m.png").is_file()
        bad = mcp("euclid_write_preview", {"fits_path": c["result"]["saved_path"], "output_path": str(OUTSIDE / "m.png")})
        assert bad["isError"] and "outside" in bad["content"][0]["text"]
        inv = _post(f"{base}/invoke", {"function_name": "euclid_write_preview",
                                       "arguments": {"fits_path": c["result"]["saved_path"], "output_path": str(RS / "mcp" / "m.png")}})
        assert inv["ok"] and inv["result"]["saved_path"] == str(RS / "mcp" / "m_1.png"), inv
        print("mcp outputs OK")
    finally:
        proc.terminate(); proc.wait(timeout=10)


if __name__ == "__main__":
    try:
        img, ra, dec = library()
        over_mcp(img, ra, dec)
        print("OUTPUT PATH TESTS PASSED")
    finally:
        for d in TMP.rglob("*"):
            if d.is_dir() and not d.is_symlink():
                os.chmod(d, 0o755)
        shutil.rmtree(TMP, ignore_errors=True)
