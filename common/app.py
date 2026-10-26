import hmac, json, os, resource, warnings, traceback, time
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any, Optional
from . import codec, engine, mcp_server
import contextlib
from fastapi.responses import JSONResponse

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.dirname(__file__))

class Req(BaseModel):
    function_name: str
    arguments: Optional[dict[str, Any]] = None

def make_app(sdk, prefixes, timeout=30, mem_gb=None, set_limit=True):
    if set_limit:
        mem_gb = int(os.environ.get("MEM_LIMIT_GB") or mem_gb or 4)
        resource.setrlimit(resource.RLIMIT_AS, (mem_gb << 30, mem_gb << 30))
    codec.ALLOWED_PREFIXES = tuple(prefixes) + codec.ALLOWED_PREFIXES
    tools = {t["name"]: t for t in json.load(open(os.path.join(HERE, "data", f"{sdk}_tools.json")))}
    mgr = mcp_server.build(sdk, tools, timeout)

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        async with mgr.run():
            yield

    app = FastAPI(title=f"{sdk} tool service", lifespan=lifespan)

    @app.get("/health")
    def health():
        return {"ok": True, "sdk": sdk, "tools": len(tools)}

    @app.get("/tools")
    def list_tools():
        return [{"name": t["name"], "target": t["target"], "description": t["desc"][:200], "params": t["params"]} for t in tools.values()]

    @app.post("/invoke")
    async def invoke(req: Req):  # async: runs in main thread so SIGALRM timeout works
        t = tools.get(req.function_name)
        if t is None:
            return {"ok": False, "result": None, "error": f"unknown function_name (not in whitelist): {req.function_name}"}
        t0 = time.time()
        try:
            res = engine.invoke(t["target"], req.arguments, t.get("timeout", timeout), t.get("raw_args", False))
            if isinstance(res, dict):
                res.pop("_mcp_images", None)  # MCP-only inline images; /invoke stays plain JSON
            out = codec.encode(res)
            json.dumps(out, allow_nan=False)
            return {"ok": True, "result": out, "error": None, "elapsed_s": round(time.time() - t0, 3)}
        except BaseException as e:  # noqa
            if isinstance(e, KeyboardInterrupt):
                raise
            return {"ok": False, "result": None, "error": f"{type(e).__name__}: {str(e)[:500]}", "elapsed_s": round(time.time() - t0, 3)}
    async def outer(scope, receive, send):
        # Pure ASGI wrapper: prefix strip (Ingress may forward /<sdk>/... unchanged), bearer auth, /mcp routing.
        if scope["type"] != "http":
            return await app(scope, receive, send)
        pre = f"/{sdk}"
        path = scope["path"]
        if path == pre or path.startswith(pre + "/"):
            scope = dict(scope, path=path[len(pre):] or "/")
        tok = (os.environ.get("API_TOKEN") or "").strip()  # auth only when set and non-empty
        if tok and scope["path"] != "/health":
            hdr = dict(scope.get("headers") or []).get(b"authorization", b"").decode("latin-1")
            if not hmac.compare_digest(hdr, f"Bearer {tok}"):
                return await JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)(scope, receive, send)
        if scope["path"] in ("/mcp", "/mcp/"):
            return await mgr.handle_request(dict(scope, path="/mcp"), receive, send)
        return await app(scope, receive, send)
    outer.fastapi = app
    outer.mgr = mgr
    return outer
