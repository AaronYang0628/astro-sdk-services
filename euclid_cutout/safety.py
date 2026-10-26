"""Path sandbox for the unauthenticated public service.

Tools only read files inside: EUCLID_CACHE_DIR (downloads from fetch_fits), EUCLID_OUTPUT_DIR
(cutouts/previews), EUCLID_MER_ROOT / EUCLID_TILE_INDEX (server-configured local MER data, if set)
and the bundled mock fixtures (fixtures/euclid_mock). Writes only go inside EUCLID_OUTPUT_DIR.
Symlinks are resolved before the check, so links pointing outside are rejected.
"""
from __future__ import annotations
import os
from pathlib import Path

FIXTURES = (Path(__file__).resolve().parent.parent / "fixtures" / "euclid_mock")


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def read_roots() -> list[Path]:
    from .config import cache_dir, default_output_dir
    roots = [cache_dir(), default_output_dir(), FIXTURES]
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
    if "://" in raw:
        raise ValueError("this tool takes the server cache `path` returned by euclid_fetch_fits, not a URL")
    p = Path(raw).expanduser().resolve()
    if not any(_inside(p, r) for r in read_roots()):
        raise PermissionError(
            "path not allowed: only files downloaded by euclid_fetch_fits (EUCLID_CACHE_DIR) or produced by "
            "cutout/preview tools (EUCLID_OUTPUT_DIR) can be read; call euclid_fetch_fits with an http(s) URL first"
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
