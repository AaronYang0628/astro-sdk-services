"""All-in-one: serve all SDKs in one process under /<sdk>/{health,tools,invoke,mcp}.

Also serves GET /tools — aggregated catalog of every currently loaded SDK (honours ASTRO_SDKS),
sourced from the same in-memory whitelist each sub-app uses for /invoke and MCP.
"""
import contextlib, html, json, os, resource
import sunpy.coordinates  # noqa: F401  registers helioprojective etc frames
from fastapi.responses import HTMLResponse, JSONResponse, Response
from common.app import make_app

ALL_SDKS = ["astropy", "astroquery", "photutils", "astroplan", "sunpy", "euclid"]
# ASTRO_SDKS: comma-separated subset to load (default: all). Unlisted SDKs are not imported (saves memory).
_sel = [s.strip() for s in (os.environ.get("ASTRO_SDKS") or "").split(",") if s.strip()]
_bad = [s for s in _sel if s not in ALL_SDKS]
if _bad:
    raise SystemExit(f"ASTRO_SDKS: unknown SDK(s) {_bad}; choose from {ALL_SDKS}")
SDKS = [s for s in ALL_SDKS if s in _sel] if _sel else list(ALL_SDKS)
_gb = int(os.environ.get("MEM_LIMIT_GB") or 8)
resource.setrlimit(resource.RLIMIT_AS, (_gb << 30, _gb << 30))
APPS = {s: make_app(s, (s,) if s != "euclid" else ("euclid_cutout",), set_limit=False) for s in SDKS}


def _catalog():
    """Build catalog from each sub-app's in-memory whitelist (same dict /invoke uses)."""
    sdks = {}
    total = 0
    for s, a in APPS.items():
        tools = [
            {"name": t["name"], "sdk": s, "target": t["target"], "description": t["desc"],
             "params": t["params"], "invoke": f"/{s}/invoke", "mcp": f"/{s}/mcp"}
            for t in a.tools.values()
        ]
        sdks[s] = {"count": len(tools), "tools": tools}
        total += len(tools)
    return {"ok": True, "total": total, "sdks": sdks}


def _catalog_html(cat):
    parts = [
        "<!doctype html><html><head><meta charset=utf-8>",
        "<title>astro-sdk-services tool catalog</title>",
        "<style>",
        "body{font:14px/1.45 system-ui,sans-serif;margin:24px;color:#222}",
        "h1{font-size:22px} h2{font-size:18px;margin-top:28px;border-bottom:1px solid #ddd;padding-bottom:4px}",
        "code,pre{font-family:ui-monospace,Menlo,Consolas,monospace}",
        ".meta{color:#555;margin-bottom:16px}",
        "details{margin:8px 0;padding:8px 12px;background:#f7f7f8;border-radius:6px}",
        "summary{cursor:pointer;font-weight:600}",
        ".target{color:#555;font-size:12px} .params{font-size:12px;color:#333}",
        "a{color:#06c}",
        "</style></head><body>",
        f"<h1>astro-sdk-services tool catalog</h1>",
        f"<p class=meta>total <b>{cat['total']}</b> callable tools across "
        f"<b>{len(cat['sdks'])}</b> loaded SDKs "
        f"(source of truth: in-memory whitelist = data/&lt;sdk&gt;_tools.json). "
        f"JSON: <a href=/tools>GET /tools</a> · per-SDK: /&lt;sdk&gt;/tools. "
        f"/invoke and /mcp stay auth-protected when API_TOKEN is set.</p>",
    ]
    for s, block in cat["sdks"].items():
        parts.append(f"<h2 id={html.escape(s)}>{html.escape(s)} "
                     f"<small>({block['count']})</small> — "
                     f"<a href=/{html.escape(s)}/tools>/{html.escape(s)}/tools</a> · "
                     f"<a href=/{html.escape(s)}/mcp>mcp</a></h2>")
        for t in block["tools"]:
            params = t.get("params") or []
            pref = ", ".join(
                ("*" if p.get("required") else "") + p.get("name", "?")
                for p in params[:12]
            )
            if len(params) > 12:
                pref += ", …"
            parts.append(
                "<details><summary><code>"
                + html.escape(t["name"])
                + "</code></summary>"
                f"<div class=target>target: <code>{html.escape(t['target'])}</code> · "
                f"invoke <code>{html.escape(t['invoke'])}</code></div>"
                f"<p>{html.escape(t.get('description') or '')}</p>"
                f"<div class=params>params: {html.escape(pref) or '(none)'}</div>"
                "</details>"
            )
    parts.append("</body></html>")
    return "".join(parts)


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
    # Aggregated catalog (no auth). JSON by default; HTML when ?format=html or Accept: text/html.
    if path in ("/tools", "/tools/"):
        cat = _catalog()
        qs = (scope.get("query_string") or b"").decode("latin-1")
        want_html = "format=html" in qs
        if not want_html:
            accept = dict(scope.get("headers") or []).get(b"accept", b"").decode("latin-1")
            # Prefer HTML only when the client clearly asks for it (browsers send text/html first).
            want_html = "text/html" in accept and "application/json" not in accept.split(",")[0]
        if want_html:
            return await HTMLResponse(_catalog_html(cat))(scope, receive, send)
        return await JSONResponse(cat)(scope, receive, send)
    first = path.strip("/").split("/", 1)[0]
    if first in APPS:
        return await APPS[first](scope, receive, send)  # sub-app strips /<sdk>, applies optional auth
    if path in ("/", "/health"):
        cat_counts = {s: len(a.tools) for s, a in APPS.items()}
        body = {"ok": True, "mode": "all", "auth": bool((os.environ.get("API_TOKEN") or "").strip()),
                "tools_catalog": "/tools",
                "total_tools": sum(cat_counts.values()),
                "services": {s: {"tools": f"/{s}/tools", "count": cat_counts[s],
                                 "invoke": f"/{s}/invoke", "mcp": f"/{s}/mcp",
                                 "health": f"/{s}/health"} for s in SDKS}}
        return await JSONResponse(body)(scope, receive, send)
    return await JSONResponse({"ok": False, "error": "not found", "services": SDKS}, status_code=404)(scope, receive, send)
