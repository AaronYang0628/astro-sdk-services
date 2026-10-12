"""Build cases/<sdk>.json: one reproducible test input per tool."""
import json, sys, importlib, os
sys.path.insert(0, os.path.dirname(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def build(sdk):
    m = importlib.import_module(f"cases_{sdk}")
    tools = json.load(open(f"{ROOT}/data/{sdk}_tools_all.json"))
    sel = [pre_ + n if not n.startswith(pre_) else n for n in getattr(m, "SELECT", [])] if (pre_ := sdk + "_") else []
    if sel:
        byname = {t["name"]: t for t in tools}
        tools = [byname[n] for n in sel]
        json.dump(tools, open(f"{ROOT}/data/{sdk}_tools.json", "w"), ensure_ascii=False, indent=1)
    else:
        json.dump(tools, open(f"{ROOT}/data/{sdk}_tools.json", "w"), ensure_ascii=False, indent=1)
    pre = sdk + "_"
    out = []
    for t in tools:
        short = t["name"][len(pre):] if t["name"].startswith(pre) else t["name"]
        case = {"name": t["name"], "arguments": None, "skip": None}
        if short in getattr(m, "SKIP", {}):
            case["skip"] = m.SKIP[short]
        elif short in m.ARGS or t["name"] in m.ARGS:
            args = dict(m.ARGS.get(short, m.ARGS.get(t["name"])))
            cls = t["target"].rsplit(".", 1)[0]
            if cls in m.SELF and m.SELF[cls] is not None and "_self" not in args and not getattr(m, "NO_SELF", set()) & {short}:
                args["_self"] = m.SELF[cls]
            case["arguments"] = args
        else:
            case["skip"] = "NO_CASE"
        out.append(case)
    json.dump(out, open(f"{ROOT}/cases/{sdk}.json", "w"), ensure_ascii=False, indent=1)
    n_no = sum(1 for c in out if c["skip"] == "NO_CASE")
    print(sdk, len(out), "no_case:", [c["name"] for c in out if c["skip"] == "NO_CASE"][:80])
if __name__ == "__main__":
    build(sys.argv[1])
