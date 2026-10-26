"""Download an http(s) FITS URL into EUCLID_CACHE_DIR (Range prefix / resume, presigned-URL safe).

Input is any http(s) URL: a public FITS link, or a temporary presigned object-storage URL
(e.g. the address 021 generates for an uploaded file: ?OSSAccessKeyId=..&Expires=..&Signature=..,
X-Amz-*, x-oss-* V4). Rules:
- the URL (incl. query string) is sent byte-for-byte as given (no re-encoding);
- no HEAD request (presigned GET URLs usually reject HEAD); size comes from Content-Range/Length;
- Range is used for max_bytes / resume; if the server ignores Range (200), we stream from 0 and stop;
- cache key / file names derive from host+path only; results and errors never contain the query
  string (signature) — it is shown as `?<redacted>`;
- FITS is detected by content (`SIMPLE  =` header card, or gzip magic), not by extension.
"""
from __future__ import annotations
import hashlib, re, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit, parse_qs
import requests

from .config import cache_dir

_URL_RE = re.compile(r"^https?://", re.I)
FITS_MAGIC = b"SIMPLE  ="
GZIP_MAGIC = b"\x1f\x8b"
_FITS_EXT = (".fits", ".fit", ".fts", ".fz", ".fits.gz", ".fit.gz", ".fts.gz")


class FetchError(RuntimeError):
    pass


def is_url(s: str) -> bool:
    return bool(_URL_RE.match((s or "").strip()))


def redact(url: str) -> str:
    """scheme://host/path with any query/fragment replaced by `?<redacted>`."""
    try:
        u = urlsplit(url)
        return f"{u.scheme}://{u.netloc.rsplit('@', 1)[-1]}{u.path}" + ("?<redacted>" if u.query or u.fragment else "")
    except Exception:
        return "<url>"


def _key(url: str) -> tuple[str, str]:
    u = urlsplit(url)
    host_path = f"{u.netloc.rsplit('@', 1)[-1].lower()}{u.path}"
    name = Path(u.path).name or "download"
    name = re.sub(r"[^\w.\-]+", "_", name)[:120]
    return hashlib.sha256(host_path.encode("utf-8")).hexdigest()[:24], name


def cache_path_for(url: str) -> Path:
    digest, name = _key(url)
    if not name.lower().endswith(_FITS_EXT):
        name += ".fits"
    return cache_dir() / f"{digest}_{name}"


def _expiry_hint(url: str) -> Optional[str]:
    """If the presigned URL says it has expired, return a description."""
    q = {k.lower(): v[0] for k, v in parse_qs(urlsplit(url).query, keep_blank_values=True).items()}
    now = time.time()
    try:
        if "expires" in q and q["expires"].isdigit() and int(q["expires"]) < now:  # OSS V1 / S3 V2
            return "expired"
        for d, e in (("x-amz-date", "x-amz-expires"), ("x-oss-date", "x-oss-expires")):
            if d in q and e in q:
                t0 = datetime.strptime(q[d], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).timestamp()
                if t0 + int(q[e]) < now:
                    return "expired"
    except Exception:
        pass
    return None


def _get(url: str, headers: dict, timeout: int) -> requests.Response:
    s = requests.Session()
    req = requests.Request("GET", url, headers=headers).prepare()
    req.url = url  # keep the exact (signed) query string, no requoting
    env = s.merge_environment_settings(url, {}, True, None, None)  # proxies / CA bundle like requests.get
    env["stream"] = True
    return s.send(req, timeout=timeout, allow_redirects=True, **env)


def _check_status(r: requests.Response, url: str) -> None:
    if r.status_code in (200, 206, 416):
        return
    body = ""
    try:
        body = r.raw.read(2048, decode_content=True).decode("utf-8", "replace")
    except Exception:
        pass
    safe = redact(url)
    expired = _expiry_hint(url) or (
        r.status_code in (400, 401, 403) and re.search(r"expired|RequestExpired|AccessDenied.*Expire", body, re.I | re.S)
    )
    if expired:
        raise FetchError(
            f"HTTP {r.status_code}: the temporary (presigned) URL has expired — please get a fresh download URL "
            f"for the file (e.g. re-share/re-upload it in 021) and call euclid_fetch_fits again. url={safe}"
        )
    if r.status_code in (401, 403):
        raise FetchError(f"HTTP {r.status_code}: access denied — the URL must be publicly readable or a valid "
                         f"presigned URL (pass the complete URL including its query string). url={safe}")
    raise FetchError(f"HTTP {r.status_code} while downloading url={safe}")


def _total_from(r: requests.Response) -> Optional[int]:
    cr = r.headers.get("Content-Range") or ""
    m = re.match(r"bytes\s+(\d+)-(\d+)/(\d+|\*)", cr)
    if m and m.group(3).isdigit():
        return int(m.group(3))
    m = re.match(r"bytes\s+\*/(\d+)", cr)
    if m:
        return int(m.group(1))
    if r.status_code == 200 and (r.headers.get("Content-Length") or "").isdigit() and not r.headers.get("Content-Encoding"):
        return int(r.headers["Content-Length"])
    return None


def _sniff(path: Path) -> str:
    with open(path, "rb") as f:
        head = f.read(16)
    if head.startswith(FITS_MAGIC):
        return "fits"
    if head.startswith(GZIP_MAGIC):
        return "gzip"
    return "unknown"


def fetch_fits(
    url: Optional[str] = None,
    force: bool = False,
    max_bytes: Optional[int] = None,
    timeout: int = 600,
    url_or_path: Optional[str] = None,  # deprecated alias of `url` (local paths are no longer accepted)
) -> dict:
    """Download an http(s) FITS URL (public or presigned/temporary) into EUCLID_CACHE_DIR.

    max_bytes: fetch only the first N bytes (multi-GB multi-extension files: early HDUs suffice).
    Returns the server cache `path` to pass to the other euclid_* tools.
    """
    raw = (url or url_or_path or "").strip()
    if not raw:
        raise ValueError("url is required: an http(s) FITS URL (public, or the temporary URL 021 gives for an uploaded file)")
    if not is_url(raw):
        raise ValueError("only http(s):// URLs are accepted (public FITS link or a presigned/temporary OSS/S3 URL); "
                         "local paths and other schemes are not allowed")
    safe = redact(raw)
    if max_bytes is not None:
        max_bytes = int(max_bytes)
        if max_bytes < 2880:
            raise ValueError("max_bytes must be >= 2880 (one FITS block)")

    dest = cache_path_for(raw)
    dest.parent.mkdir(parents=True, exist_ok=True)
    meta_path = Path(str(dest) + ".meta")
    meta = {}
    if meta_path.is_file():
        try:
            import json
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    remote_size = meta.get("remote_size_bytes")
    if force and dest.is_file():
        dest.unlink()
    local = dest.stat().st_size if dest.is_file() else 0

    def _result(from_cache, elapsed=None, range_honored=None):
        size = dest.stat().st_size
        complete = remote_size is not None and size >= remote_size
        res = {
            "ok": True, "source": safe, "path": str(dest), "cached": True,
            "complete": bool(complete), "prefix_ok": bool(complete or (max_bytes is not None and size >= max_bytes)),
            "size_bytes": size, "remote_size_bytes": remote_size, "max_bytes": max_bytes,
            "from_cache": from_cache, "format": _sniff(dest),
        }
        if elapsed is not None:
            res["elapsed_s"] = round(elapsed, 3)
        if range_honored is not None:
            res["range_honored"] = range_honored
        return res

    target = max_bytes if max_bytes is not None else None
    if remote_size is not None and target is not None:
        target = min(target, remote_size)
    if local > 0 and ((remote_size is not None and local >= remote_size) or (target is not None and local >= target)):
        return _result(True)

    headers = {"Accept-Encoding": "identity"}
    if local > 0:
        headers["Range"] = f"bytes={local}-" + (str(target - 1) if target else "")
    elif target is not None:
        headers["Range"] = f"bytes=0-{target - 1}"

    t0 = time.time()
    range_honored = None
    try:
        with _get(raw, headers, timeout) as r:
            _check_status(r, raw)
            if r.status_code == 416:  # already have everything
                remote_size = _total_from(r) or local
            else:
                range_honored = r.status_code == 206
                remote_size = _total_from(r) or remote_size
                mode = "ab" if (range_honored and local > 0) else "wb"  # 200 => server ignored Range: restart
                limit = target
                with open(dest, mode) as f:
                    for chunk in r.iter_content(chunk_size=1024 * 1024):
                        if not chunk:
                            continue
                        f.write(chunk)
                        if limit is not None and f.tell() >= limit:
                            break
                    if limit is not None and f.tell() > limit:
                        f.truncate(limit)
    except FetchError:
        raise
    except requests.RequestException as e:  # never echo the signed URL
        raise FetchError(f"download failed ({type(e).__name__}) url={safe}") from None

    kind = _sniff(dest)
    if kind == "unknown":
        dest.unlink(missing_ok=True)
        raise FetchError(f"downloaded content is not FITS (no 'SIMPLE  =' header card) url={safe}")
    import json
    meta_path.write_text(json.dumps({"source": safe, "remote_size_bytes": remote_size}), encoding="utf-8")
    res = _result(False, time.time() - t0, range_honored)
    if kind == "gzip" and max_bytes is not None and not res["complete"]:
        res["warning"] = "gzip-compressed FITS cannot be read from a prefix; fetch without max_bytes"
    return res
