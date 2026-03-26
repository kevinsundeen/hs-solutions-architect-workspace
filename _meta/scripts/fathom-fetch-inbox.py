#!/usr/bin/env python3
"""
Fetch work-related transcripts from Fathom at end of day and write them to _inbox.

Uses Fathom List meetings API (https://developers.fathom.ai/api-reference/meetings/list-meetings)
with include_transcript and include_summary. Skips meetings already written (state file).

Usage:
    # End of day: fetch all meetings created today (default)
    export FATHOM_API_KEY="your-api-key"
    python _meta/scripts/fathom-fetch-inbox.py

    # Fetch a specific date
    python _meta/scripts/fathom-fetch-inbox.py --date 2026-02-12

    # Custom date range (ISO timestamps)
    python _meta/scripts/fathom-fetch-inbox.py --after 2026-02-10T00:00:00Z --before 2026-02-12T00:00:00Z

    # Cap new transcripts per run (e.g. --max 10); run again to fetch the rest
    python _meta/scripts/fathom-fetch-inbox.py --max 10

State file (_inbox/.fathom-fetched-ids.json) stores recording_ids and last_fetched_at.

Env (or .env file in repo root):
    FATHOM_API_KEY — required (from Fathom Settings → API Access)
    INBOX_DIR         — optional; default is repo _inbox
"""

import argparse
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Use certifi's CA bundle if available (fixes SSL errors on macOS with python.org Python)
try:
    import certifi
    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CONTEXT = ssl.create_default_context()

FATHOM_API_BASE = "https://api.fathom.ai/external/v1"
STATE_FILENAME = ".fathom-fetched-ids.json"
INBOX_ENV = "INBOX_DIR"
FATHOM_API_KEY_ENV = "FATHOM_API_KEY"
S2_FATHOM_API_KEY_ENV = "S2_FATHOM_API_KEY"  # legacy / compatibility
ENV_KEYS = (FATHOM_API_KEY_ENV, S2_FATHOM_API_KEY_ENV, INBOX_ENV)


def _load_dotenv() -> None:
    """Load FATHOM_API_KEY (and legacy S2_FATHOM_API_KEY) and INBOX_DIR from .env (or env) if not already in os.environ.
    Looks in: repo root (S2), _inbox, script dir (_meta/scripts), then cwd."""
    if os.environ.get(FATHOM_API_KEY_ENV) or os.environ.get(S2_FATHOM_API_KEY_ENV):
        return
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent.parent
    inbox_dir = repo_root / "_inbox"
    for dir_path in (repo_root, inbox_dir, script_dir, Path.cwd()):
        for name in (".env", "env"):
            env_file = dir_path / name
            if not env_file.is_file():
                continue
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                if key not in ENV_KEYS:
                    continue
                value = value.strip().strip("'\"").strip()
                if key in os.environ:
                    continue
                os.environ[key] = value
            return  # loaded from first file found
    return


def get_inbox_dir() -> Path:
    env = os.environ.get(INBOX_ENV)
    if env:
        return Path(env).resolve()
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent.parent
    return repo_root / "_inbox"


def get_state_path(inbox: Path) -> Path:
    return inbox / STATE_FILENAME


def load_state(inbox: Path) -> tuple[set, str | None]:
    """Return (seen recording_ids, last_fetched_at ISO or None)."""
    p = get_state_path(inbox)
    if not p.exists():
        return set(), None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        ids = set(data.get("recording_ids", []))
        last = data.get("last_fetched_at")
        return ids, last
    except Exception:
        return set(), None


def save_state(inbox: Path, ids: set, last_fetched_at: str | None = None) -> None:
    """Persist seen IDs and optional last fetch time."""
    data: dict = {"recording_ids": list(ids)}
    if last_fetched_at is not None:
        data["last_fetched_at"] = last_fetched_at
    get_state_path(inbox).write_text(
        json.dumps(data, indent=2),
        encoding="utf-8",
    )


def slug(s: str, max_len: int = 40) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:max_len] if s else "meeting"


def format_transcript(transcript: list) -> str:
    if not transcript:
        return ""
    lines = []
    for item in transcript:
        speaker = "Unknown"
        if isinstance(item.get("speaker"), dict):
            speaker = (
                item["speaker"].get("display_name")
                or item["speaker"].get("matched_calendar_invitee_email")
                or "Unknown"
            )
        text = item.get("text", "")
        ts = item.get("timestamp", "")
        if ts:
            lines.append(f"[{ts}] {speaker}: {text}")
        else:
            lines.append(f"{speaker}: {text}")
    return "\n".join(lines)


def build_content(meeting: dict) -> str:
    """Build inbox file: date/title, then summary (if any), then transcript."""
    parts = []
    title = meeting.get("title") or meeting.get("meeting_title") or "Meeting"
    created = meeting.get("created_at") or meeting.get("recording_start_time") or ""
    if created:
        try:
            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            parts.append(f"Date: {dt.strftime('%Y-%m-%d')}")
        except Exception:
            pass
    parts.append(f"Title: {title}")
    parts.append("")
    # Summary up top (from list response or previously fetched via get_recording_summary)
    summary = meeting.get("default_summary") or {}
    if isinstance(summary, dict) and summary.get("markdown_formatted"):
        parts.append("## Summary")
        parts.append("")
        parts.append(summary["markdown_formatted"].strip())
        parts.append("")
        parts.append("---")
        parts.append("")
    parts.append("## Transcript")
    parts.append("")
    transcript = meeting.get("transcript") or []
    parts.append(format_transcript(transcript))
    return "\n".join(parts).strip() + "\n"


def suggest_filename(meeting: dict) -> str:
    created = meeting.get("created_at") or meeting.get("recording_start_time") or ""
    try:
        dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        date_str = dt.strftime("%Y-%m-%d")
    except Exception:
        date_str = datetime.now().strftime("%Y-%m-%d")
    title = meeting.get("meeting_title") or meeting.get("title") or "meeting"
    return f"{date_str}_{slug(title)}.txt"


def get_recording_summary(api_key: str, recording_id: int) -> dict | None:
    """Fetch summary for a recording via GET /recordings/{id}/summary. Returns default_summary-shaped dict or None."""
    url = f"{FATHOM_API_BASE}/recordings/{recording_id}/summary"
    req = urllib.request.Request(url, headers={"X-Api-Key": api_key})
    try:
        with urllib.request.urlopen(req, context=_SSL_CONTEXT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError):
        return None
    summary = data.get("summary")
    if isinstance(summary, dict) and summary.get("markdown_formatted"):
        return summary
    return None


def list_meetings(api_key: str, created_after: str, created_before: str | None = None) -> list:
    """Fetch all meetings in range; paginate with cursor."""
    all_items = []
    url = (
        f"{FATHOM_API_BASE}/meetings"
        f"?created_after={created_after}"
        f"&include_transcript=true"
        f"&include_summary=true"
    )
    if created_before:
        url += f"&created_before={created_before}"
    while url:
        req = urllib.request.Request(url, headers={"X-Api-Key": api_key})
        try:
            with urllib.request.urlopen(req, context=_SSL_CONTEXT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            print(f"Fathom API error {e.code}: {body}", file=sys.stderr)
            sys.exit(1)
        except urllib.error.URLError as e:
            if "CERTIFICATE_VERIFY_FAILED" in str(e) or "certificate" in str(e).lower():
                print("SSL certificate verification failed. Try one of:", file=sys.stderr)
                print("  1. pip install certifi   (if it hangs, use: pip install certifi -v)", file=sys.stderr)
                print("  2. macOS: double-click Install Certificates.command in /Applications/Python 3.x/", file=sys.stderr)
            raise
        items = data.get("items") or []
        all_items.extend(items)
        next_cursor = data.get("next_cursor")
        if not next_cursor:
            break
        base = f"{FATHOM_API_BASE}/meetings?created_after={created_after}&include_transcript=true&include_summary=true"
        if created_before:
            base += f"&created_before={created_before}"
        url = f"{base}&cursor={next_cursor}"
    return all_items


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Fathom transcripts into _inbox (end of day).")
    parser.add_argument(
        "--date",
        metavar="YYYY-MM-DD",
        help="Fetch meetings for this date (default: today)",
    )
    parser.add_argument(
        "--after",
        metavar="ISO",
        help="Fetch meetings created after this timestamp (overrides --date)",
    )
    parser.add_argument(
        "--before",
        metavar="ISO",
        help="Fetch meetings created before this timestamp",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List what would be fetched without writing files",
    )
    parser.add_argument(
        "--max",
        type=int,
        metavar="N",
        dest="max_per_run",
        default=None,
        help="Max new transcripts to write this run (default: no limit). Use to avoid a big burst if you haven't run in a while.",
    )
    args = parser.parse_args()

    _load_dotenv()
    api_key = os.environ.get(FATHOM_API_KEY_ENV) or os.environ.get(S2_FATHOM_API_KEY_ENV)
    if not api_key:
        print("Set FATHOM_API_KEY (from Fathom Settings → API Access).", file=sys.stderr)
        sys.exit(1)

    if args.after:
        created_after = args.after
        created_before = args.before
    elif args.date:
        try:
            d = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            created_after = d.isoformat().replace("+00:00", "Z")
            d_end = d + timedelta(days=1)
            created_before = d_end.isoformat().replace("+00:00", "Z")
        except ValueError:
            print(f"Invalid --date; use YYYY-MM-DD.", file=sys.stderr)
            sys.exit(1)
    else:
        # Today: local midnight to now (so "end of day" run gets your work day)
        now = datetime.now()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        created_after = start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        created_before = None

    inbox = get_inbox_dir()
    inbox.mkdir(parents=True, exist_ok=True)
    seen, last_fetched = load_state(inbox)
    if last_fetched:
        print(f"Last fetch: {last_fetched}")

    meetings = list_meetings(api_key, created_after, created_before)
    new_count = 0
    max_per_run = args.max_per_run
    for meeting in meetings:
        if max_per_run is not None and new_count >= max_per_run:
            print(f"Stopped at --max {max_per_run} new transcripts. Run again to fetch more.")
            break
        rid = meeting.get("recording_id")
        if rid is None:
            continue
        if rid in seen:
            continue
        if not meeting.get("transcript"):
            continue
        # Ensure we have summary (list may omit it); fetch via Get Summary if missing
        if not (meeting.get("default_summary") or {}).get("markdown_formatted"):
            fetched = get_recording_summary(api_key, rid)
            if fetched:
                meeting["default_summary"] = fetched
        if args.dry_run:
            title = meeting.get("meeting_title") or meeting.get("title") or "?"
            created = meeting.get("created_at") or "?"
            print(f"Would write: recording_id={rid} title={title!r} created_at={created}")
            new_count += 1
            continue
        content = build_content(meeting)
        filename = suggest_filename(meeting)
        filepath = inbox / filename
        base, ext = filepath.stem, filepath.suffix
        n = 0
        while filepath.exists():
            n += 1
            filepath = inbox / f"{base}_{n}{ext}"
        filepath.write_text(content, encoding="utf-8")
        seen.add(rid)
        new_count += 1
        print(f"Wrote: {filepath.name}")

    if not args.dry_run:
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        save_state(inbox, seen, last_fetched_at=now_iso)
    if new_count == 0 and not args.dry_run:
        print("No new transcripts to write.")
    elif new_count == 0 and args.dry_run:
        print("No new meetings would be written (none in range or all already fetched).")


if __name__ == "__main__":
    main()

