"""Call /invoke on a running service for every case; write results/<sdk>.json."""
import json, sys, os, re, requests, time, urllib3
urllib3.disable_warnings()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORTS = {"astropy": 9101, "astroquery": 9102, "photutils": 9103, "astroplan": 9104, "sunpy": 9105}
NET = re.compile(r"ConnectionError|Timeout|timed out|Max retries|HTTPError|503|502|504|500 Server|Name or service|ConnectTimeout|ReadTimeout|URLError|Remote end|RemoteDisconnected|SSLError|Connection refused|Connection reset|Service Unavailable|Bad Gateway|调用超时|Failed to resolve|urlopen error|Gateway", re.I)
def run(sdk, only=None):
    cases = json.load(open(f"{ROOT}/cases/{sdk}.json"))
    # BASE_URL e.g. https://astro.example.com (-> BASE_URL/<sdk>/invoke); API_TOKEN optional bearer token
    base = os.environ.get("BASE_URL", "").rstrip("/")
    base = f"{base}/{sdk}" if base else f"http://127.0.0.1:{PORTS[sdk]}"
    hdr = {"Authorization": "Bearer " + os.environ["API_TOKEN"]} if os.environ.get("API_TOKEN") else {}
    res = []
    for c in cases:
        if only and c["name"] not in only: continue
        r = {"name": c["name"], "arguments": c["arguments"]}
        if c["skip"]:
            r.update(status="未验证：" + c["skip"] if c["skip"] != "NO_CASE" else "未验证：暂无测试入参", ok=None, error=None, result=None, elapsed=0)
        else:
            t0 = time.time()
            try:
                j = requests.post(base + "/invoke", json={"function_name": c["name"], "arguments": c["arguments"]}, timeout=120, headers=hdr, verify=os.environ.get("VERIFY_TLS","1")!="0").json()
            except Exception as e:
                j = {"ok": False, "error": f"HTTP: {e}", "result": None}
            r.update(ok=j["ok"], error=j.get("error"), result=j.get("result"), elapsed=round(time.time() - t0, 2))
            if j["ok"]:
                r["status"] = "可用：真实调用成功"
            elif sdk == "astroquery" and not (j.get("error") or "").startswith("HTTP:") and NET.search(j.get("error") or ""):
                r["status"] = "未验证：外部服务不可达/超时（" + (j["error"] or "")[:150] + "）"
            else:
                r["status"] = "失败：" + (j.get("error") or "")[:300]
        res.append(r)
    os.makedirs(f"{ROOT}/results", exist_ok=True)
    json.dump(res, open(f"{ROOT}/results/{sdk}.json", "w"), ensure_ascii=False, indent=1)
    from collections import Counter
    print(sdk, Counter(x["status"].split("：")[0] for x in res))
    return res
if __name__ == "__main__":
    run(sys.argv[1], set(sys.argv[2:]) or None)
