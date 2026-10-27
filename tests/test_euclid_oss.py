"""OSS result delivery (presigned download_url) for euclid_cutout2d / euclid_write_preview.
The uploader is mocked: no network. All hostnames/keys below are placeholders.
Run: python tests/test_euclid_oss.py"""
from __future__ import annotations
import datetime as dt, json, os, re, shutil, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))
MOCK = REPO / "fixtures/euclid_mock/MER/999000001/VIS/EUC_MER_BGSUB-MOSAIC-VIS_TILE999000001_mock.fits"

TMP = Path(tempfile.mkdtemp(prefix="euclid_oss_")).resolve()
SCI = TMP / "home" / "scientist"
DATA = SCI / "project42" / "Data"
DATA.mkdir(parents=True)
os.environ["EUCLID_CACHE_DIR"] = str(TMP / "cache")
os.environ["EUCLID_OUTPUT_DIR"] = str(TMP / "out")
os.environ["EUCLID_INPUT_ROOTS"] = str(SCI)
os.environ["EUCLID_WRITE_ROOTS"] = str(SCI)
OSS_VARS = ("EUCLID_OSS_ENDPOINT", "EUCLID_OSS_BUCKET", "EUCLID_OSS_ACCESS_KEY_ID", "EUCLID_OSS_ACCESS_KEY_SECRET",
            "EUCLID_OSS_PREFIX", "EUCLID_OSS_URL_EXPIRES", "EUCLID_OSS_VERIFY_TLS", "EUCLID_OSS_CA_BUNDLE")
for k in ("EUCLID_MER_ROOT", "EUCLID_TILE_INDEX", "EUCLID_PREVIEW_BASE64", "EUCLID_PREVIEW_BASE64_MAX_BYTES",
          "EUCLID_PREVIEW_BASE64_TARGET_BYTES") + OSS_VARS:
    os.environ.pop(k, None)

import euclid_cutout as ec  # noqa: E402
from euclid_cutout import oss  # noqa: E402

PH = {"EUCLID_OSS_ENDPOINT": "oss.example.invalid", "EUCLID_OSS_BUCKET": "my-bucket",
      "EUCLID_OSS_ACCESS_KEY_ID": "AKID_PLACEHOLDER", "EUCLID_OSS_ACCESS_KEY_SECRET": "SECRET_PLACEHOLDER"}
CALLS: list = []
FAIL: list = []  # non-empty -> uploader raises that exception


def fake_put_and_sign(cfg, key, local_path, content_type, expires):
    CALLS.append({"cfg": dict(cfg), "key": key, "path": local_path, "ctype": content_type, "expires": expires,
                  "bytes": Path(local_path).read_bytes()})
    if FAIL:
        raise FAIL[0]
    return f"{cfg['endpoint']}/{cfg['bucket']}/{key}?Expires=1&OSSAccessKeyId={cfg['key_id']}&Signature=abc%3D"


oss._put_and_sign = fake_put_and_sign


def setenv(**kw):
    for k in OSS_VARS:
        os.environ.pop(k, None)
    os.environ.update(kw)


def prepare():
    img = DATA / "VIS.fits"
    shutil.copy(MOCK, img)
    pk = ec.find_peak_sky(str(img))
    return str(img), pk


def unconfigured(img, pk):
    for env in ({}, {k: v for k, v in PH.items() if k != "EUCLID_OSS_ACCESS_KEY_SECRET"},
                {k: v for k, v in PH.items() if k != "EUCLID_OSS_BUCKET"}):
        setenv(**env)
        assert oss.oss_config() is None
        CALLS.clear()
        c = ec.cutout2d(img, pk["ra"], pk["dec"], size=32)
        p = ec.write_preview(c["fits_path"])
        assert not CALLS
        for r in (c, p):
            assert not any(k.startswith("download_") or k in ("oss_key", "upload_error") for k in r), r
        assert "image_base64" in p and c["fits_path"] and p["preview_path"]  # auto == on without OSS
    print("unconfigured OK (nothing uploaded, no new fields, base64 kept)")


def configured(img, pk):
    setenv(**PH)
    cfg = oss.oss_config()
    assert cfg["prefix"] == "euclid-mcp/" and cfg["expires"] == 7 * 86400 and cfg["verify"] is False
    assert cfg["endpoint"] == "https://oss.example.invalid"
    CALLS.clear()
    c = ec.cutout2d(img, pk["ra"], pk["dec"], size=32, obj_id="stamp A")
    assert len(CALLS) == 1 and CALLS[0]["bytes"] == Path(c["fits_path"]).read_bytes()
    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).strftime("%Y%m%d")
    assert re.fullmatch(rf"euclid-mcp/{today}/[0-9a-f]{{8}}/stamp_A\.fits", c["oss_key"]), c["oss_key"]
    assert c["download_url"].startswith("https://oss.example.invalid/my-bucket/" + c["oss_key"])
    assert c["size_bytes"] == Path(c["fits_path"]).stat().st_size
    exp = dt.datetime.fromisoformat(c["download_expires_at"])
    assert exp.utcoffset() == dt.timedelta(hours=8)
    assert abs((exp - dt.datetime.now(dt.timezone.utc)).total_seconds() - 7 * 86400) < 30
    assert CALLS[0]["expires"] == 7 * 86400 and CALLS[0]["ctype"] == "application/fits"
    h = c["download_hint"]
    assert h.startswith("mkdir -p") and "curl -k -sS -o \"$PROJECT_DIR/ResearchSpace/euclid/stamp_A.fits\" '" + c["download_url"] + "'" in h
    assert "HEAD" in c["download_note"] and "upload_error" not in c
    assert c["saved_path"] == c["fits_path"]  # local fields kept

    CALLS.clear()
    p = ec.write_preview(c["fits_path"])
    assert len(CALLS) == 1 and CALLS[0]["bytes"] == Path(p["preview_path"]).read_bytes()  # full-resolution file
    assert CALLS[0]["ctype"] == "image/png" and p["oss_key"].endswith(".png")
    assert p["download_url"] and p["size_bytes"] == Path(p["preview_path"]).stat().st_size
    assert "image_base64" not in p and "image_base64_omitted" not in p, "auto: base64 dropped after successful upload"
    assert p["_mcp_images"]  # inline image block unchanged
    # explicit overrides
    assert "image_base64" in ec.write_preview(c["fits_path"], return_base64=True)
    os.environ["EUCLID_PREVIEW_BASE64"] = "on"
    assert "image_base64" in ec.write_preview(c["fits_path"])
    os.environ["EUCLID_PREVIEW_BASE64"] = "off"
    assert "image_base64" not in ec.write_preview(c["fits_path"])
    os.environ["EUCLID_PREVIEW_BASE64"] = "auto"
    assert "image_base64" not in ec.write_preview(c["fits_path"])
    # jpg
    CALLS.clear()
    j = ec.write_preview(c["fits_path"], format="jpg")
    assert CALLS[0]["ctype"] == "image/jpeg" and j["oss_key"].endswith(".jpg")

    # env knobs
    setenv(**PH, EUCLID_OSS_PREFIX="/team/x", EUCLID_OSS_URL_EXPIRES="3600", EUCLID_OSS_VERIFY_TLS="true")
    CALLS.clear()
    c2 = ec.cutout2d(img, pk["ra"], pk["dec"], size=16)
    assert c2["oss_key"].startswith("team/x/") and CALLS[0]["expires"] == 3600 and CALLS[0]["cfg"]["verify"] is True
    assert "curl -sS -o" in c2["download_hint"] and "curl -k" not in c2["download_hint"]
    setenv(**PH, EUCLID_OSS_CA_BUNDLE="/etc/ssl/ca.pem", EUCLID_OSS_URL_EXPIRES="bogus")
    cfg = oss.oss_config()
    assert cfg["verify"] == "/etc/ssl/ca.pem" and cfg["expires"] == 7 * 86400
    os.environ.pop("EUCLID_PREVIEW_BASE64", None)
    print("configured OK:", c["oss_key"])


def failure(img, pk):
    setenv(**PH)
    FAIL[:] = [RuntimeError("PUT failed https://x/y?Signature=TOPSECRETSIG&a=1 SECRET_PLACEHOLDER " + "z" * 2000)]
    try:
        c = ec.cutout2d(img, pk["ra"], pk["dec"], size=32)
        assert c["ok"] and c["fits_path"] and Path(c["fits_path"]).is_file() and c["saved_path"]
        assert "download_url" not in c and "oss_key" not in c
        e = c["upload_error"]
        assert e.startswith("RuntimeError") and len(e) <= 400 and "SECRET_PLACEHOLDER" not in e and "TOPSECRETSIG" not in e, e
        p = ec.write_preview(c["fits_path"])
        assert p["ok"] and Path(p["preview_path"]).is_file() and "upload_error" in p and "download_url" not in p
        assert "image_base64" in p, "auto: base64 kept when the upload failed"
        os.environ["EUCLID_PREVIEW_BASE64"] = "off"
        assert "image_base64" not in ec.write_preview(c["fits_path"])
        os.environ.pop("EUCLID_PREVIEW_BASE64")
    finally:
        FAIL.clear()
    # real _put_and_sign path with a fake oss2 (missing file / SDK error never raises out of upload_result)
    r = oss.upload_result(str(TMP / "does-not-exist.fits"))
    assert "upload_error" in r and "download_url" not in r
    print("upload failure OK:", e[:80])


def sdk_wiring():
    """_put_and_sign: v1 Auth, verify flag, virtual-host bucket, slash_safe presign (oss2 mocked)."""
    import oss2
    seen = {}

    class B:
        def __init__(self, auth, endpoint, name, session=None, **kw):
            seen.update(auth=auth, endpoint=endpoint, name=name, verify=session.session.verify)
        def put_object(self, key, f, headers=None):
            seen.update(put=(key, f.read(), headers))
        def sign_url(self, method, key, expires, slash_safe=False, **kw):
            seen.update(sign=(method, key, expires, slash_safe))
            return "https://signed.example.invalid/" + key
    real = oss2.Bucket
    oss2.Bucket = B
    try:
        f = TMP / "t.bin"
        f.write_bytes(b"abc")
        setenv(**PH)
        cfg = oss.oss_config()
        import importlib
        orig = importlib.reload(oss)  # restore the real _put_and_sign
        url = orig._put_and_sign(cfg, "k/a.bin", str(f), "application/x", 99)
    finally:
        oss2.Bucket = real
        oss._put_and_sign = fake_put_and_sign
    assert url == "https://signed.example.invalid/k/a.bin"
    assert isinstance(seen["auth"], oss2.Auth) and not isinstance(seen["auth"], oss2.AuthV4)
    assert seen["verify"] is False and seen["name"] == "my-bucket" and seen["endpoint"] == "https://oss.example.invalid"
    assert seen["put"] == ("k/a.bin", b"abc", {"Content-Type": "application/x"}) and seen["sign"] == ("GET", "k/a.bin", 99, True)
    print("sdk wiring OK")


def _post(url, body, headers=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json", **(headers or {})}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def descriptions():
    d = json.loads((REPO / "data/euclid_tools.json").read_text())
    first = {"euclid_cutout2d": "切图后返回 download_url", "euclid_write_preview": "预览后返回 download_url",
             "euclid_fetch_fits": "输入 http(s) FITS 链接"}
    for t in d:
        if t["name"] in first:
            assert t["desc"].startswith(first[t["name"]]), t["name"]
        if t["name"] in ("euclid_cutout2d", "euclid_write_preview"):
            assert "curl -k -sS -o" in t["desc"] and "不要传 output_path" in t["desc"] and "HEAD" in t["desc"], t["name"]
        assert "Returns download_url" not in t["desc"], t["name"]  # no English duplicate sentence
    # and as served over MCP tools/list
    env = dict(os.environ, SDK="euclid")
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "sdks.euclid:app", "--host", "127.0.0.1", "--port", "9199"],
                            cwd=str(REPO), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = "http://127.0.0.1:9199/euclid"
    try:
        for _ in range(80):
            try:
                urllib.request.urlopen(f"{base}/health", timeout=2); break
            except Exception:
                time.sleep(0.25)
        tl = _post(f"{base}/mcp", {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, {"accept": "application/json, text/event-stream"})
        tools = {t["name"]: t for t in tl["result"]["tools"]}
        for n, lead in first.items():
            assert tools[n]["description"].startswith(lead), tools[n]["description"][:200]
    finally:
        proc.terminate(); proc.wait(timeout=10)
    print("tool descriptions OK")


def config_flag():
    import euclid_cutout as ec
    keys = ("EUCLID_OSS_ENDPOINT", "EUCLID_OSS_BUCKET", "EUCLID_OSS_ACCESS_KEY_ID", "EUCLID_OSS_ACCESS_KEY_SECRET")
    saved = {k: os.environ.pop(k, None) for k in keys}
    try:
        assert ec.get_config()["oss_configured"] is False
        for k in keys:
            os.environ[k] = "x-" + k.lower()
        cfg = ec.get_config()
        assert cfg["oss_configured"] is True
        assert not any(("x-" + k.lower()) in json.dumps(cfg) for k in keys), "get_config must not expose OSS values"
    finally:
        for k in keys:
            os.environ.pop(k, None)
            if saved[k] is not None:
                os.environ[k] = saved[k]
    print("get_config oss_configured OK")


if __name__ == "__main__":
    try:
        img, pk = prepare()
        unconfigured(img, pk)
        configured(img, pk)
        failure(img, pk)
        sdk_wiring()
        config_flag()
        descriptions()
        print("OSS TESTS PASSED")
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
