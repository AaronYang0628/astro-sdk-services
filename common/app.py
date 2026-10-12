import hmac, json, os, resource, warnings, traceback, time
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any, Optional
from . import codec, engine

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.dirname(__file__))

class Req(BaseModel):
    function_name: str
    arguments: Optional[dict[str, Any]] = None

def make_app(sdk, prefixes, timeout=30, mem_gb=4):
    resource.setrlimit(resource.RLIMIT_AS, (mem_gb << 30, mem_gb << 30))
    codec.ALLOWED_PREFIXES = tuple(prefixes) + codec.ALLOWED_PREFIXES
    tools = {t["name"]: t for t in json.load(open(os.path.join(HERE, "data", f"{sdk}_tools.json")))}
    app = FastAPI(title=f"{sdk} tool service")

    @app.middleware("http")
    async def strip_prefix(request, call_next):
        # Ingress may forward /<sdk>/... unchanged; accept both prefixed and stripped paths.
        pre = f"/{sdk}"
        path = request.scope["path"]
        if path == pre or path.startswith(pre + "/"):
            request.scope["path"] = path[len(pre):] or "/"
        tok = os.environ.get("API_TOKEN")
        if tok and request.scope["path"] != "/health":
            got = request.headers.get("authorization", "")
            if not hmac.compare_digest(got, f"Bearer {tok}"):
                from fastapi.responses import JSONResponse
                return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        return await call_next(request)

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
            res = engine.invoke(t["target"], req.arguments, t.get("timeout", timeout))
            out = codec.encode(res)
            json.dumps(out, allow_nan=False)
            return {"ok": True, "result": out, "error": None, "elapsed_s": round(time.time() - t0, 3)}
        except BaseException as e:  # noqa
            if isinstance(e, KeyboardInterrupt):
                raise
            return {"ok": False, "result": None, "error": f"{type(e).__name__}: {str(e)[:500]}", "elapsed_s": round(time.time() - t0, 3)}
    return app
