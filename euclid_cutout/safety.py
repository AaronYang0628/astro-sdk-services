"""Path sandbox for the unauthenticated public service.

Tools only read files inside: EUCLID_CACHE_DIR (downloads from fetch_fits), EUCLID_OUTPUT_DIR
(cutouts/previews), EUCLID_INPUT_ROOTS (operator-allowlisted input dirs, e.g. a read-only mount of
021 project storage; default /home/scientist when unset, "" disables), EUCLID_MER_ROOT / EUCLID_TILE_INDEX (server-configured local
MER data, if set) and the bundled mock fixtures (fixtures/euclid_mock).
Writes go inside EUCLID_OUTPUT_DIR (defaults) and, when a tool gets an explicit output_path/output_dir,
inside EUCLID_WRITE_ROOTS (default /home/scientist when unset, "" disables) — see resolve_output().
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
    roots = [cache_dir(), default_output_dir(), FIXTURES] + input_roots() + write_roots()
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


# ---------------------------------------------------------------------------------------------
# Explicit output paths (output_path / output_dir): EUCLID_OUTPUT_DIR + EUCLID_WRITE_ROOTS
# ---------------------------------------------------------------------------------------------
DEFAULT_WRITE_ROOTS = "/home/scientist"  # 021 project storage (must be mounted READ-WRITE for writes to work)
OUTPUT_EXTS = (".fits.gz", ".fits", ".fit", ".png", ".jpg", ".jpeg")
FITS_EXTS = (".fits.gz", ".fits", ".fit")
IMAGE_EXTS = (".png", ".jpg", ".jpeg")
_PROJECT_RE = re.compile(r"^project[^/]*$")


def _write_roots_raw() -> str:
    raw = os.environ.get("EUCLID_WRITE_ROOTS")
    return DEFAULT_WRITE_ROOTS if raw is None else raw.strip()


def write_roots() -> list[Path]:
    """EUCLID_WRITE_ROOTS: ':' or ',' separated absolute dirs. Unset = /home/scientist; "" = disabled.
    EUCLID_OUTPUT_DIR is always writable in addition to these."""
    out = []
    for part in re.split(r"[:,]", _write_roots_raw()):
        part = part.strip()
        if part and os.path.isabs(part):
            out.append(Path(os.path.realpath(part)))
    return out


_NO_WRITE_HINT = "Fix: omit output_path; use image_base64 (euclid_write_preview) and save it from your own environment."


def _diagnose_not_writable(raw: str, cause: BaseException | None = None) -> str:
    """Say WHY a write failed: write root absent (= not mounted), read-only filesystem, or no permission for this uid."""
    import errno
    p = Path(os.path.abspath(str(raw)))
    root = None
    for r in write_roots():
        # compare lexically and by realpath (write_roots() are realpaths)
        if _inside(p, r) or _inside(Path(os.path.realpath(_nearest_existing(p))) / p.relative_to(_nearest_existing(p)), r):
            root = r
            break
    if root is None:
        root = write_roots()[0] if write_roots() else None
    if root is not None and not root.is_dir():
        return (f"write root {root} does not exist in the MCP container, i.e. project storage is not mounted "
                f"(needs a read-write mount at {root})")
    anc = _nearest_existing(p)
    ro = isinstance(cause, OSError) and getattr(cause, "errno", None) == errno.EROFS
    if not ro:
        try:
            ro = bool(os.statvfs(anc).f_flag & os.ST_RDONLY)
        except OSError:
            pass
    if ro:
        return (f"{anc} is on a read-only filesystem (project storage must be mounted read-write at "
                f"{root or '/home/scientist'})")
    try:
        st = os.stat(anc)
        owner = f"; {anc} is owned by uid={st.st_uid} gid={st.st_gid} mode={oct(st.st_mode & 0o7777)}"
    except OSError:
        owner = ""
    return (f"no write permission for the MCP server process (uid={os.getuid()} gid={os.getgid()}) on {anc}{owner} "
            f"(project storage must be mounted read-write and writable by this uid; see DEPLOY.md securityContext)")


def _not_writable(raw: str, cause: BaseException | None = None) -> PermissionError:
    return PermissionError(f"output_path not writable on MCP server: {raw} - {_diagnose_not_writable(raw, cause)}. {_NO_WRITE_HINT}")


def _ext(name: str) -> str:
    low = name.lower()
    for e in OUTPUT_EXTS:
        if low.endswith(e):
            return e
    return ""


def _write_roots_hint() -> str:
    roots = write_roots()
    if roots:
        return ("allowed output roots (EUCLID_WRITE_ROOTS): " + ", ".join(str(r) for r in roots)
                + "; e.g. /home/scientist/project<id>/ResearchSpace/<name>.png|.fits, or omit output_path")
    return 'external output paths are disabled on this server (EUCLID_WRITE_ROOTS=""); omit output_path'


def _nearest_existing(p: Path) -> Path:
    q = p
    while not os.path.lexists(q):
        if q.parent == q:
            break
        q = q.parent
    return q


def _resolve_target(raw: str) -> Path:
    """Absolute realpath of `raw`, resolving the deepest existing ancestor (so symlinked parents of a
    not-yet-existing file are followed) and appending the remaining, not-yet-existing components."""
    p = Path(raw)
    anc = _nearest_existing(p)
    rest = p.relative_to(anc) if anc != p else Path()
    return Path(os.path.realpath(anc)) / rest


def _pick_root(target: Path) -> tuple[Path, bool]:
    """(root, is_output_dir) containing target, or raise."""
    from .config import default_output_dir
    out_root = Path(os.path.realpath(default_output_dir()))
    if _inside(target, out_root):
        return out_root, True
    for r in write_roots():
        if _inside(target, r):
            return r, False
    raise PermissionError(f"output path not allowed (outside the output roots): {target}; {_write_roots_hint()}")


def resolve_output_dir(raw: str, *, create: bool = True) -> Path:
    """Validate an explicit output DIRECTORY (absolute, or relative to EUCLID_OUTPUT_DIR)."""
    from .config import default_output_dir
    raw = strip_file_scheme(str(raw or "").strip())
    if not raw:
        raise ValueError("output directory is empty")
    if ".." in Path(raw).parts:
        raise PermissionError(f"'..' is not allowed in output paths: {raw}")
    if not os.path.isabs(raw):
        raw = str(default_output_dir() / raw)
    target = _resolve_target(raw)
    root, is_out = _pick_root(target)
    if target == root and not is_out:
        raise PermissionError(f"output must go below a project folder, not the root itself: {raw}; {_write_roots_hint()}")
    if not is_out:
        if not root.is_dir():
            raise _not_writable(raw)
        anc = Path(os.path.realpath(_nearest_existing(target)))
        if anc == root and target != root:
            # only create directories below an EXISTING project folder (e.g. /home/scientist/project<id>/)
            raise PermissionError(
                f"output path must be inside an existing project folder under {root} "
                f"(e.g. {root}/project<id>/ResearchSpace/): {raw}"
            )
        if not anc.is_dir():
            raise PermissionError(f"output path parent is not a directory: {anc}")
        if not os.access(anc, os.W_OK | os.X_OK):
            raise _not_writable(raw)
    if create:
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            if is_out:
                raise
            raise _not_writable(raw, e) from e
        # re-check after creation (race / symlink swapped in)
        real = Path(os.path.realpath(target))
        if not _inside(real, root):
            raise PermissionError(f"output path escapes the output roots: {raw}")
        if not is_out and not os.access(real, os.W_OK | os.X_OK):
            raise _not_writable(raw)
        return real
    return target


def resolve_output(raw: str, default_name: str, allowed_exts=OUTPUT_EXTS) -> Path:
    """Validate an explicit output_path and return the target FILE path (not yet suffixed).

    raw: absolute file path, or a directory (ends with '/' or is an existing dir) -> default_name inside it;
    relative paths are relative to EUCLID_OUTPUT_DIR (backward compatible).
    Allowed under EUCLID_OUTPUT_DIR or EUCLID_WRITE_ROOTS; '..' and symlink escapes rejected;
    extensions limited to allowed_exts. Missing parent dirs are created only below an existing project folder."""
    from .config import default_output_dir
    s = strip_file_scheme(str(raw or "").strip())
    if not s:
        raise ValueError("output_path is empty")
    if "://" in s:
        raise ValueError("output_path must be a server file path (e.g. /home/scientist/project<id>/ResearchSpace/x.png), not a URL")
    if ".." in Path(s).parts:
        raise PermissionError(f"'..' is not allowed in output_path: {raw}")
    absolute = s if os.path.isabs(s) else str(default_output_dir() / s)
    is_dir = s.endswith("/") or os.path.isdir(absolute)
    if is_dir:
        d = resolve_output_dir(absolute)
        name = default_name
    else:
        p = Path(absolute)
        name = p.name
        if not _ext(name) or _ext(name) not in allowed_exts:
            raise ValueError(f"output_path extension not allowed: {name} (allowed: {', '.join(allowed_exts)})")
        d = resolve_output_dir(str(p.parent))
    if not _ext(name) or _ext(name) not in allowed_exts:
        raise ValueError(f"output file extension not allowed: {name} (allowed: {', '.join(allowed_exts)})")
    target = d / name
    if os.path.lexists(target):
        real = Path(os.path.realpath(target))
        root, _ = _pick_root(real)  # symlink pointing outside -> PermissionError
        if os.path.isdir(real):
            raise IsADirectoryError(f"output_path is a directory: {target}")
    return target


def _suffixed(target: Path, n: int) -> Path:
    e = _ext(target.name) or target.suffix
    stem = target.name[: len(target.name) - len(e)] if e else target.name
    return target.with_name(f"{stem}_{n}{e}")


def atomic_write(target: Path, writer, *, overwrite: bool = False, external: bool = True) -> Path:
    """Write via writer(tmp_path) to a temp file in target's directory, chmod 0644, then publish.

    overwrite=False: never clobber an existing file; pick target, target_1, target_2, ... (race-safe via
    os.link where supported). Returns the actual written path."""
    import uuid
    d = target.parent
    tmp = d / f".tmp-{uuid.uuid4().hex[:12]}-{target.name}"  # keeps the extension (astropy .gz detection)
    try:
        writer(tmp)
        os.chmod(tmp, 0o644)
    except PermissionError as e:
        _cleanup(tmp)
        if external:
            raise _not_writable(str(target), e) from e
        raise
    except OSError as e:
        _cleanup(tmp)
        import errno
        if external and e.errno in (errno.EROFS, errno.EACCES, errno.EPERM):
            raise _not_writable(str(target), e) from e
        raise
    except BaseException:
        _cleanup(tmp)
        raise
    try:
        if overwrite:
            os.replace(tmp, target)
            return target
        for n in range(0, 1000):
            cand = target if n == 0 else _suffixed(target, n)
            if os.path.lexists(cand):
                continue
            try:
                os.link(tmp, cand)  # atomic, fails if cand appeared meanwhile
                _cleanup(tmp)
                return cand
            except FileExistsError:
                continue
            except OSError:  # filesystem without hard links (some FUSE/object mounts)
                if os.path.lexists(cand):
                    continue
                os.replace(tmp, cand)
                return cand
        raise FileExistsError(f"too many existing files like {target}")
    finally:
        _cleanup(tmp)


def _cleanup(p: Path) -> None:
    try:
        os.unlink(p)
    except OSError:
        pass


def describe_output(path: Path) -> dict:
    """saved_path plus, under <write root>/project<id>/..., project_dir + project_relpath (e.g. ResearchSpace/x.png)."""
    p = Path(os.path.realpath(path))
    info = {"saved_path": str(p)}
    for r in write_roots():
        if _inside(p, r) and p != r:
            parts = p.relative_to(r).parts
            if len(parts) >= 2 and _PROJECT_RE.match(parts[0]):
                info["project_dir"] = str(r / parts[0])
                info["project_relpath"] = "/".join(parts[1:])
            break
    return info
