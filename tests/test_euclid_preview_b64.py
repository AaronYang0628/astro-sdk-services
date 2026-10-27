"""euclid_write_preview returns the thumbnail bytes as base64 in the JSON (for clients that drop MCP image blocks
and for deployments that do NOT mount project storage), plus the improved 'output_path not writable' errors.
Run: python tests/test_euclid_preview_b64.py"""
from __future__ import annotations
import base64, io, json, os, shutil, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))
MOCK = REPO / "fixtures/euclid_mock/MER/999000001/VIS/EUC_MER_BGSUB-MOSAIC-VIS_TILE999000001_mock.fits"

TMP = Path(tempfile.mkdtemp(prefix="euclid_b64_")).resolve()
SCI = TMP / "home" / "scientist"
RS = SCI / "project42" / "ResearchSpace"
DATA = SCI / "project42" / "Data"
for d in (RS, DATA):
    d.mkdir(parents=True)
os.environ["EUCLID_CACHE_DIR"] = str(TMP / "cache")
os.environ["EUCLID_OUTPUT_DIR"] = str(TMP / "out")
os.environ["EUCLID_INPUT_ROOTS"] = str(SCI)
os.environ["EUCLID_WRITE_ROOTS"] = f"{SCI},/nonexistent-write-root"
for k in ("EUCLID_MER_ROOT", "EUCLID_TILE_INDEX", "EUCLID_PREVIEW_BASE64", "EUCLID_PREVIEW_BASE64_MAX_BYTES",
          "EUCLID_PREVIEW_BASE64_TARGET_BYTES"):
    os.environ.pop(k, None)

import euclid_cutout as ec  # noqa: E402
from euclid_cutout import safety  # noqa: E402
from PIL import Image  # noqa: E402


def _raises(fn, exc, *needles):
    try:
        fn()
    except exc as e:
        for n in needles:
            assert n.lower() in str(e).lower(), (n, str(e))
        return str(e)
    raise AssertionError(f"did not raise {exc.__name__}")


def _png_ok(b: bytes):
    assert b[:8] == b"\x89PNG\r\n\x1a\n", b[:8]
    im = Image.open(io.BytesIO(b)); im.load()
    return im


def library():
    img = DATA / "VIS.fits"
    shutil.copy(MOCK, img)
    pk = ec.find_peak_sky(str(img))
    c = ec.cutout2d(str(img), pk["ra"], pk["dec"], size=64)

    # 1) default on; small file is embedded as-is and equals the written PNG
    os.environ["EUCLID_PREVIEW_BASE64_TARGET_BYTES"] = "10000000"
    p = ec.write_preview(c["fits_path"])
    assert p["inline_image"] is True and p["_mcp_images"], p
    raw = base64.b64decode(p["image_base64"])
    assert raw == Path(p["preview_path"]).read_bytes() and len(raw) == p["size_bytes"] == p["image_base64_size_bytes"], p
    assert p["image_base64_mime"] == p["mime_type"] == "image/png" and "image_base64_note" not in p
    _png_ok(raw)
    assert p["image_base64"] not in json.dumps({k: v for k, v in p.items() if k != "image_base64"})  # not duplicated
    assert "image_base64_omitted" not in p
    # JPG
    j = ec.write_preview(c["fits_path"], format="jpg")
    jr = base64.b64decode(j["image_base64"])
    assert jr[:3] == b"\xff\xd8\xff" and jr == Path(j["preview_path"]).read_bytes() and j["image_base64_mime"] == "image/jpeg"
    # with output_path (write succeeded) base64 is the same bytes as saved_path
    o = ec.write_preview(c["fits_path"], output_path=str(RS / "a.png"))
    assert base64.b64decode(o["image_base64"]) == (RS / "a.png").read_bytes() and o["project_relpath"] == "ResearchSpace/a.png"

    # 2) return_base64=False / env off -> no field; inline image block unchanged
    n = ec.write_preview(c["fits_path"], return_base64=False)
    assert "image_base64" not in n and "image_base64_omitted" not in n and n["_mcp_images"], n
    os.environ["EUCLID_PREVIEW_BASE64"] = "0"
    assert "image_base64" not in ec.write_preview(c["fits_path"])
    assert "image_base64" in ec.write_preview(c["fits_path"], return_base64=True)  # explicit param wins over env
    os.environ.pop("EUCLID_PREVIEW_BASE64")
    # inline_image=False keeps base64 (that is the point)
    q = ec.write_preview(c["fits_path"], inline_image=False)
    assert "_mcp_images" not in q and "image_base64" in q

    # 3) file bigger than the target -> downscaled JPEG thumbnail <= target, note says so; file on disk unchanged
    full = Path(p["preview_path"]).stat().st_size
    tgt = max(1500, full // 3)
    os.environ["EUCLID_PREVIEW_BASE64_TARGET_BYTES"] = str(tgt)
    t = ec.write_preview(c["fits_path"], return_base64=True)
    tb = base64.b64decode(t["image_base64"])
    assert t["image_base64_mime"] == "image/jpeg" and tb[:3] == b"\xff\xd8\xff" and len(tb) == t["image_base64_size_bytes"], t
    assert len(tb) <= tgt or "64" in t["image_base64_note"], (len(tb), tgt)
    assert "downscaled" in t["image_base64_note"] and t["size_bytes"] == full == Path(t["preview_path"]).stat().st_size
    assert t["mime_type"] == "image/png"  # describes the file, image_base64_mime describes the payload

    # 4) hard cap EUCLID_PREVIEW_BASE64_MAX_BYTES: over cap -> field omitted + reason
    os.environ["EUCLID_PREVIEW_BASE64_TARGET_BYTES"] = "10000000"
    os.environ["EUCLID_PREVIEW_BASE64_MAX_BYTES"] = "100"
    m = ec.write_preview(c["fits_path"])
    assert "image_base64" not in m and m["image_base64_omitted"].startswith("too large (") and "> cap 100" in m["image_base64_omitted"] \
        and "lower max_side" in m["image_base64_omitted"], m
    os.environ.pop("EUCLID_PREVIEW_BASE64_MAX_BYTES")
    os.environ.pop("EUCLID_PREVIEW_BASE64_TARGET_BYTES")
    # defaults: target 30000, cap 300000
    d = ec.write_preview(c["fits_path"])
    assert len(base64.b64decode(d["image_base64"])) <= 30000 or "image_base64_omitted" in d, d
    print("library b64 OK; default payload", d["image_base64_size_bytes"], "bytes", d["image_base64_mime"], "file", d["size_bytes"])
    return c


def errors(c):
    # not mounted: write root absent in the container
    e = _raises(lambda: ec.write_preview(c["fits_path"], output_path="/nonexistent-write-root/project1/ResearchSpace/x.png"),
                PermissionError, "output_path not writable on MCP server", "not mounted", "/nonexistent-write-root",
                "omit output_path", "image_base64")
    print("  not-mounted:", e)
    # read-only (EROFS from writer)
    import errno
    def _erofs(t):
        raise OSError(errno.EROFS, "Read-only file system", str(t))
    e = _raises(lambda: safety.atomic_write(RS / "erofs.png", _erofs), PermissionError, "read-only filesystem", "image_base64")
    print("  read-only:", e)
    # no permission for uid (chmod; skip as root)
    ro = SCI / "project_ro"
    (ro / "ResearchSpace").mkdir(parents=True)
    os.chmod(ro / "ResearchSpace", 0o555); os.chmod(ro, 0o555)
    try:
        if os.access(ro / "ResearchSpace", os.W_OK):
            print("  (skip permission check: running as root)")
        else:
            e = _raises(lambda: ec.write_preview(c["fits_path"], output_path=str(ro / "ResearchSpace" / "x.png")),
                        PermissionError, "no write permission", f"uid={os.getuid()}", f"gid={os.getgid()}",
                        "omit output_path", "image_base64")
            print("  no-permission:", e)
            assert len(e) < 800, len(e)
    finally:
        os.chmod(ro, 0o755); os.chmod(ro / "ResearchSpace", 0o755)
    print("error messages OK")


def _post(url, body, headers=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json", **(headers or {})}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def over_mcp(c):
    env = dict(os.environ, SDK="euclid", EUCLID_PREVIEW_BASE64_TARGET_BYTES="10000000")
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "sdks.euclid:app", "--host", "127.0.0.1", "--port", "9198"],
                            cwd=str(REPO), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = "http://127.0.0.1:9198/euclid"
    try:
        for _ in range(80):
            try:
                urllib.request.urlopen(f"{base}/health", timeout=2); break
            except Exception:
                time.sleep(0.25)
        H = {"accept": "application/json, text/event-stream"}
        tl = _post(f"{base}/mcp", {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, H)
        tool = {t["name"]: t for t in tl["result"]["tools"]}["euclid_write_preview"]
        assert "image_base64" in tool["description"] and "base64 -d" in tool["description"], tool["description"]
        assert "return_base64" in tool["inputSchema"]["properties"]
        res = _post(f"{base}/mcp", {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                   "params": {"name": "euclid_write_preview", "arguments": {"fits_path": c["fits_path"]}}}, H)["result"]
        assert [b["type"] for b in res["content"]] == ["text", "image"], res  # inline block unchanged
        text = res["content"][0]["text"]
        out = json.loads(text)["result"]
        assert text.count(out["image_base64"]) == 1  # not duplicated
        assert base64.b64decode(out["image_base64"]) == base64.b64decode(res["content"][1]["data"]) == Path(out["preview_path"]).read_bytes()
        _png_ok(base64.b64decode(out["image_base64"]))
        assert "_mcp_images" not in text
        inv = _post(f"{base}/invoke", {"function_name": "euclid_write_preview", "arguments": {"fits_path": c["fits_path"]}})
        assert inv["ok"] and base64.b64decode(inv["result"]["image_base64"]) == Path(inv["result"]["preview_path"]).read_bytes(), inv
        off = _post(f"{base}/invoke", {"function_name": "euclid_write_preview",
                                       "arguments": {"fits_path": c["fits_path"], "return_base64": False}})
        assert off["ok"] and "image_base64" not in off["result"]
        bad = _post(f"{base}/mcp", {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                                   "params": {"name": "euclid_write_preview", "arguments": {
                                       "fits_path": c["fits_path"], "output_path": "/nonexistent-write-root/project1/x.png"}}}, H)["result"]
        t = bad["content"][0]["text"]
        assert bad["isError"] and "image_base64" in t and "not mounted" in t, t  # hint survives the error-length cap
        print("mcp + /invoke b64 OK")
    finally:
        proc.terminate(); proc.wait(timeout=10)


if __name__ == "__main__":
    try:
        c = library()
        errors(c)
        over_mcp(c)
        print("PREVIEW BASE64 TESTS PASSED")
    finally:
        for d in TMP.rglob("*"):
            if d.is_dir() and not d.is_symlink():
                os.chmod(d, 0o755)
        shutil.rmtree(TMP, ignore_errors=True)
