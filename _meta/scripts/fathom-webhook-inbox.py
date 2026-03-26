#!/usr/bin/env python3
"""
Fathom webhook listener — receives "new meeting content ready" webhooks from Fathom
and writes transcript + summary to _inbox as .txt files.

Usage:
    # From repo root (or set INBOX_DIR and optionally FATHOM_WEBHOOK_SECRET)
    python _meta/scripts/fathom-webhook-inbox.py

    # With env vars (optional)
    export INBOX_DIR="/path/to/S2/_inbox"
    export FATHOM_WEBHOOK_SECRET="whsec_..."   # from Fathom webhook settings (recommended in production)
    export PORT=8765
    python _meta/scripts/fathom-webhook-inbox.py

The server listens on 0.0.0.0:PORT (default 8765). For Fathom to reach it you need a
public URL: use ngrok (e.g. ngrok http 8765) or deploy to a server and point Fathom
at https://your-domain/webhook/fathom.
"""

import base64
import hmac
import hashlib
import json
import os
import re
import sys
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

# Defaults
DEFAULT_PORT = 8765
WEBHOOK_PATH = "/webhook/fathom"
INBOX_ENV = "INBOX_DIR"
SECRET_ENV = "FATHOM_WEBHOOK_SECRET"
PORT_ENV = "PORT"


def get_inbox_dir() -> Path:
    """Resolve _inbox directory (repo root / _inbox)."""
    env = os.environ.get(INBOX_ENV)
    if env:
        return Path(env).resolve()
    # Assume script lives in _meta/scripts; repo root is _meta/../..
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent.parent
    return repo_root / "_inbox"


def verify_fathom_webhook(secret: str, headers: dict, raw_body: bytes) -> bool:
    """
    Verify Fathom webhook using webhook-id, webhook-timestamp, webhook-signature.
    Secret is the full value (e.g. whsec_xxx); we use the part after whsec_ for HMAC.
    """
    try:
        webhook_id = headers.get("webhook-id", "")
        webhook_ts = headers.get("webhook-timestamp", "")
        webhook_sig = headers.get("webhook-signature", "")
        if not all([webhook_id, webhook_ts, webhook_sig]):
            return False
        # Replay: timestamp within 5 minutes
        ts = int(webhook_ts)
        now = int(datetime.now().timestamp())
        if abs(now - ts) > 300:
            return False
        # Signed content: id.timestamp.body
        signed = f"{webhook_id}.{webhook_ts}.{raw_body.decode('utf-8', errors='replace')}"
        # Secret: base64 decode the part after whsec_
        secret_b64 = secret.split("_", 1)[-1] if secret.startswith("whsec_") else secret
        secret_bytes = base64.b64decode(secret_b64)
        expected = base64.b64encode(
            hmac.new(secret_bytes, signed.encode("utf-8"), hashlib.sha256).digest()
        ).decode("ascii")
        # Header can be "v1,sig1 v1,sig2" — compare to expected
        for part in webhook_sig.split():
            sig = part.split(",", 1)[-1].strip()
            if hmac.compare_digest(expected, sig):
                return True
        return False
    except Exception:
        return False


def slug(s: str, max_len: int = 40) -> str:
    """Lowercase alphanumeric + hyphens, truncated."""
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:max_len] if s else "meeting"


def format_transcript(transcript: list) -> str:
    """Turn Fathom transcript array into readable text (Speaker: text)."""
    if not transcript:
        return ""
    lines = []
    for item in transcript:
        speaker = "Unknown"
        if isinstance(item.get("speaker"), dict):
            speaker = item["speaker"].get("display_name") or item["speaker"].get("matched_calendar_invitee_email") or "Unknown"
        text = item.get("text", "")
        ts = item.get("timestamp", "")
        if ts:
            lines.append(f"[{ts}] {speaker}: {text}")
        else:
            lines.append(f"{speaker}: {text}")
    return "\n".join(lines)


def build_content(payload: dict) -> str:
    """Build full .txt content: optional summary, then transcript."""
    parts = []
    title = payload.get("title") or payload.get("meeting_title") or "Meeting"
    created = payload.get("created_at") or payload.get("recording_start_time") or ""
    if created:
        try:
            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            parts.append(f"Date: {dt.strftime('%Y-%m-%d')}")
        except Exception:
            pass
    parts.append(f"Title: {title}")
    parts.append("")
    summary = payload.get("default_summary") or {}
    if isinstance(summary, dict) and summary.get("markdown_formatted"):
        parts.append(summary["markdown_formatted"].strip())
        parts.append("")
    transcript = payload.get("transcript") or []
    parts.append(format_transcript(transcript))
    return "\n".join(parts).strip() + "\n"


def suggest_filename(payload: dict) -> str:
    """Suggest filename: YYYY-MM-DD_title-slug.txt"""
    created = payload.get("created_at") or payload.get("recording_start_time") or ""
    try:
        dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        date_str = dt.strftime("%Y-%m-%d")
    except Exception:
        date_str = datetime.now().strftime("%Y-%m-%d")
    title = payload.get("meeting_title") or payload.get("title") or "meeting"
    return f"{date_str}_{slug(title)}.txt"


class FathomWebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if urlparse(self.path).path != WEBHOOK_PATH:
            self.send_response(404)
            self.end_headers()
            return
        raw_body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        secret = os.environ.get(SECRET_ENV)
        if secret and not verify_fathom_webhook(secret, dict(self.headers), raw_body):
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b"Unauthorized")
            return
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Invalid JSON")
            return
        inbox = get_inbox_dir()
        inbox.mkdir(parents=True, exist_ok=True)
        filename = suggest_filename(payload)
        filepath = inbox / filename
        # Avoid overwrite: append _1, _2, ...
        base = filepath.stem
        ext = filepath.suffix
        n = 0
        while filepath.exists():
            n += 1
            filepath = inbox / f"{base}_{n}{ext}"
        content = build_content(payload)
        filepath.write_text(content, encoding="utf-8")
        print(f"Wrote: {filepath}", flush=True)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True, "file": filepath.name}).encode("utf-8"))

    def do_GET(self):
        if urlparse(self.path).path == WEBHOOK_PATH or urlparse(self.path).path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Fathom webhook inbox listener. POST to /webhook/fathom")
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        print(f"[{self.log_date_time_string()}] {format % args}", flush=True)


def main():
    port = int(os.environ.get(PORT_ENV, DEFAULT_PORT))
    inbox = get_inbox_dir()
    print(f"Inbox dir: {inbox}", flush=True)
    print(f"Listening on http://0.0.0.0:{port}{WEBHOOK_PATH}", flush=True)
    if not os.environ.get(SECRET_ENV):
        print("Warning: FATHOM_WEBHOOK_SECRET not set — webhook verification disabled.", flush=True)
    server = HTTPServer(("0.0.0.0", port), FathomWebhookHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.", flush=True)
        server.shutdown()
        sys.exit(0)


if __name__ == "__main__":
    main()

