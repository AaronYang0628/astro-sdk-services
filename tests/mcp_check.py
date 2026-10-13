"""MCP smoke test: initialize + list_tools + call N tools per SDK.
Usage: BASE=http://127.0.0.1 API_TOKEN=... [VERIFY_TLS=0] [NCALL=2] python tests/mcp_check.py
BASE may be e.g. https://astro.example.com (then URL = BASE/<sdk>/mcp) or local ports via PORTS=1."""
import asyncio, json, os, sys, httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SDKS = ["astropy", "astroquery", "photutils", "astroplan", "sunpy"]
BASE = os.environ.get("BASE", "http://127.0.0.1"); TOK = os.environ.get("API_TOKEN", "")
VERIFY = os.environ.get("VERIFY_TLS", "1") != "0"; NCALL = int(os.environ.get("NCALL", "2"))

def url(i, sdk):
    return f"{BASE}:{9101+i}/{sdk}/mcp" if os.environ.get("PORTS") else f"{BASE}/{sdk}/mcp"

def factory(headers=None, timeout=None, auth=None):
    return httpx.AsyncClient(headers=headers, timeout=timeout or httpx.Timeout(120), auth=auth, verify=VERIFY, follow_redirects=True)

async def check(i, sdk):
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
