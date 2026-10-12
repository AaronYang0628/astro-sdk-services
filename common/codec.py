"""JSON <-> Python object codec for astronomy objects.

Inbound (decode) conventions:
  {"value": 1.0, "unit": "deg"}                      -> astropy Quantity
  {"ra":..,"dec":..,"unit":"deg","frame":"icrs"}     -> SkyCoord  (also l/b for galactic)
  {"__type__":"Time","value":..,"format":..,"scale":..} -> Time
  {"__type__":"ndarray","data":[..],"dtype":..}      -> numpy array
  {"__type__":"Table","rows":[{..}],"units":{col:unit}} -> astropy Table
  {"__type__":"Unit","unit":"m/s"}                   -> Unit
  {"__call__":"pkg.mod.func","args":[],"kwargs":{},"self":<spec>} -> call whitelisted callable
  {"__handle__":"h123"}                              -> server-side object from earlier call
Outbound (encode): inverse, unknown objects become {"__type__":"object","handle":..,"repr":..}.
"""
import math, numbers, collections
import numpy as np

HANDLES = collections.OrderedDict()
MAX_HANDLES = 256
ALLOWED_PREFIXES = ("numpy", "astropy", "scipy.ndimage")  # extended per SDK
_counter = [0]


def put_handle(obj):
    _counter[0] += 1
    hid = f"h{_counter[0]}"
    HANDLES[hid] = obj
    while len(HANDLES) > MAX_HANDLES:
        HANDLES.popitem(last=False)
    return hid


def _resolve_path(path):
    import importlib
    if not path.startswith(ALLOWED_PREFIXES):
        raise ValueError(f"__call__ target not allowed: {path}")
    parts = path.split(".")
    if any(p.startswith("_") for p in parts):
        raise ValueError("private names not allowed")
    mod = None
    i = len(parts)
    while i > 0:
        try:
            mod = importlib.import_module(".".join(parts[:i]))
            break
        except ImportError:
            i -= 1
    if mod is None:
        raise ValueError(f"cannot import {path}")
    o = mod
    for p in parts[i:]:
        o = getattr(o, p)
    return o


def decode(x):
    import astropy.units as u
    from astropy.coordinates import SkyCoord
    from astropy.time import Time
    from astropy.table import Table, QTable
    if isinstance(x, list):
        return [decode(i) for i in x]
    if not isinstance(x, dict):
        return x
    if "__handle__" in x:
        return HANDLES[x["__handle__"]]
    if "__call__" in x:
        f = _resolve_path(x["__call__"])
        a = [decode(i) for i in x.get("args", [])]
        k = {kk: decode(v) for kk, v in x.get("kwargs", {}).items()}
        if "self" in x:
            return getattr(decode(x["self"]), x["__call__"].split(".")[-1])(*a, **k)
        return f(*a, **k)
    t = x.get("__type__")
    if t == "Time":
        v = decode(x["value"])
        return Time(v, format=x.get("format"), scale=x.get("scale", "utc"))
    if t == "ndarray":
        return np.array(decode(x["data"]), dtype=x.get("dtype"))
    if t == "Table":
        rows = x.get("rows", [])
        tb = Table(rows=[tuple(r.values()) for r in rows], names=list(rows[0].keys())) if rows else Table()
        for c, un in (x.get("units") or {}).items():
            tb[c].unit = un
        return tb
    if t == "slice":
        return slice(x.get("start"), x.get("stop"), x.get("step"))
    if t == "tuple":
        return tuple(decode(i) for i in x["items"])
    if t == "Unit":
        return u.Unit(x["unit"])
    if t == "SkyCoord" or (("ra" in x and "dec" in x) or ("l" in x and "b" in x)) and set(x) <= {
            "ra", "dec", "l", "b", "unit", "frame", "distance", "distance_unit", "obstime", "__type__"}:
        unit = x.get("unit", "deg")
        kw = {"frame": x.get("frame", "galactic" if "l" in x else "icrs"), "unit": unit}
        if "distance" in x:
            kw["distance"] = x["distance"] * u.Unit(x.get("distance_unit", "pc"))
        if "obstime" in x:
            kw["obstime"] = Time(x["obstime"])
        if "l" in x:
            return SkyCoord(l=decode(x["l"]), b=decode(x["b"]), **kw)
        return SkyCoord(ra=decode(x["ra"]), dec=decode(x["dec"]), **kw)
    if set(x) == {"value", "unit"}:
        return u.Quantity(decode(x["value"]), x["unit"])
    return {k: decode(v) for k, v in x.items()}


def _num(v):
    if isinstance(v, float) and not math.isfinite(v):
        return None
    return v


def encode(o, depth=0):
    import astropy.units as u
    from astropy.coordinates import SkyCoord, BaseCoordinateFrame, Angle
    from astropy.time import Time, TimeDelta
    from astropy.table import Table
    if o is None or isinstance(o, (bool, str)):
        return o
    if isinstance(o, (int,)) and not isinstance(o, bool):
        return o
    if isinstance(o, (float, np.floating)):
        return _num(float(o))
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, complex) or isinstance(o, np.complexfloating):
        return {"real": float(o.real), "imag": float(o.imag)}
    if isinstance(o, bytes):
        return o.decode("utf-8", "replace")
    if depth > 6:
        return {"__type__": "object", "class": type(o).__name__, "repr": repr(o)[:300]}
    if isinstance(o, (SkyCoord, BaseCoordinateFrame)):
        sph = o.spherical
        d = {"__type__": "SkyCoord", "frame": o.frame.name if isinstance(o, SkyCoord) else o.name,
             "lon_deg": encode(sph.lon.deg), "lat_deg": encode(sph.lat.deg)}
        try:
            if o.distance.unit != u.dimensionless_unscaled:
                d["distance"] = encode(o.distance)
        except Exception:
            pass
        return d
    if isinstance(o, Time):
        if o.isscalar:
            return {"__type__": "Time", "iso": o.iso, "jd": float(o.jd), "scale": o.scale}
        return {"__type__": "Time", "iso": [str(i) for i in o.iso.ravel()[:1000]], "jd": o.jd.ravel()[:1000].tolist(), "shape": list(o.shape), "scale": o.scale}
    if isinstance(o, u.UnitBase):
        return {"__type__": "Unit", "unit": str(o)}
    if isinstance(o, u.Quantity):
        v = o.value
        return {"value": encode(v, depth + 1) if np.ndim(v) else _num(float(v)) if np.isrealobj(v) else encode(v), "unit": str(o.unit)}
    if isinstance(o, Table):
        n = len(o)
        rows = []
        for r in o[:500]:
            rows.append({c: encode(r[c], depth + 1) for c in o.colnames})
        return {"__type__": "Table", "n_rows": n, "columns": o.colnames, "rows": rows,
                "units": {c: str(o[c].unit) for c in o.colnames if getattr(o[c], "unit", None) is not None}}
    if isinstance(o, np.ma.MaskedArray):
        o = o.filled(np.nan) if o.dtype.kind == "f" else o.filled(0)
    if isinstance(o, np.ndarray):
        if o.size > 20000:
            return {"__type__": "ndarray", "shape": list(o.shape), "dtype": str(o.dtype), "note": "too large; summary only",
                    "min": _num(float(np.nanmin(o))) if o.dtype.kind in "fiu" else None,
                    "max": _num(float(np.nanmax(o))) if o.dtype.kind in "fiu" else None,
                    "mean": _num(float(np.nanmean(o))) if o.dtype.kind in "fiu" else None}
        if o.dtype.names:
            return {n: encode(o[n], depth + 1) for n in o.dtype.names}
        if o.dtype.kind in "SUO":
            return [encode(i, depth + 1) for i in o.tolist()]
        return encode_list(o.tolist())
    if isinstance(o, dict):
        return {str(k): encode(v, depth + 1) for k, v in list(o.items())[:500]}
    if isinstance(o, (list, tuple, set, frozenset)):
        return [encode(v, depth + 1) for v in list(o)[:500]]
    if isinstance(o, numbers.Number):
        return _num(float(o))
    if hasattr(o, "__iter__") and type(o).__name__ in ("generator", "map", "zip", "dict_keys", "dict_values", "range"):
        return [encode(v, depth + 1) for v in list(o)[:500]]
    hid = put_handle(o)
    d = {"__type__": "object", "class": f"{type(o).__module__}.{type(o).__name__}", "handle": hid, "repr": repr(o)[:400]}
    return d


def encode_list(l):
    if isinstance(l, list):
        return [encode_list(i) for i in l]
    return _num(l)
