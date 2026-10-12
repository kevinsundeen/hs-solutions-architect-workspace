#!/usr/bin/env python3
"""
Fetch work-related transcripts from Fathom at end of day and write them to _inbox.

Uses Fathom List meetings API to discover recordings, then fetches each transcript and summary
via dedicated /recordings/{id}/transcript and /recordings/{id}/summary endpoints.
Skips meetings already written (state file).

Usage:
    # End of day: fetch all meetings created today (default)
    export S2_FATHOM_API_KEY="your-api-key"
    python _meta/scripts/fathom-fetch-inbox.py

    # Fetch a specific date
    python _meta/scripts/fathom-fetch-inbox.py --date 2026-02-12

    # Custom date range (ISO timestamps)
    python _meta/scripts/fathom-fetch-inbox.py --after 2026-02-10T00:00:00Z --before 2026-02-12T00:00:00Z

    # Cap new transcripts per run (e.g. --max 10); run again to fetch the rest
    python _meta/scripts/fathom-fetch-inbox.py --max 10

    # After writing new transcripts, run AI facilitation coach (needs OPENAI_API_KEY or ANTHROPIC_API_KEY)
    python _meta/scripts/fathom-fetch-inbox.py --coach

State file (_inbox/.fathom-fetched-ids.json) stores recording_ids and last_fetched_at.

Env (or .env file in repo root):
    S2_FATHOM_API_KEY — required (from Fathom Settings → API Access)
    INBOX_DIR         — optional; default is repo _inbox
"""

import argparse
import json
import os
import re
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
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
API_KEY_ENV = "S2_FATHOM_API_KEY"
API_KEY_TEST_ENV = "FATHOM_TEST_KEY"
ENV_KEYS = (API_KEY_ENV, API_KEY_TEST_ENV, INBOX_ENV)


def _load_dotenv() -> None:
    """Load S2_FATHOM_API_KEY, FATHOM_TEST_KEY, and INBOX_DIR from .env (or env).
    Looks in: repo root (S2), _inbox, script dir (_meta/scripts), then cwd."""
    if os.environ.get(API_KEY_ENV) and os.environ.get(API_KEY_TEST_ENV):
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
        # Normalise to str: save_state writes strings, older files hold ints. Every comparison
        # against this set must use str(rid) or the dedupe silently misses and re-fetches.
        ids = {str(x) for x in (data.get("recording_ids") or [])}
        last = data.get("last_fetched_at")
        return ids, last
    except Exception:
        return set(), None


def save_state(inbox: Path, ids: set, last_fetched_at: str | None = None) -> None:
    """Persist seen IDs and optional last fetch time.

    MERGE with what is on disk, never replace it. post-call.py runs as a LaunchAgent every 5
    minutes and writes this same file; this function used to build a fresh dict, so a save that
    landed just after the agent's silently dropped every id the agent had added and those
    meetings were re-fetched as byte-identical duplicates (observed 2026-09-08 19:15).
    """
    path = get_state_path(inbox)
    data: dict = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8")) or {}
        except (json.JSONDecodeError, OSError):
            data = {}
    prior = {str(x) for x in (data.get("recording_ids") or [])}
    data["recording_ids"] = sorted(prior | {str(x) for x in ids})
    if last_fetched_at is not None:
        data["last_fetched_at"] = last_fetched_at
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def slug(s: str, max_len: int = 40) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:max_len] if s else "meeting"


def strip_fathom_links(text: str) -> str:
    return re.sub(r'\[([^\]]*)\]\(https?://[^)]+\)', r'\1', text)


def format_transcript(transcript: list) -> str:
    if not transcript:
        return ""

    paragraphs: list[str] = []
    group_speaker: str | None = None
    group_ts: str = "00:00:00"
    buffer: list[str] = []

    def flush() -> None:
        if group_speaker and buffer:
            paragraphs.append(f"**{group_speaker} [{group_ts}]:** {' '.join(buffer)}")

    for item in transcript:
        text = (item.get("text") or "").strip()
        if not text:
            continue
        speaker = "Unknown"
        if isinstance(item.get("speaker"), dict):
            speaker = (
                item["speaker"].get("display_name")
                or item["speaker"].get("matched_calendar_invitee_email")
                or "Unknown"
            )
        ts = item.get("timestamp") or "00:00:00"

        if speaker == group_speaker:
            buffer.append(text)
        else:
            flush()
            group_speaker = speaker
            group_ts = ts
            buffer = [text]

    flush()
    return "\n\n".join(paragraphs)


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
        parts.append(strip_fathom_links(summary["markdown_formatted"].strip()))
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


def _get_json_with_retry(api_key: str, url: str, max_retries: int = 4) -> dict | None:
    """GET url with X-Api-Key, retrying on 429 using the Retry-After header.

    2026-09-22: a 10-req/window rate limit on /recordings/{id}/{transcript,summary} was
    getting hit during backfills (list_meetings + per-meeting transcript + summary calls add
    up fast). The old bare `except (HTTPError, URLError): return None` swallowed 429s
    identically to "recording has no transcript yet" — a backfill would silently skip
    real meetings and report them as having no transcript. Retry on 429 before giving up;
    any other HTTP/URL error still returns None (those ARE genuine "not available" cases).
    """
    req = urllib.request.Request(url, headers={"X-Api-Key": api_key})
    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(req, context=_SSL_CONTEXT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < max_retries:
                wait = float(e.headers.get("Retry-After", "3")) if e.headers else 3.0
                time.sleep(max(wait, 1.0))
                continue
            return None
        except urllib.error.URLError:
            return None
    return None


def get_recording_summary(api_key: str, recording_id: int) -> dict | None:
    """Fetch summary for a recording via GET /recordings/{id}/summary. Returns default_summary-shaped dict or None."""
    url = f"{FATHOM_API_BASE}/recordings/{recording_id}/summary"
    data = _get_json_with_retry(api_key, url)
    if not data:
        return None
    summary = data.get("summary")
    if isinstance(summary, dict) and summary.get("markdown_formatted"):
        return summary
    return None


def get_recording_transcript(api_key: str, recording_id: int) -> list | None:
    """Fetch transcript for a recording via GET /recordings/{id}/transcript. Returns list of segments or None."""
    url = f"{FATHOM_API_BASE}/recordings/{recording_id}/transcript"
    data = _get_json_with_retry(api_key, url)
    if not data:
        return None
    transcript = data.get("transcript")
    if isinstance(transcript, list) and transcript:
        return transcript
    return None


# Scope to the user's own meetings client-side. 2026-09-08: Fathom-side team sharing widened, so
# this API key can now see every team recording — 24 meetings on a day the user recorded 4,
# most of them other accounts (Origin, Accurx, Corpay, Ashling...). It also pulled a colleague's
# copy of calls already captured, producing _1/_2/_3 duplicates of the same meeting.
#
# 2026-09-22: switched off the server-side `recorded_by[]=` filter. Team went to a shared Fathom
# instance where only the HOST's client joins as recorder — the user's own meetings now often show
# up with a colleague as `recorded_by` (e.g. Daniel Kwok recorded a client call the user ran). The
# API filters strictly on the recorder, so it silently dropped every meeting the user attended but
# didn't record. Fix: pull the full team list and filter client-side on EITHER recorded_by OR
# calendar_invitees containing one of the scoped emails — this is an OR, not a replacement, so
# the user's own solo/personal recordings (no calendar invite) still match.
# NOTE the brackets on recorded_by[]= if you ever reintroduce a server-side filter: bare
# `recorded_by=` is silently ignored (measured — returned all 24).
# Override or widen scope with S2_FATHOM_RECORDED_BY (comma-separated emails);
# set it empty to fetch everything (no client-side filtering).
DEFAULT_RECORDED_BY = os.environ.get("S2_FATHOM_RECORDED_BY", "")


def scoped_emails() -> list[str]:
    raw = os.environ.get("S2_FATHOM_RECORDED_BY", DEFAULT_RECORDED_BY)
    if raw is not None and raw.strip() == "":
        return []    # explicitly opted out — no filtering
    return [e.strip().lower() for e in (raw or DEFAULT_RECORDED_BY).split(",") if e.strip()]


def meeting_matches_scope(meeting: dict, emails: list[str]) -> bool:
    """True if meeting was recorded by, or invited, one of the scoped emails.

    Client-side (not an API filter) so meetings recorded by a teammate host, where the user was
    just an invitee, still come through. See note above scoped_emails().
    """
    if not emails:
        return True
    recorded_by = (meeting.get("recorded_by") or {}).get("email", "").lower()
    if recorded_by in emails:
        return True
    for invitee in meeting.get("calendar_invitees") or []:
        if (invitee.get("email") or "").lower() in emails:
            return True
    return False


def dedupe_logical_meetings(meetings: list, emails: list[str]) -> list:
    """Collapse multiple recorder copies of the same meeting into one.

    A meeting with N attendees who all have Fathom can produce N recording_ids — one per
    recorder — for the SAME logical meeting. Scoping by invitee (see meeting_matches_scope)
    fixed missing host-only-recorded meetings, but without this step it also re-admits every
    teammate's duplicate copy of a meeting the user's own client already recorded — exactly the
    "colleague's copy" duplication the recorded_by[] filter existed to prevent (see 2026-09-08
    note above). Group by (title, scheduled_start_time); within a group, prefer the copy
    recorded by a scoped email (the user's own), else keep the first.
    """
    from collections import OrderedDict
    groups: "OrderedDict[tuple, list]" = OrderedDict()
    for m in meetings:
        key = (m.get("title"), m.get("scheduled_start_time") or m.get("recording_start_time"))
        groups.setdefault(key, []).append(m)
    result = []
    for copies in groups.values():
        preferred = next(
            (c for c in copies if (c.get("recorded_by") or {}).get("email", "").lower() in emails),
            copies[0],
        )
        result.append(preferred)
    return result


def list_meetings(api_key: str, created_after: str, created_before: str | None = None) -> list:
    """Fetch all meetings in range; paginate with cursor. Scope filtering happens client-side
    in main() via meeting_matches_scope() — see note above scoped_emails()."""
    all_items = []
    url = f"{FATHOM_API_BASE}/meetings?created_after={created_after}"
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
        base = f"{FATHOM_API_BASE}/meetings?created_after={created_after}"
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
    parser.add_argument(
        "--coach",
        action="store_true",
        help=(
            "Run AI facilitation coach on the written files. Note: by default coaching only applies to transcripts "
            "filed into client transcripts/ folders (not _inbox). See _meta/call-coaching/README.md."
        ),
    )
    args = parser.parse_args()

    _load_dotenv()
    api_key = os.environ.get(API_KEY_TEST_ENV) or os.environ.get(API_KEY_ENV)
    if not api_key:
        print("Set S2_FATHOM_API_KEY (from Fathom Settings → API Access).", file=sys.stderr)
        sys.exit(1)
    if os.environ.get(API_KEY_TEST_ENV):
        print(f"Using test API key ({API_KEY_TEST_ENV})", file=sys.stderr)

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
        created_after = None
        created_before = None

    inbox = get_inbox_dir()
    inbox.mkdir(parents=True, exist_ok=True)
    seen, last_fetched = load_state(inbox)

    if created_after is None:
        # Default window: from local midnight, or 24h before the last fetch if that's earlier.
        # 2026-09-24: "today only" silently skipped every meeting from a day `s2 fetch` wasn't
        # run (9 attended calls from 09-22/23 missed). The 24h overlap also catches host-recorded
        # copies that finish processing after a fetch; the `seen` set keeps re-runs idempotent.
        # Capped at 14 days so a long-stale state file doesn't trigger a huge backfill.
        now = datetime.now()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
        if last_fetched:
            try:
                lf = datetime.strptime(last_fetched, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                start = min(start, max(lf - timedelta(days=1), start - timedelta(days=14)))
            except ValueError:
                pass
        created_after = start.strftime("%Y-%m-%dT%H:%M:%SZ")
        print(f"Window: since {created_after}")
    if last_fetched:
        print(f"Last fetch: {last_fetched}")

    meetings = list_meetings(api_key, created_after, created_before)
    emails = scoped_emails()
    meetings = [m for m in meetings if meeting_matches_scope(m, emails)]
    meetings = dedupe_logical_meetings(meetings, emails)
    new_count = 0
    written_paths: list[Path] = []
    max_per_run = args.max_per_run
    for meeting in meetings:
        if max_per_run is not None and new_count >= max_per_run:
            print(f"Stopped at --max {max_per_run} new transcripts. Run again to fetch more.")
            break
        rid = meeting.get("recording_id")
        if rid is None:
            continue
        if str(rid) in seen:
            continue
        # Fetch transcript via dedicated endpoint (include_transcript on /meetings is disabled)
        if not meeting.get("transcript"):
            fetched_transcript = get_recording_transcript(api_key, rid)
            if fetched_transcript:
                meeting["transcript"] = fetched_transcript
        if not meeting.get("transcript"):
            continue
        # Fetch summary via dedicated endpoint if not already present
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
        seen.add(str(rid))
        new_count += 1
        written_paths.append(filepath)
        print(f"Wrote: {filepath.name}")

    if not args.dry_run:
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        save_state(inbox, seen, last_fetched_at=now_iso)
    if new_count == 0 and not args.dry_run:
        print("No new transcripts to write.")
    elif new_count == 0 and args.dry_run:
        print("No new meetings would be written (none in range or all already fetched).")

    coach_script = Path(__file__).resolve().parent / "fathom-call-coach.py"
    if args.coach and written_paths and not args.dry_run and coach_script.is_file():
        payload = json.dumps([str(p.resolve()) for p in written_paths])
        r = subprocess.run(
            [
                sys.executable,
                str(coach_script),
                "--allow-inbox",
                "--paths-json",
                payload,
            ],
            cwd=str(Path(__file__).resolve().parent.parent),
        )
        if r.returncode != 0:
            print("fathom-call-coach.py exited with errors (transcripts were still saved).", file=sys.stderr)


if __name__ == "__main__":
    main()
