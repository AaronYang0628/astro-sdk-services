"""All-in-one: serve all SDKs in one process under /<sdk>/{health,tools,invoke,mcp}."""
import contextlib, os, resource
import sunpy.coordinates  # noqa: F401  registers helioprojective etc frames
from fastapi.responses import JSONResponse
from common.app import make_app

SDKS = ["astropy", "astroquery", "photutils", "astroplan", "sunpy", "euclid"]
_gb = int(os.environ.get("MEM_LIMIT_GB") or 8)
resource.setrlimit(resource.RLIMIT_AS, (_gb << 30, _gb << 30))
APPS = {s: make_app(s, (s,) if s != "euclid" else ("euclid_cutout",), set_limit=False) for s in SDKS}


async def _lifespan(receive, send):
    await receive()  # lifespan.startup
    async with contextlib.AsyncExitStack() as st:
        try:
            for a in APPS.values():  # start every MCP session manager
                await st.enter_async_context(a.mgr.run())
        except BaseException as e:
            await send({"type": "lifespan.startup.failed", "message": repr(e)})
            return
        await send({"type": "lifespan.startup.complete"})
        await receive()  # lifespan.shutdown
    await send({"type": "lifespan.shutdown.complete"})


async def app(scope, receive, send):
    if scope["type"] == "lifespan":
        return await _lifespan(receive, send)
    path = scope.get("path", "/")
    first = path.strip("/").split("/", 1)[0]
    if first in APPS:
        return await APPS[first](scope, receive, send)  # sub-app strips /<sdk>, applies optional auth
    if path in ("/", "/health"):
        body = {"ok": True, "mode": "all", "auth": bool((os.environ.get("API_TOKEN") or "").strip()),
                "services": {s: {"tools": f"/{s}/tools", "invoke": f"/{s}/invoke", "mcp": f"/{s}/mcp",
                                 "health": f"/{s}/health"} for s in SDKS}}
        return await JSONResponse(body)(scope, receive, send)
    return await JSONResponse({"ok": False, "error": "not found", "services": SDKS}, status_code=404)(scope, receive, send)
