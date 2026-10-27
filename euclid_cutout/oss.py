"""Optional result delivery through an Aliyun-OSS-compatible object store (presigned GET URLs).

For deployments where the MCP server has NO shared storage with the caller (e.g. 021): after a tool has written
its result file, the server uploads it to the bucket and returns a time-limited download URL. The caller saves it
into its own workspace with `curl -k -sS -o <path> '<url>'`.

Active only when ALL of EUCLID_OSS_ENDPOINT, EUCLID_OSS_BUCKET, EUCLID_OSS_ACCESS_KEY_ID and
EUCLID_OSS_ACCESS_KEY_SECRET are set; otherwise every function here is a no-op and tools behave exactly as before.

Env:
  EUCLID_OSS_ENDPOINT          e.g. https://oss-<region>.example.com  (scheme optional, default https)
  EUCLID_OSS_BUCKET            bucket name
  EUCLID_OSS_ACCESS_KEY_ID / EUCLID_OSS_ACCESS_KEY_SECRET
  EUCLID_OSS_PREFIX            key prefix (default "euclid-mcp/")
  EUCLID_OSS_URL_EXPIRES       presigned URL lifetime in seconds (default 604800 = 7 days; OSS v1 signatures allow more)
  EUCLID_OSS_VERIFY_TLS        default false (private endpoints often use a self-signed chain); true to verify
  EUCLID_OSS_CA_BUNDLE         optional CA bundle path; implies verification against it
Objects are keyed <prefix><yyyymmdd>/<uuid8>/<filename>. Signing is OSS v1 (HMAC-SHA1), which private OSS endpoints
accept even when v4 is not offered, and which has no 7-day cap on expiry.
"""
from __future__ import annotations
import datetime as _dt
import mimetypes
import os
import re
import uuid
from pathlib import Path
from typing import Optional

DEFAULT_PREFIX = "euclid-mcp/"
DEFAULT_EXPIRES = 7 * 24 * 3600
_TZ = _dt.timezone(_dt.timedelta(hours=8), "Asia/Shanghai")


def _e(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def oss_config() -> Optional[dict]:
    """Effective OSS settings, or None when not (fully) configured."""
    ep, bucket, kid, sec = (_e("EUCLID_OSS_ENDPOINT"), _e("EUCLID_OSS_BUCKET"),
                            _e("EUCLID_OSS_ACCESS_KEY_ID"), _e("EUCLID_OSS_ACCESS_KEY_SECRET"))
    if not (ep and bucket and kid and sec):
        return None
    if "://" not in ep:
        ep = "https://" + ep
    prefix = _e("EUCLID_OSS_PREFIX") or DEFAULT_PREFIX
    prefix = prefix.lstrip("/")
    if prefix and not prefix.endswith("/"):
        prefix += "/"
    try:
        expires = int(_e("EUCLID_OSS_URL_EXPIRES") or DEFAULT_EXPIRES)
    except ValueError:
        expires = DEFAULT_EXPIRES
    ca = _e("EUCLID_OSS_CA_BUNDLE")
    verify = ca if ca else (_e("EUCLID_OSS_VERIFY_TLS").lower() in ("1", "true", "yes", "on"))
    return {"endpoint": ep, "bucket": bucket, "key_id": kid, "secret": sec, "prefix": prefix,
            "expires": max(60, expires), "verify": verify}


def is_configured() -> bool:
    return oss_config() is not None


def _safe_name(name: str) -> str:
    n = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).name).strip("._") or "result"
    return n[:150]


def make_key(cfg: dict, filename: str, now: Optional[_dt.datetime] = None) -> str:
    now = now or _dt.datetime.now(_TZ)
    return f"{cfg['prefix']}{now.astimezone(_TZ):%Y%m%d}/{uuid.uuid4().hex[:8]}/{_safe_name(filename)}"


def _put_and_sign(cfg: dict, key: str, local_path: str, content_type: str, expires: int) -> str:
    """Upload local_path to cfg['bucket']/key and return a presigned GET URL (OSS v1 signature).
    Network boundary: tests replace this function."""
    import oss2
    import urllib3
    sess = oss2.Session()
    sess.session.verify = cfg["verify"]
    if cfg["verify"] is False:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    bucket = oss2.Bucket(oss2.Auth(cfg["key_id"], cfg["secret"]), cfg["endpoint"], cfg["bucket"], session=sess,
                         connect_timeout=15)
    with open(local_path, "rb") as f:
        bucket.put_object(key, f, headers={"Content-Type": content_type})
    return bucket.sign_url("GET", key, int(expires), slash_safe=True)


def _redact(msg: str, cfg: dict) -> str:
    for s in (cfg.get("secret"), cfg.get("key_id")):
        if s:
            msg = msg.replace(s, "***")
    msg = re.sub(r"(Signature|OSSAccessKeyId|Authorization)[=:]\s*[^&\s'\"]+", r"\1=***", msg)
    return msg


def upload_result(local_path: str, filename: Optional[str] = None, content_type: Optional[str] = None,
                  project_subdir: str = "euclid") -> dict:
    """Upload a result file and describe how to fetch it. Never raises.

    Returns {} when OSS is not configured; on success download_url, download_expires_at (ISO, Asia/Shanghai),
    download_expires_in_seconds, oss_key, size_bytes, download_hint, download_note; on failure upload_error
    (the caller keeps its local path fields)."""
    cfg = oss_config()
    if cfg is None:
        return {}
    try:
        p = Path(local_path)
        name = _safe_name(filename or p.name)
        ctype = content_type or mimetypes.guess_type(name)[0] or "application/octet-stream"
        key = make_key(cfg, name)
        size = p.stat().st_size
        url = _put_and_sign(cfg, key, str(p), ctype, cfg["expires"])
        exp = (_dt.datetime.now(_TZ) + _dt.timedelta(seconds=cfg["expires"])).replace(microsecond=0)
        k = "-k " if cfg["verify"] is False else ""
        return {
            "download_url": url,
            "download_expires_at": exp.isoformat(),
            "download_expires_in_seconds": cfg["expires"],
            "oss_key": key,
            "size_bytes": size,
            "download_hint": f"mkdir -p \"$PROJECT_DIR/ResearchSpace/{project_subdir}\" && "
                             f"curl {k}-sS -o \"$PROJECT_DIR/ResearchSpace/{project_subdir}/{name}\" '{url}'",
            "download_note": "Use GET (curl without -I/--head): HEAD requests return 403. Set PROJECT_DIR to your project "
                             "directory first (e.g. via pwd).",
        }
    except Exception as e:  # noqa: BLE001 - delivery must never fail the tool
        msg = _redact(f"{type(e).__name__}: {e}", cfg)
        return {"upload_error": msg[:400]}
