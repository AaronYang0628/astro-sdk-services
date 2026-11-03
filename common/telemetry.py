"""Observability for the SDK tool services: Prometheus metrics, OpenTelemetry traces, JSONL call log.

- Prometheus metrics are always recorded (cheap). They are served on a separate port by
  `start_metrics_server()` when METRICS_PORT is set (e.g. 9100) -- never through the API port / Ingress.
- OpenTelemetry tracing is enabled only when OTEL_EXPORTER_OTLP_ENDPOINT is set (OTLP/HTTP).
  Service name: OTEL_SERVICE_NAME (default astro-sdk-services); extra resource attrs: OTEL_RESOURCE_ATTRIBUTES.
- One JSON line per tool call goes to stdout (TOOL_CALL_LOG=0 disables). Argument values are never logged.
"""
from __future__ import annotations
import contextlib, contextvars, hashlib, json, os, sys, time, uuid
from typing import Any, Optional

from prometheus_client import Counter, Gauge, Histogram, start_http_server

try:  # tracing is optional at import time (tests / minimal installs)
    from opentelemetry import trace, propagate, context as otel_context
    from opentelemetry.trace import SpanKind, Status, StatusCode
except Exception:  # pragma: no cover
    trace = None

_DUR_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120)
_BYTE_BUCKETS = (256, 1024, 4096, 16384, 65536, 262144, 1048576, 4194304, 16777216)

TOOL_CALLS = Counter("astro_tool_calls", "Tool calls", ["sdk", "tool", "transport", "status", "error_type"])
TOOL_DURATION = Histogram("astro_tool_duration_seconds", "Tool call duration", ["sdk", "tool", "transport"],
                          buckets=_DUR_BUCKETS)
TOOL_REQ_BYTES = Histogram("astro_tool_request_bytes", "Tool call argument size (JSON bytes)", ["sdk", "tool"],
                           buckets=_BYTE_BUCKETS)
TOOL_RESP_BYTES = Histogram("astro_tool_response_bytes", "Tool call result size (JSON bytes)", ["sdk", "tool"],
                            buckets=_BYTE_BUCKETS)
TOOL_INFLIGHT = Gauge("astro_tool_inflight", "Tool calls in progress", ["sdk"])
TOOL_TIMEOUTS = Counter("astro_tool_timeouts", "Tool calls that hit the per-tool timeout", ["sdk", "tool"])
HTTP_REQUESTS = Counter("astro_http_requests", "HTTP requests (excluding /health)", ["sdk", "route", "code"])
# outbound fetches / OSS uploads (euclid)
FETCH_TOTAL = Counter("astro_fetch", "Outbound fetches", ["host", "status", "cache"])
FETCH_BYTES = Counter("astro_fetch_bytes", "Outbound fetched bytes", ["host"])
FETCH_DURATION = Histogram("astro_fetch_duration_seconds", "Outbound fetch duration", ["host"], buckets=_DUR_BUCKETS)
OSS_UPLOADS = Counter("astro_oss_upload", "OSS result uploads", ["status"])
OSS_UPLOAD_BYTES = Counter("astro_oss_upload_bytes", "OSS uploaded bytes")

SERVICE_NAME = os.environ.get("OTEL_SERVICE_NAME") or "astro-sdk-services"
_state = {"tracing": False, "metrics_port": None, "init": False}
# per-HTTP-request info set by the ASGI wrapper, read by the tool span / call log
_req = contextvars.ContextVar("astro_req", default=None)


def tracing_enabled() -> bool:
    return _state["tracing"]


def init() -> None:
    """Idempotent. Enables OTel only if OTEL_EXPORTER_OTLP_ENDPOINT is set; starts /metrics if METRICS_PORT is set."""
    if _state["init"]:
        return
    _state["init"] = True
    start_metrics_server()
    if trace is None or not (os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or "").strip():
        return
    try:
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        res = Resource.create({"service.name": SERVICE_NAME})
        tp = TracerProvider(resource=res)
        tp.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(tp)
        _state["tracing"] = True
        try:  # CLIENT spans for SIMBAD / VizieR / CASDC calls made through `requests`
            from opentelemetry.instrumentation.requests import RequestsInstrumentor
            RequestsInstrumentor().instrument(request_hook=_redact_request_span)
        except Exception as e:  # pragma: no cover
            print(json.dumps({"telemetry": "requests instrumentation off", "error": type(e).__name__}), flush=True)
    except Exception as e:  # never break the service because of telemetry
        print(json.dumps({"telemetry": "tracing init failed", "error": f"{type(e).__name__}: {str(e)[:200]}"}),
              flush=True)


def _redact_request_span(span, request):
    """Outbound URLs may carry signatures/tokens in the query string: keep scheme://host/path only."""
    try:
        from urllib.parse import urlsplit
        u = urlsplit(getattr(request, "url", "") or "")
        clean = f"{u.scheme}://{u.hostname or ''}{(':' + str(u.port)) if u.port else ''}{u.path}"
        for k in ("http.url", "url.full"):
            span.set_attribute(k, clean)
    except Exception:
        pass


def start_metrics_server() -> Optional[int]:
    port = (os.environ.get("METRICS_PORT") or "").strip()
    if not port or port == "0" or _state["metrics_port"]:
        return _state["metrics_port"]
    try:
        start_http_server(int(port))
        _state["metrics_port"] = int(port)
    except OSError as e:  # e.g. port already taken in a dev reload
        print(json.dumps({"telemetry": "metrics server failed", "error": str(e)[:200]}), flush=True)
    return _state["metrics_port"]


def _tracer():
    return trace.get_tracer("astro_sdk_services")


def client_fp(authorization: str) -> str:
    """sha256 prefix of the bearer token (never the token itself)."""
    tok = (authorization or "").removeprefix("Bearer ").strip()
    return hashlib.sha256(tok.encode()).hexdigest()[:8] if tok else ""


# ---------------------------------------------------------------- HTTP (ASGI) level
@contextlib.asynccontextmanager
async def http_request(sdk: str, scope: dict):
    """Wrap one HTTP request: request id, W3C traceparent extraction, SERVER span `POST /<sdk>/mcp`.
    Yields a dict with `request_id` and a `status` slot the caller may fill."""
    headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in (scope.get("headers") or [])}
    rid = headers.get("x-request-id") or uuid.uuid4().hex
    route = scope.get("path") or "/"
    info = {"request_id": rid, "sdk": sdk, "ua": headers.get("user-agent", "")[:200],
            "fp": client_fp(headers.get("authorization", "")), "status": None, "route": route}
    tok = _req.set(info)
    span_cm = contextlib.nullcontext(None)
    if _state["tracing"]:
        parent = propagate.extract(headers)
        span_cm = _tracer().start_as_current_span(
            f"{scope.get('method', 'GET')} /{sdk}{route}", context=parent, kind=SpanKind.SERVER,
            attributes={"http.request.method": scope.get("method", ""), "url.path": f"/{sdk}{route}",
                        "http.route": f"/{sdk}{route}", "user_agent.original": info["ua"],
                        "asa.client.fp": info["fp"], "astro.sdk": sdk, "astro.request_id": rid})
    try:
        with span_cm as span:
            info["span"] = span
            yield info
            if span is not None and info["status"] is not None:
                span.set_attribute("http.response.status_code", info["status"])
                if info["status"] >= 500:
                    span.set_status(Status(StatusCode.ERROR))
    finally:
        HTTP_REQUESTS.labels(sdk, _route_label(route), str(info["status"] or 0)).inc()
        _req.reset(tok)


def _route_label(route: str) -> str:
    r = route.rstrip("/") or "/"
    return r if r in ("/", "/mcp", "/invoke", "/tools", "/health") else "other"


def wrap_send(send, info):
    """ASGI send wrapper: record status code and add X-Request-ID to the response."""
    async def _send(msg):
        if msg["type"] == "http.response.start":
            info["status"] = msg.get("status")
            hdrs = list(msg.get("headers") or [])
            hdrs.append((b"x-request-id", info["request_id"].encode("latin-1")))
            msg = dict(msg, headers=hdrs)
        await send(msg)
    return _send


# ---------------------------------------------------------------- tool call level
class _Call:
    def __init__(self, sdk, tool, transport, args_bytes):
        self.sdk, self.tool, self.transport, self.args_bytes = sdk, tool, transport, args_bytes
        self.ok, self.error_type, self.error_msg = None, "", ""
        self.result_bytes, self.images = 0, 0

    def success(self, result_obj: Any = None, images: int = 0, result_bytes: Optional[int] = None):
        self.ok = True
        self.images = images
        if result_bytes is None:
            try:
                result_bytes = len(json.dumps(result_obj, ensure_ascii=False, default=str).encode())
            except Exception:
                result_bytes = 0
        self.result_bytes = result_bytes

    def failure(self, exc: BaseException):
        self.ok = False
        self.error_type = type(exc).__name__
        self.error_msg = str(exc)[:900]
        self.exc = exc


def _args_size(arguments) -> int:
    try:
        return len(json.dumps(arguments or {}, ensure_ascii=False, default=str).encode())
    except Exception:
        return 0


@contextlib.contextmanager
def tool_call(sdk: str, tool: str, transport: str, target: str, arguments: Any = None,
              parent_traceparent: Optional[str] = None):
    """Instrument one tool invocation. Usage:
        with tool_call(sdk, name, "mcp", target, args) as c:
            try: res = ...; c.success(res)
            except Exception as e: c.failure(e)
    """
    c = _Call(sdk, tool, transport, _args_size(arguments))
    info = _req.get() or {}
    TOOL_INFLIGHT.labels(sdk).inc()
    t0 = time.perf_counter()
    span_cm = contextlib.nullcontext(None)
    if _state["tracing"]:
        ctx = None
        links = None
        if parent_traceparent:  # MCP params._meta.traceparent wins over the HTTP header
            ctx = propagate.extract({"traceparent": parent_traceparent})
            http_span = info.get("span")
            if http_span is not None:
                from opentelemetry.trace import Link
                links = [Link(http_span.get_span_context())]
        span_cm = _tracer().start_as_current_span(
            f"execute_tool {tool}", context=ctx, links=links, kind=SpanKind.INTERNAL,
            attributes={"gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": tool,
                        "astro.sdk": sdk, "astro.transport": transport, "astro.target": target,
                        "astro.args.bytes": c.args_bytes})
    trace_id = ""
    try:
        with span_cm as span:
            if span is not None:
                trace_id = format(span.get_span_context().trace_id, "032x")
            yield c
            if span is not None:
                span.set_attribute("astro.result.bytes", c.result_bytes)
                span.set_attribute("astro.result.images", c.images)
                if c.ok is False:
                    span.set_attribute("error.type", c.error_type)
                    span.set_status(Status(StatusCode.ERROR, f"{c.error_type}: {c.error_msg}"[:900]))
                    if getattr(c, "exc", None) is not None:
                        span.record_exception(c.exc, attributes={"exception.message": c.error_msg})
    finally:
        dt = time.perf_counter() - t0
        TOOL_INFLIGHT.labels(sdk).dec()
        status = "ok" if c.ok else "error"
        TOOL_CALLS.labels(sdk, tool, transport, status, c.error_type).inc()
        TOOL_DURATION.labels(sdk, tool, transport).observe(dt)
        TOOL_REQ_BYTES.labels(sdk, tool).observe(c.args_bytes)
        if c.ok:
            TOOL_RESP_BYTES.labels(sdk, tool).observe(c.result_bytes)
        if c.error_type == "Timeout":
            TOOL_TIMEOUTS.labels(sdk, tool).inc()
        _log(c, dt, info, trace_id)


def _log(c: _Call, dt: float, info: dict, trace_id: str):
    if (os.environ.get("TOOL_CALL_LOG") or "1") == "0":
        return
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z", "event": "tool_call",
           "request_id": info.get("request_id", ""), "trace_id": trace_id, "sdk": c.sdk, "tool": c.tool,
           "transport": c.transport, "ok": bool(c.ok), "error_type": c.error_type,
           "elapsed_ms": round(dt * 1000, 1), "args_bytes": c.args_bytes, "result_bytes": c.result_bytes,
           "client_ua": info.get("ua", ""), "client_fp": info.get("fp", "")}
    try:
        sys.stdout.write(json.dumps(rec, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    except Exception:
        pass


# ---------------------------------------------------------------- outbound helpers (euclid)
def url_host(url: str) -> str:
    from urllib.parse import urlsplit
    try:
        return (urlsplit(url).hostname or "")[:100]
    except Exception:
        return ""


def record_fetch(url: str, status: str, cache: str, nbytes: int = 0, seconds: Optional[float] = None):
    h = url_host(url)
    FETCH_TOTAL.labels(h, status, cache).inc()
    if nbytes:
        FETCH_BYTES.labels(h).inc(nbytes)
    if seconds is not None:
        FETCH_DURATION.labels(h).observe(seconds)


def record_oss_upload(ok: bool, nbytes: int = 0):
    OSS_UPLOADS.labels("ok" if ok else "error").inc()
    if ok and nbytes:
        OSS_UPLOAD_BYTES.inc(nbytes)
