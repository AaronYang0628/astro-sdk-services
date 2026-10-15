"""FITS cache: local path passthrough or HTTPS download with resume."""
from __future__ import annotations
import hashlib, os, re, time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
import requests

from .config import cache_dir


_URL_RE = re.compile(r"^https?://", re.I)


def is_url(s: str) -> bool:
    return bool(_URL_RE.match((s or "").strip()))


def cache_path_for(url_or_path: str, suffix: str = "") -> Path:
    raw = (url_or_path or "").strip()
    if not is_url(raw):
        return Path(raw).expanduser().resolve()
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    name = Path(urlparse(raw).path).name or "download.fits"
    # keep readable name + hash to avoid collisions
    stem = re.sub(r"[^\w.\-]+", "_", name)[:120]
    return cache_dir() / f"{digest}_{stem}{suffix}"


def _head(url: str, timeout: int = 60) -> requests.Response:
    r = requests.head(url, allow_redirects=True, timeout=timeout)
    if r.status_code >= 400:
        # some mirrors dislike HEAD
        r = requests.get(url, allow_redirects=True, timeout=timeout, stream=True, headers={"Range": "bytes=0-0"})
    r.raise_for_status()
    return r


def fetch_fits(
    url_or_path: str,
    force: bool = False,
    max_bytes: Optional[int] = None,
    timeout: int = 600,
) -> dict:
    """Open local FITS path or download HTTPS FITS into EUCLID_CACHE_DIR.

    - Local path: returned as-is if it exists.
    - URL: resumed download (Accept-Ranges). If max_bytes is set, only the
      prefix is fetched (useful for multi-GB multi-extension mirrors when
      early HDUs suffice). Incomplete downloads set complete=False.
    """
    raw = (url_or_path or "").strip()
    if not raw:
        raise ValueError("url_or_path is required")

    if not is_url(raw):
        p = Path(raw).expanduser().resolve()
        if not p.is_file():
            raise FileNotFoundError(f"local FITS not found: {p}")
        return {
            "ok": True,
            "source": str(p),
            "path": str(p),
            "cached": False,
            "complete": True,
            "size_bytes": p.stat().st_size,
            "remote_size_bytes": None,
            "max_bytes": max_bytes,
            "from_cache": True,
        }

    dest = cache_path_for(raw)
    dest.parent.mkdir(parents=True, exist_ok=True)
    meta_path = Path(str(dest) + ".meta")

    remote_size = None
    accept_ranges = False
    try:
        h = _head(raw, timeout=min(60, timeout))
        remote_size = h.headers.get("Content-Length") or h.headers.get("Content-Range", "").split("/")[-1]
        remote_size = int(remote_size) if str(remote_size).isdigit() else None
        accept_ranges = "bytes" in (h.headers.get("Accept-Ranges") or "").lower() or h.status_code == 206
    except Exception:
        pass

    target_size = remote_size
    if max_bytes is not None:
        target_size = max_bytes if remote_size is None else min(max_bytes, remote_size)

    if dest.is_file() and not force:
        local = dest.stat().st_size
        if target_size is None or local >= target_size or (remote_size and local >= remote_size):
            complete = remote_size is not None and local >= remote_size and max_bytes is None
            if max_bytes is not None:
                complete = local >= (target_size or 0)
            elif remote_size is None:
                complete = local > 0
            else:
                complete = local >= remote_size
            if complete or (max_bytes is not None and local >= (target_size or 0)):
                return {
                    "ok": True,
                    "source": raw,
                    "path": str(dest),
                    "cached": True,
                    "complete": bool(complete and max_bytes is None) or (max_bytes is not None and local >= (target_size or 0) and (remote_size is None or local >= remote_size or max_bytes < remote_size)),
                    "size_bytes": local,
                    "remote_size_bytes": remote_size,
                    "max_bytes": max_bytes,
                    "from_cache": True,
                    "accept_ranges": accept_ranges,
                }

    # download / resume
    existing = dest.stat().st_size if dest.is_file() and not force else 0
    if force and dest.is_file():
        dest.unlink()
        existing = 0

    headers = {}
    mode = "wb"
    if existing > 0 and accept_ranges:
        if target_size is not None and existing >= target_size:
            pass  # nothing to do
        else:
            end = "" if target_size is None else str(target_size - 1)
            headers["Range"] = f"bytes={existing}-{end}" if end else f"bytes={existing}-"
            mode = "ab"
    elif target_size is not None:
        headers["Range"] = f"bytes=0-{target_size - 1}"

    t0 = time.time()
    with requests.get(raw, stream=True, headers=headers, timeout=timeout, allow_redirects=True) as r:
        r.raise_for_status()
        with open(dest, mode) as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                f.write(chunk)
                if target_size is not None and f.tell() >= target_size:
                    break

    local = dest.stat().st_size
    if max_bytes is not None:
        complete = remote_size is not None and local >= remote_size
        prefix_ok = local >= min(max_bytes, remote_size or max_bytes)
    else:
        complete = remote_size is None or local >= remote_size
        prefix_ok = complete

    meta_path.write_text(raw + "\n", encoding="utf-8")
    return {
        "ok": True,
        "source": raw,
        "path": str(dest),
        "cached": True,
        "complete": bool(complete),
        "prefix_ok": bool(prefix_ok),
        "size_bytes": local,
        "remote_size_bytes": remote_size,
        "max_bytes": max_bytes,
        "from_cache": False,
        "elapsed_s": round(time.time() - t0, 3),
        "accept_ranges": accept_ranges,
    }
