"""Generate ASA Observability Grafana dashboards (datasource via ${ds} variable, no hosts)."""
import json, os, sys
OUT = sys.argv[1] if len(sys.argv) > 1 else "out"
os.makedirs(OUT, exist_ok=True)
DS = {"type": "prometheus", "uid": "${ds}"}
SEL = 'job="asa_obs", asa_cluster=~"$cluster"'
PAL = ["#5794F2", "#73BF69", "#FADE2A", "#FF9830", "#F2495C", "#B877D9", "#8AB8FF", "#96D98D"]
_id = [0]
def nid():
    _id[0] += 1; return _id[0]

def tgt(expr, legend="", ref="A", instant=False, fmt=None):
    t = {"datasource": DS, "expr": expr, "legendFormat": legend, "refId": ref, "range": not instant, "instant": instant}
    if fmt: t["format"] = fmt
    return t

def stat(title, expr, x, y, w=4, h=4, unit="short", dec=None, thresholds=None, desc="", color_mode="background", legend=""):
    th = thresholds or [("green", None)]
    p = {"id": nid(), "type": "stat", "title": title, "description": desc, "datasource": DS,
         "gridPos": {"x": x, "y": y, "w": w, "h": h},
         "targets": [tgt(expr, legend, instant=True)],
         "fieldConfig": {"defaults": {"unit": unit, "color": {"mode": "thresholds"},
                         "thresholds": {"mode": "absolute", "steps": [{"color": c, "value": v} for c, v in th]},
                         "noValue": "0"}, "overrides": []},
         "options": {"colorMode": color_mode, "graphMode": "area", "justifyMode": "center", "textMode": "auto",
                     "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "wideLayout": True}}
    if dec is not None: p["fieldConfig"]["defaults"]["decimals"] = dec
    return p

def ts(title, targets, x, y, w=12, h=8, unit="short", stack=False, desc="", fill=18, draw="line", overrides=None, legend_calcs=("mean", "max", "lastNotNull"), minv=None):
    d = {"unit": unit, "color": {"mode": "palette-classic"},
         "custom": {"drawStyle": draw, "lineWidth": 2, "fillOpacity": fill, "gradientMode": "opacity",
                    "showPoints": "never", "spanNulls": True, "axisBorderShow": False,
                    "stacking": {"mode": "normal" if stack else "none", "group": "A"}, "lineInterpolation": "smooth"}}
    if minv is not None: d["min"] = minv
    return {"id": nid(), "type": "timeseries", "title": title, "description": desc, "datasource": DS,
            "gridPos": {"x": x, "y": y, "w": w, "h": h}, "targets": targets,
            "fieldConfig": {"defaults": d, "overrides": overrides or []},
            "options": {"legend": {"displayMode": "table", "placement": "bottom", "calcs": list(legend_calcs), "showLegend": True},
                        "tooltip": {"mode": "multi", "sort": "desc"}}}

def row(title, y, collapsed=False):
    return {"id": nid(), "type": "row", "title": title, "collapsed": collapsed, "gridPos": {"x": 0, "y": y, "w": 24, "h": 1}, "panels": []}

def text(title, md, x, y, w=24, h=4):
    return {"id": nid(), "type": "text", "title": title, "gridPos": {"x": x, "y": y, "w": w, "h": h},
            "options": {"mode": "markdown", "content": md}}

def table(title, targets, x, y, w=24, h=9, overrides=None, transformations=None, desc=""):
    return {"id": nid(), "type": "table", "title": title, "description": desc, "datasource": DS,
            "gridPos": {"x": x, "y": y, "w": w, "h": h}, "targets": targets,
            "fieldConfig": {"defaults": {"custom": {"align": "auto", "cellOptions": {"type": "auto"}}}, "overrides": overrides or []},
            "options": {"showHeader": True, "cellHeight": "sm", "footer": {"show": False}},
            "transformations": transformations or []}

def var_ds():
    return {"name": "ds", "label": "Prometheus", "type": "datasource", "query": "prometheus",
            "current": {"text": "Prometheus", "value": "prometheus"}, "hide": 0, "refresh": 1, "regex": ""}

def var_q(name, label, query, multi=True, include_all=True, hide=0):
    return {"name": name, "label": label, "type": "query", "datasource": DS,
            "query": {"query": query, "refId": "v"}, "definition": query, "refresh": 2,
            "multi": multi, "includeAll": include_all, "allValue": ".*", "hide": hide, "sort": 1,
            "current": {"text": "All", "value": "$__all"} if include_all else {}}

def var_cluster():
    return var_q("cluster", "Cluster", 'label_values(asa_up{job="asa_obs"}, asa_cluster)', multi=False, include_all=True)

def dash(uid, title, panels, variables, tags, desc="", links=True):
    d = {"uid": uid, "title": title, "description": desc, "tags": ["asa", "observability"] + tags,
         "timezone": "browser", "editable": True, "graphTooltip": 1, "style": "dark",
         "time": {"from": "now-6h", "to": "now"}, "refresh": "30s", "schemaVersion": 39,
         "fiscalYearStartMonth": 0, "weekStart": "",
         "templating": {"list": [var_ds()] + variables}, "annotations": {"list": []}, "panels": panels,
         "links": [{"title": "ASA dashboards", "type": "dashboards", "tags": ["asa"], "asDropdown": True, "includeVars": True, "keepTime": True, "icon": "external link"}] if links else []}
    with open(os.path.join(OUT, uid + ".json"), "w") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)
    return d

# ---------- shared exprs ----------
T = f'{SEL}, sdk=~"$sdk"'
CALLS = f'astro_tool_calls_total{{{T}}}'
DUR = f'astro_tool_duration_seconds_bucket{{{T}}}'
def q(p, by, r="$__rate_interval"):
    return f'histogram_quantile({p}, sum by (le, {by}) (rate({DUR}[{r}])))' if by else f'histogram_quantile({p}, sum by (le) (rate({DUR}[{r}])))'
sdk_var = var_q("sdk", "SDK", f'label_values(astro_tool_calls_total{{job="asa_obs", asa_cluster=~"$cluster"}}, sdk)')
ERR_TH = [("green", None), ("orange", 1), ("red", 5)]
LAT_TH = [("green", None), ("orange", 2), ("red", 10)]

# ===== 1. Overview =====
_id[0] = 0
y = 0
P = [text("", "#### 🔭 ASA Observability · Overview\nastro-sdk-services MCP / HTTP tools, Tempo + OTel Collector, Pod 资源。指标经 OTel Collector → Pushgateway (`job=asa_obs`) → Prometheus；Trace 存于 Tempo（72h）。Agent/LLM token 与任务耗时面板 **等待 Workspace 埋点**。", 0, y, 24, 3)]
y += 3
P += [stat("Tool calls / min", f'sum(rate({CALLS}[5m])) * 60', 0, y, unit="short", dec=1, color_mode="value"),
      stat("Calls (range)", f'sum(increase({CALLS}[$__range]))', 4, y, unit="short", dec=0, color_mode="value"),
      stat("Error rate", f'100 * sum(rate(astro_tool_calls_total{{{T}, status="error"}}[$__range])) / clamp_min(sum(rate({CALLS}[$__range])), 1e-9)', 8, y, unit="percent", dec=1, thresholds=ERR_TH),
      stat("p95 latency", q(0.95, None, "$__range"), 12, y, unit="s", dec=2, thresholds=LAT_TH),
      stat("In-flight", f'sum(astro_tool_inflight{{{T}}})', 16, y, unit="short", dec=0, color_mode="value"),
      stat("Targets up", f'sum(asa_up{{{SEL}}}) ', 20, y, unit="short", dec=0, thresholds=[("red", None), ("green", 1)],
           desc="Scrape targets (astro-sdk / asa-workspace pods with asa.obs/scrape=true) seen by the collector")]
y += 4
P += [ts("Tool calls by SDK (req/s)", [tgt(f'sum by (sdk) (rate({CALLS}[$__rate_interval]))', "{{sdk}}")], 0, y, 12, 8, unit="reqps", stack=True),
      ts("Latency by SDK (p50 / p95)", [tgt(q(0.5, "sdk"), "p50 {{sdk}}", "A"), tgt(q(0.95, "sdk"), "p95 {{sdk}}", "B")], 12, y, 12, 8, unit="s", fill=5,
         overrides=[{"matcher": {"id": "byRegexp", "options": "^p50.*"}, "properties": [{"id": "custom.lineStyle", "value": {"fill": "dash", "dash": [6, 4]}}]}])]
y += 8
P += [ts("Errors by SDK / type (per min)", [tgt(f'sum by (sdk, error_type) (rate(astro_tool_calls_total{{{T}, status="error"}}[$__rate_interval])) * 60', "{{sdk}} · {{error_type}}")], 0, y, 12, 8, unit="short", draw="bars", fill=80, stack=True),
      ts("HTTP responses by code (req/s)", [tgt(f'sum by (code) (rate(astro_http_requests_total{{{SEL}}}[$__rate_interval]))', "{{code}}")], 12, y, 12, 8, unit="reqps", stack=True,
         overrides=[{"matcher": {"id": "byRegexp", "options": "^5.."}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "red"}}]},
                    {"matcher": {"id": "byRegexp", "options": "^4.."}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "orange"}}]},
                    {"matcher": {"id": "byRegexp", "options": "^2.."}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "green"}}]}])]
y += 8
P += [ts("Memory working set by namespace", [tgt(f'sum by (k8s_namespace_name) (asa_k8s_pod_memory_working_set_bytes{{{SEL}}})', "{{k8s_namespace_name}}")], 0, y, 12, 8, unit="bytes", stack=True),
      ts("CPU by namespace (cores)", [tgt(f'sum by (k8s_namespace_name) (asa_k8s_pod_cpu_usage{{{SEL}}})', "{{k8s_namespace_name}}")], 12, y, 12, 8, unit="short", stack=True)]
y += 8
P += [text("⏳ Agent / LLM — waiting on Workspace", "Token 用量、任务（workflow / step）耗时、LLM 调用延迟需要 **asa-workspace** 侧 OTel 埋点（`gen_ai.client.token.usage`、`asa.workflow.*` span）。埋点上线后，面板见 **ASA · Agent & LLM** dashboard，无需改动。", 0, y, 24, 3)]
dash("asa-overview", "ASA · Overview", P, [var_cluster(), sdk_var], ["overview"], "ASA observability overview")

# ===== 2. MCP tools =====
_id[0] = 0
tool_var = var_q("tool", "Tool", f'label_values(astro_tool_calls_total{{job="asa_obs", asa_cluster=~"$cluster", sdk=~"$sdk"}}, tool)')
TT = f'{T}, tool=~"$tool"'
CT = f'astro_tool_calls_total{{{TT}}}'
DT = f'astro_tool_duration_seconds_bucket{{{TT}}}'
y = 0
P = [stat("Calls (range)", f'sum(increase({CT}[$__range]))', 0, y, 6, 4, dec=0, color_mode="value"),
     stat("Error rate", f'100 * sum(rate(astro_tool_calls_total{{{TT}, status="error"}}[$__range])) / clamp_min(sum(rate({CT}[$__range])), 1e-9)', 6, y, 6, 4, unit="percent", dec=1, thresholds=ERR_TH),
     stat("p50 latency", f'histogram_quantile(0.5, sum by (le) (rate({DT}[$__range])))', 12, y, 6, 4, unit="s", dec=2, thresholds=LAT_TH),
     stat("p99 latency", f'histogram_quantile(0.99, sum by (le) (rate({DT}[$__range])))', 18, y, 6, 4, unit="s", dec=2, thresholds=LAT_TH)]
y += 4
P += [table("Per-tool summary (selected range)", [
        tgt(f'sum by (sdk, tool) (increase({CT}[$__range]))', "", "A", True, "table"),
        tgt(f'sum by (sdk, tool) (increase(astro_tool_calls_total{{{TT}, status="error"}}[$__range]))', "", "B", True, "table"),
        tgt(f'histogram_quantile(0.5, sum by (le, sdk, tool) (rate({DT}[$__range])))', "", "C", True, "table"),
        tgt(f'histogram_quantile(0.95, sum by (le, sdk, tool) (rate({DT}[$__range])))', "", "D", True, "table"),
        tgt(f'sum by (sdk, tool) (increase(astro_tool_response_bytes_sum{{{TT}}}[$__range])) / clamp_min(sum by (sdk, tool) (increase(astro_tool_response_bytes_count{{{TT}}}[$__range])), 1)', "", "E", True, "table")],
        0, y, 24, 10,
        transformations=[{"id": "merge", "options": {}},
                         {"id": "organize", "options": {"excludeByName": {"Time": True},
                          "renameByName": {"Value #A": "Calls", "Value #B": "Errors", "Value #C": "p50 (s)", "Value #D": "p95 (s)", "Value #E": "Avg response", "sdk": "SDK", "tool": "Tool"}}},
                         {"id": "sortBy", "options": {"sort": [{"field": "Calls", "desc": True}]}}],
        overrides=[{"matcher": {"id": "byName", "options": "Calls"}, "properties": [{"id": "decimals", "value": 0}, {"id": "custom.cellOptions", "value": {"type": "gauge", "mode": "basic"}}, {"id": "color", "value": {"mode": "continuous-BlPu"}}]},
                   {"matcher": {"id": "byName", "options": "Errors"}, "properties": [{"id": "decimals", "value": 0}, {"id": "custom.cellOptions", "value": {"type": "color-background", "mode": "basic"}}, {"id": "thresholds", "value": {"mode": "absolute", "steps": [{"color": "transparent", "value": None}, {"color": "red", "value": 1}]}}, {"id": "color", "value": {"mode": "thresholds"}}]},
                   {"matcher": {"id": "byRegexp", "options": "^p(50|95).*"}, "properties": [{"id": "unit", "value": "s"}, {"id": "decimals", "value": 2}, {"id": "custom.cellOptions", "value": {"type": "color-text"}}, {"id": "thresholds", "value": {"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "orange", "value": 2}, {"color": "red", "value": 10}]}}, {"id": "color", "value": {"mode": "thresholds"}}]},
                   {"matcher": {"id": "byName", "options": "Avg response"}, "properties": [{"id": "unit", "value": "bytes"}]}])]
y += 10
P += [ts("Calls by tool (req/s)", [tgt(f'sum by (sdk, tool) (rate({CT}[$__rate_interval]))', "{{sdk}}/{{tool}}")], 0, y, 12, 9, unit="reqps", stack=True),
      ts("p95 latency by tool", [tgt(f'histogram_quantile(0.95, sum by (le, sdk, tool) (rate({DT}[$__rate_interval])))', "{{sdk}}/{{tool}}")], 12, y, 12, 9, unit="s", fill=0)]
y += 9
P += [{"id": nid(), "type": "heatmap", "title": "Latency distribution (all selected tools)", "datasource": DS,
       "gridPos": {"x": 0, "y": y, "w": 12, "h": 9},
       "targets": [tgt(f'sum by (le) (increase({DT}[$__rate_interval]))', "{{le}}", fmt="heatmap")],
       "options": {"calculate": False, "yAxis": {"unit": "s", "axisPlacement": "left"}, "color": {"mode": "scheme", "scheme": "Spectral", "steps": 64, "reverse": True, "exponent": 0.5},
                   "cellGap": 1, "tooltip": {"mode": "single", "yHistogram": True}, "legend": {"show": True}, "rowsFrame": {"layout": "auto"}, "filterValues": {"le": 1e-9}}},
      ts("Errors by tool / type (per min)", [tgt(f'sum by (sdk, tool, error_type) (rate(astro_tool_calls_total{{{TT}, status="error"}}[$__rate_interval])) * 60', "{{sdk}}/{{tool}} · {{error_type}}")], 12, y, 12, 9, draw="bars", fill=80, stack=True)]
y += 9
P += [ts("Calls by transport", [tgt(f'sum by (transport) (rate({CT}[$__rate_interval]))', "{{transport}}")], 0, y, 8, 8, unit="reqps", stack=True),
      ts("Timeouts / in-flight", [tgt(f'sum by (sdk) (increase(astro_tool_timeouts_total{{{T}}}[$__rate_interval]))', "timeouts {{sdk}}", "A"),
                                  tgt(f'sum by (sdk) (astro_tool_inflight{{{T}}})', "in-flight {{sdk}}", "B")], 8, y, 8, 8),
      ts("Request / response size (avg)", [tgt(f'sum(rate(astro_tool_request_bytes_sum{{{TT}}}[$__rate_interval])) / clamp_min(sum(rate(astro_tool_request_bytes_count{{{TT}}}[$__rate_interval])), 1e-9)', "request", "A"),
                                          tgt(f'sum(rate(astro_tool_response_bytes_sum{{{TT}}}[$__rate_interval])) / clamp_min(sum(rate(astro_tool_response_bytes_count{{{TT}}}[$__rate_interval])), 1e-9)', "response", "B")], 16, y, 8, 8, unit="bytes", fill=5)]
y += 8
P += [row("Remote fetch / OSS (euclid cache, when enabled)", y)]
y += 1
P += [ts("Fetch results", [tgt(f'sum by (result) (rate(astro_fetch_total{{{SEL}}}[$__rate_interval]))', "{{result}}")], 0, y, 8, 7, unit="reqps", stack=True),
      ts("Fetch throughput", [tgt(f'sum(rate(astro_fetch_bytes_total{{{SEL}}}[$__rate_interval]))', "bytes/s")], 8, y, 8, 7, unit="Bps"),
      ts("OSS uploads", [tgt(f'sum by (result) (rate(astro_oss_upload_total{{{SEL}}}[$__rate_interval]))', "{{result}}")], 16, y, 8, 7, unit="reqps", stack=True)]
dash("asa-mcp-tools", "ASA · MCP Tools", P, [var_cluster(), sdk_var, tool_var], ["mcp"], "Per-tool calls, latency, errors")

# ===== 3. Resources =====
_id[0] = 0
ns_var = var_q("namespace", "Namespace", f'label_values(asa_k8s_pod_memory_working_set_bytes{{job="asa_obs", asa_cluster=~"$cluster"}}, k8s_namespace_name)')
ns_var["current"] = {"text": ["astro-sdk", "observability"], "value": ["astro-sdk", "observability"]}
pod_var = var_q("pod", "Pod", f'label_values(asa_k8s_pod_memory_working_set_bytes{{job="asa_obs", asa_cluster=~"$cluster", k8s_namespace_name=~"$namespace"}}, k8s_pod_name)')
N = f'{SEL}, k8s_namespace_name=~"$namespace", k8s_pod_name=~"$pod"'
y = 0
P = [stat("Memory (working set)", f'sum(asa_k8s_pod_memory_working_set_bytes{{{N}}})', 0, y, 6, 4, unit="bytes", dec=0, color_mode="value"),
     stat("Memory requests", f'sum(asa_k8s_container_memory_request_bytes{{{N}}})', 6, y, 6, 4, unit="bytes", dec=0, color_mode="value"),
     stat("Memory limits", f'sum(asa_k8s_container_memory_limit_bytes{{{N}}})', 12, y, 6, 4, unit="bytes", dec=0, color_mode="value"),
     stat("Container restarts (range)", f'sum(increase(asa_k8s_container_restarts{{{N}}}[$__range]))', 18, y, 6, 4, dec=0, thresholds=[("green", None), ("orange", 1), ("red", 3)])]
y += 4
P += [ts("Pod memory working set", [tgt(f'sum by (k8s_namespace_name, k8s_pod_name) (asa_k8s_pod_memory_working_set_bytes{{{N}}})', "{{k8s_pod_name}}")], 0, y, 12, 9, unit="bytes"),
      ts("Pod memory vs limit (%)", [tgt(f'100 * max by (k8s_pod_name) (asa_k8s_pod_memory_limit_utilization_ratio{{{N}}})', "{{k8s_pod_name}}")], 12, y, 12, 9, unit="percent", fill=5, minv=0,
         overrides=[], desc="working set / sum of container limits")]
P[-1]["fieldConfig"]["defaults"]["thresholds"] = {"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "orange", "value": 75}, {"color": "red", "value": 90}]}
P[-1]["fieldConfig"]["defaults"]["custom"]["thresholdsStyle"] = {"mode": "line+area"}
y += 9
P += [ts("Pod CPU (cores)", [tgt(f'sum by (k8s_pod_name) (asa_k8s_pod_cpu_usage{{{N}}})', "{{k8s_pod_name}}")], 0, y, 12, 8),
      ts("Container CPU vs limit (%)", [tgt(f'100 * max by (k8s_pod_name, k8s_container_name) (asa_k8s_container_cpu_limit_utilization_ratio{{{N}}})', "{{k8s_pod_name}}/{{k8s_container_name}}")], 12, y, 12, 8, unit="percent", fill=5, minv=0)]
y += 8
P += [table("Containers: usage / request / limit", [
        tgt(f'sum by (k8s_namespace_name, k8s_pod_name, k8s_container_name) (asa_container_memory_working_set_bytes{{{N}}})', "", "A", True, "table"),
        tgt(f'sum by (k8s_namespace_name, k8s_pod_name, k8s_container_name) (asa_k8s_container_memory_request_bytes{{{N}}})', "", "B", True, "table"),
        tgt(f'sum by (k8s_namespace_name, k8s_pod_name, k8s_container_name) (asa_k8s_container_memory_limit_bytes{{{N}}})', "", "C", True, "table"),
        tgt(f'sum by (k8s_namespace_name, k8s_pod_name, k8s_container_name) (asa_container_cpu_usage{{{N}}})', "", "D", True, "table"),
        tgt(f'sum by (k8s_namespace_name, k8s_pod_name, k8s_container_name) (asa_k8s_container_restarts{{{N}}})', "", "E", True, "table")],
        0, y, 24, 9,
        transformations=[{"id": "merge", "options": {}},
                         {"id": "organize", "options": {"excludeByName": {"Time": True},
                          "renameByName": {"k8s_namespace_name": "Namespace", "k8s_pod_name": "Pod", "k8s_container_name": "Container",
                                           "Value #A": "Mem used", "Value #B": "Mem request", "Value #C": "Mem limit", "Value #D": "CPU (cores)", "Value #E": "Restarts"}}},
                         {"id": "sortBy", "options": {"sort": [{"field": "Mem used", "desc": True}]}}],
        overrides=[{"matcher": {"id": "byRegexp", "options": "^Mem.*"}, "properties": [{"id": "unit", "value": "bytes"}]},
                   {"matcher": {"id": "byName", "options": "Mem used"}, "properties": [{"id": "custom.cellOptions", "value": {"type": "gauge", "mode": "lcd"}}, {"id": "color", "value": {"mode": "continuous-GrYlRd"}}]},
                   {"matcher": {"id": "byName", "options": "CPU (cores)"}, "properties": [{"id": "decimals", "value": 3}]}])]
y += 9
P += [row("Nodes", y)]
y += 1
P += [ts("Node memory working set", [tgt(f'max by (k8s_node_name) (asa_k8s_node_memory_working_set_bytes{{{SEL}}})', "{{k8s_node_name}} used", "A"),
                                     tgt(f'max by (k8s_node_name) (asa_k8s_node_allocatable_memory_bytes{{{SEL}}})', "{{k8s_node_name}} allocatable", "B")], 0, y, 12, 8, unit="bytes", fill=8),
      ts("Node CPU (cores)", [tgt(f'max by (k8s_node_name) (asa_k8s_node_cpu_usage{{{SEL}}})', "{{k8s_node_name}} used", "A"),
                              tgt(f'max by (k8s_node_name) (asa_k8s_node_allocatable_cpu{{{SEL}}})', "{{k8s_node_name}} allocatable", "B")], 12, y, 12, 8, fill=8)]
y += 8
P += [ts("OTel Collector: RSS / heap", [tgt(f'max(asa_otelcol_process_memory_rss_bytes{{{SEL}}})', "rss", "A"), tgt(f'max(asa_otelcol_process_runtime_heap_alloc_bytes{{{SEL}}})', "heap", "B")], 0, y, 12, 7, unit="bytes", fill=5),
      ts("OTel Collector: metric points", [tgt(f'sum(rate(asa_otelcol_receiver_accepted_metric_points_total{{{SEL}}}[$__rate_interval]))', "accepted", "A"),
                                           tgt(f'sum(rate(asa_otelcol_receiver_refused_metric_points_total{{{SEL}}}[$__rate_interval]))', "refused", "B"),
                                           tgt(f'sum(rate(asa_otelcol_exporter_send_failed_metric_points_total{{{SEL}}}[$__rate_interval]))', "export failed", "C")], 12, y, 12, 7, unit="short", fill=5)]
dash("asa-resources", "ASA · Pod Resources", P, [var_cluster(), ns_var, pod_var], ["resources"], "Pod / container / node CPU and memory")

# ===== 4. Traces (spanmetrics) =====
_id[0] = 0
SM = f'{SEL}, asa_service=~"$service"'
svc_var = var_q("service", "Service", f'label_values(asa_traces_span_metrics_calls_total{{job="asa_obs", asa_cluster=~"$cluster"}}, asa_service)')
y = 0
P = [text("", "#### 🧵 Traces (span metrics)\nRED metrics derived from every span by the collector's `spanmetrics` connector (before tail sampling). Raw traces live in **Tempo** (72h retention, tail-sampled: all errors, spans > 5s, workflow runs, 20% of the rest). Tempo datasource: _pending Grafana admin_ — query traces via Explore once it is added.", 0, y, 24, 3)]
y += 3
P += [stat("Spans / s", f'sum(rate(asa_traces_span_metrics_calls_total{{{SM}}}[5m]))', 0, y, 6, 4, unit="short", dec=2, color_mode="value"),
      stat("Error spans %", f'100 * sum(rate(asa_traces_span_metrics_calls_total{{{SM}, status_code="STATUS_CODE_ERROR"}}[$__range])) / clamp_min(sum(rate(asa_traces_span_metrics_calls_total{{{SM}}}[$__range])), 1e-9)', 6, y, 6, 4, unit="percent", dec=1, thresholds=ERR_TH),
      stat("p95 HTTP request span", f'histogram_quantile(0.95, sum by (le) (rate(asa_traces_span_metrics_duration_seconds_bucket{{{SM}, span_name=~"(GET|POST|PUT|DELETE) .*"}}[$__range])))', 12, y, 6, 4, unit="s", dec=2, thresholds=LAT_TH),
      stat("Services", f'count(count by (asa_service) (asa_traces_span_metrics_calls_total{{{SEL}}}))', 18, y, 6, 4, dec=0, color_mode="value")]
y += 4
P += [ts("Span rate by operation", [tgt(f'sum by (asa_service, span_name) (rate(asa_traces_span_metrics_calls_total{{{SM}}}[$__rate_interval]))', "{{asa_service}} · {{span_name}}")], 0, y, 12, 9, unit="reqps", stack=True),
      ts("p95 by operation", [tgt(f'histogram_quantile(0.95, sum by (le, span_name) (rate(asa_traces_span_metrics_duration_seconds_bucket{{{SM}}}[$__rate_interval])))', "{{span_name}}")], 12, y, 12, 9, unit="s", fill=0)]
y += 9
P += [table("Operations (selected range)", [
        tgt(f'sum by (asa_service, span_name) (increase(asa_traces_span_metrics_calls_total{{{SM}}}[$__range]))', "", "A", True, "table"),
        tgt(f'sum by (asa_service, span_name) (increase(asa_traces_span_metrics_calls_total{{{SM}, status_code="STATUS_CODE_ERROR"}}[$__range]))', "", "B", True, "table"),
        tgt(f'histogram_quantile(0.95, sum by (le, asa_service, span_name) (rate(asa_traces_span_metrics_duration_seconds_bucket{{{SM}}}[$__range])))', "", "C", True, "table")],
        0, y, 24, 10,
        transformations=[{"id": "merge", "options": {}},
                         {"id": "organize", "options": {"excludeByName": {"Time": True},
                          "renameByName": {"asa_service": "Service", "span_name": "Operation", "Value #A": "Spans", "Value #B": "Errors", "Value #C": "p95 (s)"}}},
                         {"id": "sortBy", "options": {"sort": [{"field": "Spans", "desc": True}]}}],
        overrides=[{"matcher": {"id": "byName", "options": "Spans"}, "properties": [{"id": "decimals", "value": 0}, {"id": "custom.cellOptions", "value": {"type": "gauge", "mode": "basic"}}, {"id": "color", "value": {"mode": "continuous-BlPu"}}]},
                   {"matcher": {"id": "byName", "options": "Errors"}, "properties": [{"id": "decimals", "value": 0}, {"id": "custom.cellOptions", "value": {"type": "color-background"}}, {"id": "thresholds", "value": {"mode": "absolute", "steps": [{"color": "transparent", "value": None}, {"color": "red", "value": 1}]}}, {"id": "color", "value": {"mode": "thresholds"}}]},
                   {"matcher": {"id": "byName", "options": "p95 (s)"}, "properties": [{"id": "unit", "value": "s"}, {"id": "decimals", "value": 3}]}])]
y += 10
P += [ts("Service graph: requests between services", [tgt(f'sum by (client, server) (rate(asa_traces_service_graph_request_total{{{SEL}}}[$__rate_interval]))', "{{client}} → {{server}}")], 0, y, 12, 8, unit="reqps"),
      ts("Service graph: failed requests", [tgt(f'sum by (client, server) (rate(asa_traces_service_graph_request_failed_total{{{SEL}}}[$__rate_interval]))', "{{client}} → {{server}}")], 12, y, 12, 8, unit="reqps")]
dash("asa-traces", "ASA · Traces (span metrics)", P, [var_cluster(), svc_var], ["traces"], "Span metrics from the OTel collector; raw traces in Tempo")

# ===== 5. Agent & LLM (placeholders) =====
_id[0] = 0
y = 0
W = "⏳ waiting on Workspace"
P = [text("", "#### 🤖 Agent & LLM — ⏳ waiting on Workspace instrumentation\n这些面板已经按 OTel GenAI 语义约定写好查询；**asa-workspace** 输出 `gen_ai.client.token.usage` / `gen_ai.client.operation.duration` 指标及 `asa.workflow.key`、`asa.step.id` span 属性后会自动出数据（collector 已就绪，指标统一加 `asa_` 前缀）。", 0, y, 24, 3)]
y += 3
TOK = f'asa_gen_ai_client_token_usage_sum{{{SEL}}}'
P += [stat(f"Tokens (range) · {W}", f'sum(increase({TOK}[$__range]))', 0, y, 8, 4, dec=0, color_mode="value"),
      stat(f"LLM calls (range) · {W}", f'sum(increase(asa_gen_ai_client_operation_duration_seconds_count{{{SEL}}}[$__range]))', 8, y, 8, 4, dec=0, color_mode="value"),
      stat(f"Task p95 · {W}", f'histogram_quantile(0.95, sum by (le) (rate(asa_traces_span_metrics_duration_seconds_bucket{{{SEL}, asa_workflow_key!=""}}[$__range])))', 16, y, 8, 4, unit="s", dec=1, thresholds=LAT_TH)]
for p in P[-3:]: p["fieldConfig"]["defaults"]["noValue"] = "waiting on Workspace"
y += 4
P += [ts(f"Tokens by model / type · {W}", [tgt(f'sum by (gen_ai_request_model, gen_ai_token_type) (rate({TOK}[$__rate_interval])) * 60', "{{gen_ai_request_model}} · {{gen_ai_token_type}}")], 0, y, 12, 8, unit="short", stack=True, desc="tokens / min"),
      ts(f"LLM latency p95 by model · {W}", [tgt(f'histogram_quantile(0.95, sum by (le, gen_ai_request_model) (rate(asa_gen_ai_client_operation_duration_seconds_bucket{{{SEL}}}[$__rate_interval])))', "{{gen_ai_request_model}}")], 12, y, 12, 8, unit="s", fill=0)]
y += 8
P += [ts(f"Task (workflow) duration p50/p95 · {W}", [tgt(f'histogram_quantile(0.5, sum by (le, asa_workflow_key) (rate(asa_traces_span_metrics_duration_seconds_bucket{{{SEL}, asa_workflow_key!=""}}[$__rate_interval])))', "p50 {{asa_workflow_key}}", "A"),
                                                      tgt(f'histogram_quantile(0.95, sum by (le, asa_workflow_key) (rate(asa_traces_span_metrics_duration_seconds_bucket{{{SEL}, asa_workflow_key!=""}}[$__rate_interval])))', "p95 {{asa_workflow_key}}", "B")], 0, y, 12, 8, unit="s", fill=0),
      ts(f"Step duration p95 · {W}", [tgt(f'histogram_quantile(0.95, sum by (le, asa_step_id) (rate(asa_traces_span_metrics_duration_seconds_bucket{{{SEL}, asa_step_id!=""}}[$__rate_interval])))', "{{asa_step_id}}")], 12, y, 12, 8, unit="s", fill=0)]
for p in P:
    if p["type"] == "timeseries": p["fieldConfig"]["defaults"]["noValue"] = "waiting on Workspace"
dash("asa-agent-llm", "ASA · Agent & LLM (waiting on Workspace)", P, [var_cluster()], ["agent", "placeholder"], "Placeholders until asa-workspace emits GenAI telemetry")
print("ok", sorted(os.listdir(OUT)))
