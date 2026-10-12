import importlib, inspect, signal, resource, json, re, traceback, threading
from . import codec

class Timeout(Exception):
    pass

def _alarm(signum, frame):
    raise Timeout("调用超时")

def resolve_target(path):
    parts = path.split(".")
    for i in range(len(parts), 0, -1):
        try:
            m = importlib.import_module(".".join(parts[:i]))
            break
        except Exception:
            continue
    else:
        raise ImportError(path)
    o = m
    owner = None
    for p in parts[i:]:
        owner = o
        try:
            o = getattr(o, p)
        except AttributeError:
            if inspect.isclass(owner):  # dynamic instance-level attribute (e.g. SkyCoord.separation)
                return None, owner
            raise
    return o, owner

def invoke(target, arguments, timeout=30):
    """Call target (dotted path) with decoded arguments. Methods require `_self`."""
    args = dict(arguments or {})
    self_spec = args.pop("_self", None)
    pos = args.pop("_args", None)
    fn, owner = resolve_target(target)
    dec = {k: codec.decode(v) for k, v in args.items()}
    dpos = [codec.decode(v) for v in (pos or [])]
    is_method = False
    if owner is not None and inspect.isclass(owner):
        st = inspect.getattr_static(owner, target.split(".")[-1], None)
        if fn is None or (not isinstance(st, (classmethod, staticmethod)) and callable(fn) and not inspect.isclass(fn)):
            is_method = True
    if is_method:
        if self_spec is None:
            raise ValueError(f"方法 {target} 需要 _self（{owner.__name__} 实例）")
        obj = codec.decode(self_spec)
        fn = getattr(obj, target.split(".")[-1])
    if timeout:
        signal.signal(signal.SIGALRM, _alarm)
        signal.setitimer(signal.ITIMER_REAL, timeout)
    try:
        res = fn(*dpos, **dec) if callable(fn) else fn
    finally:
        if timeout:
            signal.setitimer(signal.ITIMER_REAL, 0)
    return res
