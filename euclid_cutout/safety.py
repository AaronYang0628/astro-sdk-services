"""Path sandbox for the unauthenticated public service.

Tools only read files inside: EUCLID_CACHE_DIR (downloads from fetch_fits), EUCLID_OUTPUT_DIR
(cutouts/previews), EUCLID_INPUT_ROOTS (operator-allowlisted input dirs, e.g. a read-only mount of
021 project storage; default /home/scientist when unset, "" disables), EUCLID_MER_ROOT / EUCLID_TILE_INDEX (server-configured local
MER data, if set) and the bundled mock fixtures (fixtures/euclid_mock).
Writes only go inside EUCLID_OUTPUT_DIR.
Symlinks are resolved before the check, so links pointing outside are rejected.
"""
from __future__ import annotations
import os, re
from pathlib import Path
from urllib.parse import unquote, urlsplit

FIXTURES = (Path(__file__).resolve().parent.parent / "fixtures" / "euclid_mock")


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


DEFAULT_INPUT_ROOTS = "/home/scientist"  # 021 project pods' storage path (mount it read-only at the same path)


def _input_roots_raw() -> str:
    """EUCLID_INPUT_ROOTS; unset => DEFAULT_INPUT_ROOTS, explicitly set to "" => local inputs disabled."""
    raw = os.environ.get("EUCLID_INPUT_ROOTS")
    return DEFAULT_INPUT_ROOTS if raw is None else raw.strip()


def input_roots() -> list[Path]:
    """EUCLID_INPUT_ROOTS: ':' or ',' separated absolute dirs. Unset = /home/scientist (default);
    set to "" = no local inputs. Roots need not exist (a missing root just yields "file not found")."""
    out = []
    for part in re.split(r"[:,]", _input_roots_raw()):
        part = part.strip()
        if part and os.path.isabs(part):
            out.append(Path(part).resolve())
    return out


def _roots_hint() -> str:
    roots = input_roots()
    if roots:
        return ("allowed input roots (EUCLID_INPUT_ROOTS): " + ", ".join(str(r) for r in roots)
                + "; e.g. /home/scientist/project<id>/Data/<file>.fits. Alternatively pass an http(s) URL")
    return 'local input files are disabled on this server (EUCLID_INPUT_ROOTS=""); pass an http(s) URL instead'


def strip_file_scheme(raw: str) -> str:
    if raw.lower().startswith("file://"):
        u = urlsplit(raw)
        if u.netloc not in ("", "localhost"):
            raise ValueError("file:// URLs must refer to a local path (file:///abs/path)")
        return unquote(u.path)
    return raw


def resolve_input(raw: str) -> Path:
    """Local input file (absolute path or file://) that must lie inside EUCLID_INPUT_ROOTS."""
    raw = strip_file_scheme(raw.strip())
    roots = input_roots()
    if not roots:
        raise ValueError("local paths are not accepted: " + _roots_hint())
    if not os.path.isabs(raw):
        raise ValueError(f"local input must be an absolute path; {_roots_hint()}")
    p = Path(raw).resolve()  # resolves symlinks and '..'
    if not any(_inside(p, r) for r in roots):
        raise PermissionError(f"path not allowed (outside the input roots): {raw}; {_roots_hint()}")
    if not p.is_file():
        raise FileNotFoundError(f"file not found: {raw} (check the project file path; {_roots_hint()})")
    return p


def read_roots() -> list[Path]:
    from .config import cache_dir, default_output_dir
    roots = [cache_dir(), default_output_dir(), FIXTURES] + input_roots()
    if _env("EUCLID_MER_ROOT"):
        roots.append(Path(_env("EUCLID_MER_ROOT")))
    if _env("EUCLID_TILE_INDEX"):
        roots.append(Path(_env("EUCLID_TILE_INDEX")))
    return [r.expanduser().resolve() for r in roots]


def _inside(p: Path, root: Path) -> bool:
    return p == root or root in p.parents


def check_read(path: str | os.PathLike) -> Path:
    """Resolve `path` and require it to be an existing file inside an allowed root."""
    raw = str(path or "").strip()
    if not raw:
        raise ValueError("path is required (use the `path` returned by euclid_fetch_fits)")
    raw = strip_file_scheme(raw)
    if "://" in raw:
        raise ValueError("this tool takes the `path` returned by euclid_fetch_fits, not a URL; call euclid_fetch_fits first")
    p = Path(raw).expanduser().resolve()
    if not any(_inside(p, r) for r in read_roots()):
        raise PermissionError(
            f"path not allowed: {raw}. Readable: files under EUCLID_INPUT_ROOTS, files downloaded by euclid_fetch_fits "
            f"or produced by cutout/preview tools; {_roots_hint()} (to euclid_fetch_fits)"
        )
    if not p.is_file():
        raise FileNotFoundError(f"file not found: {raw}")
    return p


def check_write(path: str | os.PathLike) -> Path:
    """Require an output path inside EUCLID_OUTPUT_DIR."""
    from .config import default_output_dir
    root = default_output_dir().resolve()
    p = Path(str(path)).expanduser()
    if not p.is_absolute():
        p = root / p
    p = p.resolve()
    if not _inside(p, root) or p == root:
        raise PermissionError(f"output path must be inside EUCLID_OUTPUT_DIR ({root}); omit it to use the default")
    return p


def check_under(path: str | os.PathLike, root: Path, what: str) -> Path:
    p = Path(str(path)).expanduser().resolve()
    r = root.expanduser().resolve()
    if not _inside(p, r):
        raise PermissionError(f"{what} must be inside {r}")
    return p
