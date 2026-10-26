"""MCP (Streamable HTTP) front-end for an SDK tool service.

Each whitelisted tool is exposed as an MCP tool with the same name; calls reuse
common.engine / common.codec (same timeout and encoding as POST /invoke).
"""
import base64, inspect, json, os, time
import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from . import codec, engine

_JSON = {"str": "string", "int": "integer", "float": "number", "bool": "boolean",
         "dict": "object", "list": "array", "tuple": "array", "array": "array",
         "numpy.ndarray": "array"}


def _is_method(target):
    try:
        fn, owner = engine.resolve_target(target)
    except Exception:
        return False
    if owner is None or not inspect.isclass(owner):
        return False
    st = inspect.getattr_static(owner, target.split(".")[-1], None)
    return fn is None or (not isinstance(st, (classmethod, staticmethod)) and callable(fn) and not inspect.isclass(fn))


def input_schema(t):
    props, req = {}, []
    for p in t["params"]:
        if p["name"] in ("args", "kwargs"):
            continue
        s = {"description": f"[{p['type']}] {p.get('desc') or ''}".strip()}
        jt = _JSON.get(p["type"])
        if jt:
            s["type"] = jt
            if jt == "array":
                s["items"] = {}
        # complex astro types (SkyCoord, Time, Quantity, WCS...) accept the codec's JSON forms: no type restriction
        props[p["name"]] = s
        if p.get("required"):
            req.append(p["name"])
    if any(p["name"] == "args" for p in t["params"]):
        props["_args"] = {"type": "array", "items": {}, "description": "额外位置参数（按顺序）"}
    if _is_method(t["target"]):
        props["_self"] = {"description": "实例构造参数（方法调用必填），格式同 /invoke 的 _self"}
        req.append("_self")
    return {"type": "object", "properties": props, "required": req, "additionalProperties": True}


MAX_INLINE_BYTES = int(os.environ.get("MCP_MAX_INLINE_IMAGE_BYTES") or 2_000_000)


def image_blocks(images):
    """Tool results may carry `_mcp_images`: [{"path": str, "mimeType": str} | {"data": b64, "mimeType": str}].
    Each becomes an MCP image content block; oversized/missing files are skipped."""
    blocks = []
    for im in images or []:
        try:
            mime = im.get("mimeType") or "image/png"
            data = im.get("data")
            if data is None:
                with open(im["path"], "rb") as f:
                    raw = f.read(MAX_INLINE_BYTES + 1)
                if len(raw) > MAX_INLINE_BYTES:
                    continue
                data = base64.b64encode(raw).decode("ascii")
            blocks.append(types.ImageContent(type="image", data=data, mimeType=mime))
        except Exception:
            continue
    return blocks


def build(sdk, tools, timeout):
    server = Server(f"astro-{sdk}")
    tool_list = [types.Tool(name=t["name"], description=t["desc"], inputSchema=input_schema(t)) for t in tools.values()]

    @server.list_tools()
    async def _list():
        return tool_list

    @server.call_tool(validate_input=False)
    async def _call(name, arguments):
        t = tools.get(name)
        images = None
        if t is None:
            out = {"ok": False, "result": None, "error": f"unknown tool: {name}"}
        else:
            t0 = time.time()
            try:  # runs on the event-loop (main) thread so the SIGALRM timeout works, like /invoke
                raw = engine.invoke(t["target"], arguments, t.get("timeout", timeout))
                if isinstance(raw, dict) and "_mcp_images" in raw:
                    images = raw.pop("_mcp_images")
                res = codec.encode(raw)
                json.dumps(res, allow_nan=False)
                out = {"ok": True, "result": res, "error": None, "elapsed_s": round(time.time() - t0, 3)}
            except BaseException as e:  # noqa
                if isinstance(e, KeyboardInterrupt):
                    raise
                out = {"ok": False, "result": None, "error": f"{type(e).__name__}: {str(e)[:500]}", "elapsed_s": round(time.time() - t0, 3)}
        content = [types.TextContent(type="text", text=json.dumps(out, ensure_ascii=False))]
        if out["ok"] and images:
            content += image_blocks(images)
        return types.CallToolResult(content=content, isError=not out["ok"])

    return StreamableHTTPSessionManager(app=server, json_response=True, stateless=True)
