import os
FX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures")
OUT = "/tmp/astro_out"
def C(path, *args, _self=None, **kw):
    d = {"__call__": path}
    if args: d["args"] = list(args)
    if kw: d["kwargs"] = kw
    if _self is not None: d["self"] = _self
    return d
def Q(v, u): return {"value": v, "unit": u}
def T(s="2026-10-12T12:00:00", fmt=None, scale="utc"):
    d = {"__type__": "Time", "value": s, "scale": scale}
    if fmt: d["format"] = fmt
    return d
def SC(ra=10.684, dec=41.269, **kw): return {"ra": ra, "dec": dec, "unit": "deg", **kw}
def ARR(x, dtype=None): return {"__type__": "ndarray", "data": x, **({"dtype": dtype} if dtype else {})}
def TAB(rows=None, units=None):
    rows = rows or [{"id": i, "ra": 10 + .1 * i, "dec": 41 + .1 * i, "mag": 12 + i, "name": "abcde"[i - 1]} for i in range(1, 6)]
    d = {"__type__": "Table", "rows": rows}
    if units: d["units"] = units
    return d
IMG = C("numpy.load", FX + "/image.npy")
FITS = FX + "/image.fits"
