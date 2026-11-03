"""Telemetry: spans (attributes, traceparent parenting), Prometheus counters/histograms, log redaction."""
import asyncio, io, json, contextlib, os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from prometheus_client import REGISTRY

from common import telemetry
from common.app import make_app

EXP = InMemorySpanExporter()
_tp = TracerProvider()
_tp.add_span_processor(SimpleSpanProcessor(EXP))
trace.set_tracer_provider(_tp)
telemetry._state["init"] = True      # skip env-driven init (no OTLP endpoint / metrics port in tests)
telemetry._state["tracing"] = True
APP = make_app("astropy", ("astropy",), set_limit=False)

TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
PARENT = f"00-{TRACE_ID}-00f067aa0ba902b7-01"


def _metric(name, **labels):
    return REGISTRY.get_sample_value(name, labels) or 0.0


def _post(path, body, headers=None):
    async def go():
        t = httpx.ASGITransport(app=APP)
        async with httpx.AsyncClient(transport=t, base_url="http://test") as c:
            return await c.post(path, json=body, headers=headers or {})
    return asyncio.run(go())


def test_invoke_span_parent_and_metrics():
    EXP.clear()
    before = _metric("astro_tool_calls_total", sdk="astropy", tool="angle_to_string", transport="invoke",
                     status="ok", error_type="")
    tool = json.load(open(Path(__file__).resolve().parent.parent / "data" / "astropy_tools.json"))[0]["name"]
    before = _metric("astro_tool_calls_total", sdk="astropy", tool=tool, transport="invoke", status="ok", error_type="")
    before_err = _metric("astro_tool_calls_total", sdk="astropy", tool=tool, transport="invoke", status="error",
                         error_type="TypeError")
    r = _post("/astropy/invoke", {"function_name": tool, "arguments": {"bogus_kw": 1}},
              {"traceparent": PARENT, "x-request-id": "req-123", "authorization": "Bearer s3cret"})
    assert r.status_code == 200
    assert r.headers["x-request-id"] == "req-123"
    spans = {s.name: s for s in EXP.get_finished_spans()}
    server = spans["POST /astropy/invoke"]
    tool_span = spans[f"execute_tool {tool}"]
    assert format(server.context.trace_id, "032x") == TRACE_ID          # joined the upstream trace
    assert tool_span.parent.span_id == server.context.span_id             # child of the SERVER span
    assert server.kind == trace.SpanKind.SERVER
    a = tool_span.attributes
    assert a["gen_ai.operation.name"] == "execute_tool" and a["gen_ai.tool.name"] == tool
    assert a["astro.sdk"] == "astropy" and a["astro.transport"] == "invoke" and a["astro.args.bytes"] > 0
    ok = r.json()["ok"]
    after = _metric("astro_tool_calls_total", sdk="astropy", tool=tool, transport="invoke", status="ok", error_type="")
    after_err = sum(v for v in [_metric("astro_tool_calls_total", sdk="astropy", tool=tool, transport="invoke",
                                        status="error", error_type=e) for e in ("TypeError", "ValueError")])
    assert (after - before) + (after_err - before_err) >= 1
    if not ok:
        assert tool_span.status.status_code == trace.StatusCode.ERROR and "error.type" in a
    assert server.attributes["asa.client.fp"] and "s3cret" not in json.dumps(dict(server.attributes))
    assert _metric("astro_tool_duration_seconds_count", sdk="astropy", tool=tool, transport="invoke") >= 1


def test_meta_traceparent_wins_and_error_metrics():
    EXP.clear()
    with telemetry.tool_call("astropy", "t_err", "mcp", "x.y", {"a": 1}, parent_traceparent=PARENT) as c:
        c.failure(ValueError("boom"))
    s = EXP.get_finished_spans()[-1]
    assert format(s.context.trace_id, "032x") == TRACE_ID
    assert s.attributes["error.type"] == "ValueError"
    assert _metric("astro_tool_calls_total", sdk="astropy", tool="t_err", transport="mcp", status="error",
                   error_type="ValueError") == 1
    with telemetry.tool_call("astropy", "t_to", "mcp", "x.y", {}) as c:
        from common.engine import Timeout
        c.failure(Timeout("调用超时"))
    assert _metric("astro_tool_timeouts_total", sdk="astropy", tool="t_to") == 1
    assert _metric("astro_tool_inflight", sdk="astropy") == 0


def test_log_has_no_argument_values_or_tokens():
    buf = io.StringIO()
    secret_url = "https://oss.example.com/f.fits?OSSAccessKeyId=AKID&Signature=SIGVALUE&Expires=1"
    with contextlib.redirect_stdout(buf):
        with telemetry.tool_call("euclid", "euclid_fetch_fits", "mcp", "x", {"url": secret_url}) as c:
            c.success({"ok": True})
    line = json.loads(buf.getvalue().strip().splitlines()[-1])
    assert line["tool"] == "euclid_fetch_fits" and line["ok"] is True and line["args_bytes"] > 0
    assert "SIGVALUE" not in buf.getvalue() and "AKID" not in buf.getvalue()


def test_requests_span_url_redacted():
    class Req:
        url = "https://oss.example.com:8443/b/f.fits?Signature=SIGVALUE"
    class Span:
        attrs = {}
        def set_attribute(self, k, v): self.attrs[k] = v
    sp = Span()
    telemetry._redact_request_span(sp, Req())
    assert sp.attrs["url.full"] == "https://oss.example.com:8443/b/f.fits"


def test_fetch_and_upload_metrics():
    telemetry.record_fetch("https://casdc.example.org/x.fits?sig=1", "ok", "miss", 100, 0.2)
    assert _metric("astro_fetch_total", host="casdc.example.org", status="ok", cache="miss") == 1
    assert _metric("astro_fetch_bytes_total", host="casdc.example.org") == 100
    telemetry.record_oss_upload(False)
    assert _metric("astro_oss_upload_total", status="error") == 1
