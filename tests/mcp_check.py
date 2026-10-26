"""MCP smoke test: initialize + list_tools + call N tools per SDK, plus the euclid chain
(fetch -> peak -> cutout2d -> write_preview) asserting an inline MCP image block (decodable PNG).
Usage: BASE=http://127.0.0.1 API_TOKEN=... [VERIFY_TLS=0] [NCALL=2] [EUCLID_URL=<https FITS>] [SDKS=euclid] python tests/mcp_check.py
Without EUCLID_URL the in-image mock FITS is used directly (no fetch); set it to e.g. the CASDC VIS URL for a real-data check (hdu_index=1).
BASE may be e.g. https://astro.example.com (then URL = BASE/<sdk>/mcp) or local ports via PORTS=1."""
import asyncio, base64, json, os, sys, httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SDKS = [x for x in os.environ.get("SDKS", "astropy,astroquery,photutils,astroplan,sunpy,euclid").split(",") if x]
MOCK = "fixtures/euclid_mock/MER/999000001/VIS/EUC_MER_BGSUB-MOSAIC-VIS_TILE999000001_mock.fits"
BASE = os.environ.get("BASE", "http://127.0.0.1"); TOK = os.environ.get("API_TOKEN", "")
VERIFY = os.environ.get("VERIFY_TLS", "1") != "0"; NCALL = int(os.environ.get("NCALL", "2"))

def url(i, sdk):
    return f"{BASE}:{9101+i}/{sdk}/mcp" if os.environ.get("PORTS") else f"{BASE}/{sdk}/mcp"

def factory(headers=None, timeout=None, auth=None):
    return httpx.AsyncClient(headers=headers, timeout=timeout or httpx.Timeout(600), auth=auth, verify=VERIFY, follow_redirects=True)

def _json(res):
    assert not res.isError, res.content[0].text[:300]
    return json.loads(res.content[0].text)["result"]

async def check_euclid(s):
    src = os.environ.get("EUCLID_URL") or MOCK
    hdu = {"hdu_index": 1} if os.environ.get("EUCLID_URL") else {}
    f = _json(await s.call_tool("euclid_fetch_fits", {"url": src, "max_bytes": 25_000_000})) if src.startswith("http") else {"path": src}
    bad = await s.call_tool("euclid_list_hdus", {"path": "/etc/passwd"})
    assert bad.isError or '"ok": false' in bad.content[0].text, "sandbox must reject /etc/passwd"
    pk = _json(await s.call_tool("euclid_find_peak_sky", {"path": f["path"], **hdu}))
    c = _json(await s.call_tool("euclid_cutout2d", {"path": f["path"], "ra": pk["ra"], "dec": pk["dec"], "size": 1024, "obj_id": "mcp_check", **hdu}))
    res = await s.call_tool("euclid_write_preview", {"fits_path": c["fits_path"]})
    imgs = [b for b in res.content if b.type == "image"]
    assert len(imgs) == 1 and imgs[0].mimeType == "image/png", [b.type for b in res.content]
    png = base64.b64decode(imgs[0].data)
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and "_mcp_images" not in res.content[0].text
    off = await s.call_tool("euclid_write_preview", {"fits_path": c["fits_path"], "inline_image": False})
    assert [b.type for b in off.content] == ["text"]
    if os.environ.get("SAVE_IMAGE"):
        open(os.environ["SAVE_IMAGE"], "wb").write(png)
    return ["fetch_fits", "find_peak_sky", "cutout2d", f"write_preview(image {len(png)} B)"]

async def check(i, sdk):
    if sdk == "euclid":
        async with streamablehttp_client(url(i, sdk), headers=({"Authorization": f"Bearer {TOK}"} if TOK else {}), timeout=600,
                                         httpx_client_factory=factory) as (r, w, _):
            async with ClientSession(r, w) as s:
                init = await s.initialize()
                tools = (await s.list_tools()).tools
                ok = await check_euclid(s)
                print(f"{sdk}: server={init.serverInfo.name} tools={len(tools)} calls_ok={ok}")
                return len(tools) == 14
    cases = [c for c in json.load(open(f"{HERE}/cases/{sdk}.json")) if not c.get("skip")]
    async with streamablehttp_client(url(i, sdk), headers=({"Authorization": f"Bearer {TOK}"} if TOK else {}), timeout=120,
                                     httpx_client_factory=factory) as (r, w, _):
        async with ClientSession(r, w) as s:
            init = await s.initialize()
            tools = (await s.list_tools()).tools
            ok = []
            for c in cases:
                if len(ok) >= NCALL: break
                res = await s.call_tool(c["name"], c["arguments"])
                if not res.isError: ok.append(c["name"])
                else: print("  fail", c["name"], res.content[0].text[:200])
            print(f"{sdk}: server={init.serverInfo.name} tools={len(tools)} calls_ok={ok}")
            return len(tools) == 20 and len(ok) >= NCALL

async def main():
    res = []
    for i, sdk in enumerate(SDKS):
        try: res.append(await check(i, sdk))
        except Exception as e: print(sdk, "ERROR", repr(e)[:300]); res.append(False)
    print("ALL OK" if all(res) else "FAILURES"); sys.exit(0 if all(res) else 1)
asyncio.run(main())
