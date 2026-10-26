"""Tiny threaded HTTP server emulating object storage for tests.

Routes (all serve `data` as application/octet-stream, no file extension needed):
  /signed/<name>   requires the exact presigned query string (byte-for-byte), else 403; honors Range (206)
  /norange/<name>  same signature check, but ignores Range (always 200 + full body)
  /expired/<name>  always 403 with an S3/OSS-style "Request has expired" XML body
  /notfits/<name>  returns 200 text/html
HEAD always returns 403 (like a presigned GET URL signed for GET only).
"""
from __future__ import annotations
import re, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SIG_QUERY = "OSSAccessKeyId=LTAIexampleKEY&Expires={exp}&Signature=ab%2Bcd%2Fef%3D"
DENIED = b"<?xml version='1.0'?><Error><Code>SignatureDoesNotMatch</Code><Message>denied</Message></Error>"
EXPIRED = b"<?xml version='1.0'?><Error><Code>AccessDenied</Code><Message>Request has expired.</Message></Error>"


def start(data: bytes):
    exp = int(time.time()) + 3600
    query = SIG_QUERY.format(exp=exp)
    seen = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/xml", extra=None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def do_HEAD(self):
            self.send_response(403); self.send_header("Content-Length", "0"); self.end_headers()

        def do_GET(self):
            path, _, q = self.path.partition("?")
            seen.append({"path": path, "query": q, "range": self.headers.get("Range")})
            kind = path.split("/")[1] if path.count("/") >= 2 else ""
            if kind == "expired":
                return self._send(403, EXPIRED)
            if kind == "notfits":
                return self._send(200, b"<html>login</html>", "text/html")
            if kind not in ("signed", "norange"):
                return self._send(404, b"no")
            if q != query:  # raw query must arrive unchanged (no re-encoding)
                return self._send(403, DENIED)
            rng = self.headers.get("Range")
            m = re.match(r"bytes=(\d+)-(\d*)$", rng or "")
            if kind == "signed" and m:
                a = int(m.group(1)); b = int(m.group(2)) if m.group(2) else len(data) - 1
                if a >= len(data):
                    return self._send(416, b"", extra={"Content-Range": f"bytes */{len(data)}"})
                b = min(b, len(data) - 1)
                return self._send(206, data[a:b + 1], "application/octet-stream",
                                  {"Content-Range": f"bytes {a}-{b}/{len(data)}", "Accept-Ranges": "bytes"})
            return self._send(200, data, "application/octet-stream")

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    return srv, base, query, seen
