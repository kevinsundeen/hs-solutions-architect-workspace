#!/usr/bin/env python3
"""
Generate the morning briefing file (_meta/today.md).
Uses GOOGLE_CALENDAR_ICAL_URL for today's events, optional Teamwork for tasks.
Loads env from repo root (.env or env).
"""

import os
import re
import ssl
import sys
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# Display times in Eastern (EST/EDT)
DISPLAY_TZ = ZoneInfo("America/New_York")

try:
    import certifi
    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CONTEXT = ssl.create_default_context()

# Optional: load .env from repo root so GOOGLE_CALENDAR_ICAL_URL, TEAMWORK_* are set
def _load_env(repo_root: Path) -> None:
    for name in (".env", "env"):
        env_file = repo_root / name
        if not env_file.is_file():
            continue
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = value
        return


def _fetch_ical_for_dates(ical_url: str, dates: list[date]) -> tuple[dict[date, list[tuple[str, str]]], str | None]:
    """Fetch iCal URL once and return events by date (in EST). dates = [today, tomorrow, ...].
    Returns (events_by_date, error_msg). Events are (time_str_est, title); time_str_est is '' for all-day."""
    events_by_date: dict[date, list[tuple[str, str]]] = {d: [] for d in dates}
    url = (ical_url or "").strip()
    if not url:
        return events_by_date, "GOOGLE_CALENDAR_ICAL_URL is empty"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "S2-Morning-Briefing/1.0"})
        with urllib.request.urlopen(req, timeout=15, context=_SSL_CONTEXT) as resp:
            data = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return events_by_date, f"Calendar fetch failed: {e}"

    # Unfold ICS (continuation lines start with space/tab)
    lines = []
    for line in data.splitlines():
        if lines and line and line[0] in " \t":
            lines[-1] = lines[-1] + line.strip()
        else:
            lines.append(line)

    # Parse ics: find VEVENT blocks; extract DTSTART (convert to EST) + SUMMARY
    block = []
    in_event = False
    for line in lines:
        line_stripped = line.strip()
        if line_stripped == "BEGIN:VEVENT":
            block = []
            in_event = True
            continue
        if line_stripped == "END:VEVENT":
            in_event = False
            event_date, time_str, title = _parse_vevent_block_est(block)
            if event_date is not None and event_date in events_by_date and title:
                events_by_date[event_date].append((time_str or "", title or "Untitled"))
            block = []
            continue
        if in_event:
            block.append(line)

    for d in events_by_date:
        events_by_date[d].sort(key=lambda x: (x[0], x[1]))
    return events_by_date, None


def _parse_vevent_block_est(lines: list[str]) -> tuple[date | None, str, str]:
    """Return (event_date_in_est, time_str_est, title). time_str_est is '' for all-day. Date is for comparison."""
    dtstart_dt: datetime | None = None  # naive date or datetime in EST
    all_day = False
    summary = ""
    for line in lines:
        if line.startswith("DTSTART"):
            # DTSTART;VALUE=DATE:20260217 or DTSTART;TZID=America/...:20260217T140000 or ...T140000Z
            if ":DATE:" in line.upper():
                part = line.split(":")[-1].strip()[:8]
                if len(part) == 8 and part.isdigit():
                    d = date(int(part[:4]), int(part[4:6]), int(part[6:8]))
                    dtstart_dt = datetime.combine(d, datetime.min.time())
                    all_day = True
            else:
                # DATE-TIME: get TZID or Z
                upper = line.upper()
                tz = None
                if "TZID=" in upper:
                    # DTSTART;TZID=America/New_York:20260217T140000
                    i = upper.index("TZID=") + 5
                    end = line.find(":", i)
                    if end == -1:
                        end = len(line)
                    tz_str = line[i:end].strip()
                    try:
                        tz = ZoneInfo(tz_str.replace(" ", "_"))
                    except Exception:
                        tz = DISPLAY_TZ
                elif "Z" in line.split(":")[-1].strip():
                    tz = ZoneInfo("UTC")
                else:
                    tz = DISPLAY_TZ
                part = line.split(":")[-1].strip().replace("Z", "")
                if "T" in part and len(part) >= 15:
                    y, m, d = int(part[:4]), int(part[4:6]), int(part[6:8])
                    h, mi = int(part[9:11]), int(part[11:13]) if len(part) >= 13 else (0, 0)
                    dtstart_dt = datetime(y, m, d, h, mi, 0, tzinfo=tz)
                    all_day = False
            break
    for line in lines:
        if line.startswith("SUMMARY"):
            summary = line.split(":", 1)[-1].strip().replace("\\n", "\n")
            break

    if dtstart_dt is None:
        return (None, "", summary)

    # Convert to EST for date and time display
    if dtstart_dt.tzinfo is not None:
        est = dtstart_dt.astimezone(DISPLAY_TZ)
    else:
        est = dtstart_dt.replace(tzinfo=DISPLAY_TZ)
    event_date = est.date()
    time_str = "" if all_day else est.strftime("%H:%M")
    return (event_date, time_str, summary)


def _get_client_folders(repo_root: Path) -> list[str]:
    """Return list of client folder names (have context.md), excluding _*, Archive, Templates."""
    names = []
    for d in repo_root.iterdir():
        if not d.is_dir():
            continue
        if d.name.startswith("_") or d.name in ("Archive", "Templates"):
            continue
        if (d / "context.md").exists():
            names.append(d.name)
    return sorted(names)


def _match_prep(events: list[tuple[str, str]], client_folders: list[str]) -> list[tuple[str, str, str]]:
    """Return list of (time, title, context_path) where title matches a client folder."""
    preps = []
    for time_str, title in events:
        for client in client_folders:
            if client.lower() in title.lower():
                preps.append((time_str, title, f"{client}/context.md"))
                break
    return preps


def _fetch_task_comments(base_url: str, headers: dict, task_id: str) -> tuple[str, int]:
    """Fetch comments for a task; return (last_comment_text, count)."""
    import json as _json
    try:
        # v1: GET /tasks/{id}/comments.json; get most recent first
        url = f"{base_url}/tasks/{task_id}/comments.json?pageSize=5&orderBy=date&sortOrder=desc"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=8, context=_SSL_CONTEXT) as resp:
            data = _json.loads(resp.read().decode())
    except Exception:
        return "", 0
    comments = data.get("comments", [])
    if not comments:
        return "", 0
    # First one is most recent (sortOrder=desc)
    body = (comments[0].get("body") or "").strip()
    # Strip HTML-ish tags for brief display
    if "<" in body:
        import re as _re
        body = _re.sub(r"<[^>]+>", " ", body).strip()
    return body[:200], len(comments)


def _teamwork_debug() -> bool:
    """True if Teamwork API debug output is requested (TEAMWORK_DEBUG=1 or --debug)."""
    if os.environ.get("TEAMWORK_DEBUG", "").strip() in ("1", "true", "yes"):
        return True
    if "--debug" in sys.argv or "-d" in sys.argv:
        return True
    return False


def _teamwork_base_url_and_headers(site: str, api_key: str) -> tuple[str, dict]:
    import base64
    if "." in site and " " not in site:
        base_url = f"https://{site}"
    else:
        base_url = f"https://{site}.teamwork.com"
    auth = base64.b64encode(f":{api_key}".encode()).decode()
    headers = {"Authorization": f"Basic {auth}", "Content-Type": "application/json"}
    return base_url, headers


# Keywords in task content that indicate a meeting (exclude from "this week" task list)
_MEETING_KEYWORDS = re.compile(
    r"\b(meeting|call|sync|standup|stand-up|check-in|checkin|huddle|demo|review)\b",
    re.IGNORECASE,
)


def _is_meeting_task(content: str) -> bool:
    """True if task content looks like a meeting (call, sync, etc.)."""
    return bool(content and _MEETING_KEYWORDS.search(content))


def _fetch_teamwork_tasks(site: str, api_key: str) -> tuple[list[dict], str, dict]:
    """Return (list of task dicts, base_url, headers). Tasks due current week (not meetings); uses taskFilter.
    Task: project, content, due_info, due_ymd, task_id, filter_source."""
    import json

    debug = _teamwork_debug()
    base_url, headers = _teamwork_base_url_and_headers(site, api_key)

    if debug:
        print("\n[Teamwork API debug]", flush=True)
        print(f"  base_url: {base_url}", flush=True)

    # Resolve current user (required for filtering by assignee)
    try:
        me_url = f"{base_url}/me.json"
        if debug:
            print(f"  GET {me_url}", flush=True)
        req = urllib.request.Request(me_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10, context=_SSL_CONTEXT) as resp:
            body = resp.read().decode()
            me = json.loads(body)
        person_id = me.get("person", {}).get("id")
        if debug:
            print(f"  me.json → status={resp.status}; person.id={person_id}; keys={list(me.keys())}", flush=True)
        if not person_id:
            if debug:
                print("  → No person.id in response; cannot filter by assignee. Aborting.", flush=True)
            return [], base_url, headers
    except urllib.error.HTTPError as e:
        if debug:
            print(f"  me.json → HTTP {e.code} {e.reason}", flush=True)
            try:
                err_body = e.read().decode()[:500]
                print(f"  body: {err_body}", flush=True)
            except Exception:
                pass
        return [], base_url, headers
    except Exception as e:
        if debug:
            print(f"  me.json → error: {type(e).__name__}: {e}", flush=True)
        return [], base_url, headers

    seen_ids = set()
    tasks_out = []
    # Teamwork: try multiple endpoint styles (V1 vs V3, custom domains may differ)
    # Style A: /tasks.json?taskFilter= (V3-style param on legacy path)
    # Style B: /projects/api/v3/tasks.json?taskFilter=
    # Style C: /tasks.json?filter= (V1 param name)
    task_endpoints = [
        ("tasks.json", "taskFilter"),
        ("projects/api/v3/tasks.json", "taskFilter"),
        ("tasks.json", "filter"),
    ]
    chosen = None  # (path, param_name) that worked
    for path, param_name in task_endpoints:
        url = f"{base_url}/{path}?{param_name}=overdue&pageSize=100"
        if debug:
            print(f"  try GET {url}", flush=True)
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10, context=_SSL_CONTEXT) as resp:
                body = resp.read().decode()
                data = json.loads(body)
            todo_items = data.get("todo-items", data.get("tasks", []))
            if isinstance(todo_items, list):
                chosen = (path, param_name)
                if debug:
                    print(f"  → {path} with {param_name}= works (status={resp.status}, len(todo-items)={len(todo_items)})", flush=True)
                break
        except urllib.error.HTTPError as e:
            if debug:
                err_body = ""
                try:
                    err_body = e.read().decode()[:300]
                except Exception:
                    pass
                print(f"  → HTTP {e.code} {e.reason} {err_body}", flush=True)
            continue
        except Exception as e:
            if debug:
                print(f"  → error: {type(e).__name__}: {e}", flush=True)
            continue

    if not chosen:
        if debug:
            print("  All task endpoint styles returned 401.", flush=True)
            print("  → /me.json works but /tasks.json does not: your API key can read profile but not tasks.", flush=True)
            print("  → In Teamwork: People → your profile → API Keys, create a key with access to Projects/Tasks, or use a different token.", flush=True)
        return tasks_out, base_url, headers

    path, param_name = chosen
    for filter_name in ("overdue", "today", "thisweek"):
        try:
            url = f"{base_url}/{path}?{param_name}={filter_name}&pageSize=100"
            if debug:
                print(f"  GET {url}", flush=True)
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10, context=_SSL_CONTEXT) as resp:
                body = resp.read().decode()
                data = json.loads(body)
        except urllib.error.HTTPError as e:
            if debug:
                print(f"  {path}?{param_name}={filter_name} → HTTP {e.code} {e.reason}", flush=True)
                try:
                    err_body = e.read().decode()[:500]
                    print(f"  body: {err_body}", flush=True)
                except Exception:
                    pass
            continue
        except Exception as e:
            if debug:
                print(f"  → error: {type(e).__name__}: {e}", flush=True)
            continue

        todo_items = data.get("todo-items", data.get("tasks", []))
        if debug:
            print(f"  → status={resp.status}; top-level keys={list(data.keys())}; len(todo-items)={len(todo_items)}", flush=True)

        added = 0
        skipped_dup = 0
        skipped_not_assigned = 0
        skipped_meeting = 0
        for t in todo_items:
            tid = t.get("id")
            if tid in seen_ids:
                skipped_dup += 1
                continue
            rp = t.get("responsible-party-ids")
            rp_str = (rp if isinstance(rp, str) else ",".join(str(x) for x in (rp or []))) or ""
            party_ids = [x.strip() for x in rp_str.split(",") if x.strip()]
            if str(person_id) not in party_ids:
                skipped_not_assigned += 1
                if debug and skipped_not_assigned <= 2:
                    content_preview = (t.get("content") or "")[:50]
                    print(f"    skip (not assigned): id={tid} responsible-party-ids={repr(rp)} content={content_preview!r}", flush=True)
                continue
            seen_ids.add(tid)
            content = (t.get("content") or "").strip()
            if filter_name == "thisweek" and _is_meeting_task(content):
                skipped_meeting += 1
                continue
            project = (t.get("project-name") or "?")
            due = t.get("due-date") or ""
            due_ymd = due[:10] if due and len(due) >= 10 else ""
            if filter_name == "today":
                due_info = "due today"
            elif filter_name == "overdue":
                due_info = "overdue"
            else:
                due_info = f"due {due_ymd}" if due_ymd else "this week"
            if due_ymd:
                due_info += f" ({due_ymd})"
            tasks_out.append({
                "project": project,
                "content": content,
                "due_info": due_info,
                "due_ymd": due_ymd,
                "task_id": str(tid),
                "filter_source": filter_name,
            })
            added += 1

        if debug:
            print(f"  filter={filter_name}: added={added}, skipped_dup={skipped_dup}, skipped_not_assigned={skipped_not_assigned}, skipped_meeting={skipped_meeting}", flush=True)

    if debug:
        print(f"  TOTAL tasks for briefing: {len(tasks_out)}", flush=True)
        print("[Teamwork API debug end]\n", flush=True)

    return tasks_out, base_url, headers


def _teamwork_status_line(task: dict, base_url: str, headers: dict, use_ai: bool) -> str:
    """Build one-line status (and optional AI summary) for a task."""
    last_comment, n_comments = _fetch_task_comments(base_url, headers, task["task_id"])
    desc = (task.get("content") or "")[:150]
    parts = []
    if last_comment:
        parts.append(f"{n_comments} comment(s) (last: \"{last_comment[:80]}\")")
    if desc and not parts:
        parts.append(desc)
    status = "; ".join(parts) if parts else "No comments yet."
    if use_ai and (desc or last_comment):
        try:
            import sys
            _script_dir = Path(__file__).resolve().parent
            if str(_script_dir) not in sys.path:
                sys.path.insert(0, str(_script_dir))
            import llm_helper
            from prompts_loader import get_prompt
            prompt = get_prompt("task-status-summary") or "In one short sentence: current state, blocking, next. No preamble."
            text = f"Task: {desc}\n\nLatest comment: {last_comment}"
            briefing_model = os.environ.get("MORNING_BRIEFING_MODEL") or os.environ.get("OPENAI_MODEL")
            summary = llm_helper.summarize(text, prompt, max_tokens=80, model=briefing_model)
            if summary:
                status = summary
        except Exception:
            pass
    return status


def _inbox_count(repo_root: Path) -> int:
    inbox = repo_root / "_inbox"
    if not inbox.is_dir():
        return 0
    return sum(1 for f in inbox.iterdir() if f.is_file() and f.suffix.lower() in (".txt", ".md") and not f.name.startswith("."))


def _last_sync(repo_root: Path) -> str | None:
    state = repo_root / "_inbox" / ".fathom-fetched-ids.json"
    if not state.is_file():
        return None
    try:
        import json
        data = json.loads(state.read_text(encoding="utf-8"))
        return data.get("last_fetched_at")
    except Exception:
        return None


def _read_planner_tasks(meta: Path) -> list[str]:
    planner = meta / "planner.md"
    if not planner.is_file():
        return []
    lines = []
    for line in planner.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("- [ ]") or line.startswith("- [x]"):
            lines.append(line)
        elif line.startswith("- ") and not line.startswith("- ["):
            lines.append("- [ ] " + line[2:].strip())
    return lines[:15]


def _inbox_one_liners(repo_root: Path) -> list[tuple[str, str]]:
    """Return list of (filename, one_line_summary) for _inbox transcripts when LLM available."""
    inbox = repo_root / "_inbox"
    if not inbox.is_dir():
        return []
    try:
        _script_dir = Path(__file__).resolve().parent
        import sys
        if str(_script_dir) not in sys.path:
            sys.path.insert(0, str(_script_dir))
        import llm_helper
        if not _get_api_key()[0]:
            return []
    except Exception:
        return []
    out = []
    for f in sorted(inbox.iterdir()):
        if not f.is_file() or f.name.startswith(".") or f.suffix.lower() not in (".txt", ".md"):
            continue
        try:
            from prompts_loader import get_prompt
            prompt = get_prompt("inbox-one-liner") or "In one short sentence, what is this meeting about and what was agreed or next step?"
            text = f.read_text(encoding="utf-8", errors="replace")[:4000]
            briefing_model = os.environ.get("MORNING_BRIEFING_MODEL") or os.environ.get("OPENAI_MODEL")
            one = llm_helper.summarize(text, prompt, max_tokens=100, model=briefing_model)
            out.append((f.name, one or "(no summary)"))
        except Exception:
            out.append((f.name, "(could not summarize)"))
    return out


def _get_api_key():
    """Delegate to llm_helper if available."""
    try:
        _script_dir = Path(__file__).resolve().parent
        import sys
        if str(_script_dir) not in sys.path:
            sys.path.insert(0, str(_script_dir))
        import llm_helper
        return llm_helper._get_api_key()
    except Exception:
        return None, ""


def _prep_brief(repo_root: Path, client: str) -> str | None:
    """Return 3-5 bullet prep brief for a client (context + last transcript) or None."""
    ctx_path = repo_root / client / "context.md"
    trans_dir = repo_root / client / "transcripts"
    if not ctx_path.is_file():
        return None
    try:
        _script_dir = Path(__file__).resolve().parent
        import sys
        if str(_script_dir) not in sys.path:
            sys.path.insert(0, str(_script_dir))
        import llm_helper
        if not llm_helper._get_api_key()[0]:
            return None
    except Exception:
        return None
    parts = [ctx_path.read_text(encoding="utf-8", errors="replace")[:6000]]
    if trans_dir.is_dir():
        last_trans = sorted(trans_dir.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
        if last_trans:
            parts.append("Last transcript:\n" + last_trans[0].read_text(encoding="utf-8", errors="replace")[:4000])
    text = "\n\n".join(parts)
    try:
        from prompts_loader import get_prompt
        prompt = get_prompt("morning-prep-brief") or "Give 3-5 bullet points to prep for this client meeting: current focus, open questions, last call takeaways, suggested talking points. One line per bullet."
    except Exception:
        prompt = "Give 3-5 bullet points to prep for this client meeting: current focus, open questions, last call takeaways. One line per bullet."
    briefing_model = os.environ.get("MORNING_BRIEFING_MODEL") or os.environ.get("OPENAI_MODEL")
    result = llm_helper.summarize(text, prompt, max_tokens=400, model=briefing_model)
    return result


def _one_sentence_call_agenda(repo_root: Path, client: str) -> str | None:
    """One-sentence agenda for terminal summary. Returns None if no LLM or no context."""
    ctx_path = repo_root / client / "context.md"
    trans_dir = repo_root / client / "transcripts"
    if not ctx_path.is_file():
        return None
    try:
        _script_dir = Path(__file__).resolve().parent
        import sys
        if str(_script_dir) not in sys.path:
            sys.path.insert(0, str(_script_dir))
        import llm_helper
        if not llm_helper._get_api_key()[0]:
            return None
        from prompts_loader import get_prompt
        prompt = get_prompt("morning-call-agenda-one-sentence") or 'In one short sentence, give the agenda for this client call. No preamble.'
    except Exception:
        return None
    parts = [ctx_path.read_text(encoding="utf-8", errors="replace")[:4000]]
    if trans_dir.is_dir():
        last_trans = sorted(trans_dir.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
        if last_trans:
            parts.append(last_trans[0].read_text(encoding="utf-8", errors="replace")[:2000])
    briefing_model = os.environ.get("MORNING_BRIEFING_MODEL") or os.environ.get("OPENAI_MODEL")
    result = llm_helper.summarize("\n\n".join(parts), prompt, max_tokens=80, model=briefing_model)
    return result


def _load_teamwork_client_map(meta: Path) -> dict[str, str]:
    """Load optional _meta/teamwork-clients.txt: lines 'project_substring=ClientFolder' -> map project substring to client."""
    f = meta / "teamwork-clients.txt"
    if not f.is_file():
        return {}
    m = {}
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip()
        if key and val:
            m[key] = val
    return m


def _task_to_client(client_map: dict[str, str], task: dict) -> str | None:
    """Return client folder name if task's project matches a key in client_map, else None."""
    project = (task.get("project") or "").lower()
    for sub, client in client_map.items():
        if sub.lower() in project:
            return client
    return None


def _suggested_activities_for_task(
    repo_root: Path, client: str, task: dict, last_comment: str, use_ai: bool
) -> list[str]:
    """Using client context (and optional last transcript), suggest 2-4 activities to keep the task rolling. Returns list of lines."""
    ctx_path = repo_root / client / "context.md"
    if not ctx_path.is_file():
        return []
    if not use_ai:
        return []
    try:
        _script_dir = Path(__file__).resolve().parent
        import sys
        if str(_script_dir) not in sys.path:
            sys.path.insert(0, str(_script_dir))
        import llm_helper
        if not llm_helper._get_api_key()[0]:
            return []
    except Exception:
        return []
    parts = [ctx_path.read_text(encoding="utf-8", errors="replace")[:6000]]
    trans_dir = repo_root / client / "transcripts"
    if trans_dir.is_dir():
        last_trans = sorted(trans_dir.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
        if last_trans:
            parts.append("Last transcript:\n" + last_trans[0].read_text(encoding="utf-8", errors="replace")[:3000])
    context_text = "\n\n".join(parts)
    task_desc = (task.get("content") or "")[:500]
    comment_block = f"\n\nLatest task comment: {last_comment}" if last_comment else ""
    text = f"Client context:\n{context_text}\n\nTask: {task_desc}{comment_block}"
    try:
        from prompts_loader import get_prompt
        prompt = get_prompt("task-suggested-activities") or "Suggest 2-4 concrete activities to keep this task moving. One short line per activity. No preamble."
        briefing_model = os.environ.get("MORNING_BRIEFING_MODEL") or os.environ.get("OPENAI_MODEL")
        result = llm_helper.summarize(text, prompt, max_tokens=300, model=briefing_model)
        if not result:
            return []
        activities = []
        for line in result.strip().split("\n"):
            line = line.strip().strip("-•*123456789.")
            if line:
                activities.append(line)
        return activities[:4]
    except Exception:
        return []


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent.parent
    meta = repo_root / "_meta"
    briefing_path = meta / "today.md"

    _load_env(repo_root)

    today = date.today()
    date_str = today.strftime("%Y-%m-%d")

    sections = []
    sections.append(f"# Morning Briefing — {date_str}\n")

    # Calendar (times in EST); look ahead to tomorrow and day after
    ical_url = (os.environ.get("GOOGLE_CALENDAR_ICAL_URL") or "").strip()
    dates_to_fetch = [today, today + timedelta(days=1), today + timedelta(days=2)]
    events_by_date: dict[date, list[tuple[str, str]]] = {d: [] for d in dates_to_fetch}
    if ical_url:
        events_by_date, cal_error = _fetch_ical_for_dates(ical_url, dates_to_fetch)
        events = events_by_date.get(today, [])
        sections.append("## Calendar (EST)")
        if cal_error:
            sections.append(f"- {cal_error}")
        elif events:
            for time_str, title in events:
                if time_str:
                    sections.append(f"- {time_str}  {title}")
                else:
                    sections.append(f"- {title}")
        else:
            sections.append("- No events today.")
        sections.append("")
        # Coming up: tomorrow and day after
        coming_up = []
        for d in (today + timedelta(days=1), today + timedelta(days=2)):
            day_events = events_by_date.get(d, [])
            if day_events:
                label = "Tomorrow" if d == today + timedelta(days=1) else d.strftime("%a %b %d")
                coming_up.append((label, day_events))
        if coming_up:
            sections.append("## Coming up (get ahead)")
            for label, day_events in coming_up:
                sections.append(f"- **{label}**")
                for time_str, title in day_events:
                    if time_str:
                        sections.append(f"  - {time_str}  {title}")
                    else:
                        sections.append(f"  - {title}")
            sections.append("")
    else:
        sections.append("## Calendar (EST)")
        sections.append("- (Set GOOGLE_CALENDAR_ICAL_URL in .env to show today's events)")
        sections.append("")

    # Prep (event title matches client folder)
    client_folders = _get_client_folders(repo_root)
    preps = []
    if ical_url and events:
        preps = _match_prep(events, client_folders)
        if preps:
            sections.append("## Prep")
            for time_str, title, ctx_path in preps:
                sections.append(f"- {time_str} {title} → {ctx_path}")
            sections.append("")
            # Prep briefs (Phase 2: AI 3-5 bullets per prep client)
            if _get_api_key()[0]:
                prep_clients = list({ctx_path.split("/")[0] for (_, _, ctx_path) in preps})
                for client in prep_clients:
                    brief = _prep_brief(repo_root, client)
                    if brief:
                        sections.append(f"### Prep brief: {client}")
                        for line in brief.strip().split("\n"):
                            line = line.strip().strip("-•*")
                            if line:
                                sections.append(f"- {line}")
                        sections.append("")

    # Teamwork (Phase 2: today, overdue, this week + status/summary)
    site = os.environ.get("TEAMWORK_SITE", "").strip()
    tw_key = os.environ.get("TEAMWORK_API_KEY", "").strip()
    use_ai = bool(
        os.environ.get("OPENAI_API_KEY")
        or os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("S2_ANTHROPIC_API_KEY")
    )
    tasks_list, today_overdue, this_week = [], [], []
    base_url, headers = "", {}
    if _teamwork_debug() and not (site and tw_key):
        print("[Teamwork API debug] Skipped: TEAMWORK_SITE or TEAMWORK_API_KEY not set in .env", flush=True)
    if site and tw_key:
        tasks_list, base_url, headers = _fetch_teamwork_tasks(site, tw_key)
        today_overdue = [t for t in tasks_list if t["filter_source"] in ("overdue", "today")]
        this_week = [t for t in tasks_list if t["filter_source"] == "thisweek"]
        client_map = _load_teamwork_client_map(meta)
        non_meeting_tasks = [t for t in tasks_list if not _is_meeting_task(t.get("content") or "")]

        if today_overdue:
            sections.append("## Teamwork — Today & Overdue")
            for t in today_overdue:
                status = _teamwork_status_line(t, base_url, headers, use_ai)
                sections.append(f"- [ ] {t['content']} ({t['project']}) — {t['due_info']} — *{status}*")
            sections.append("")
        else:
            sections.append("## Teamwork — Today & Overdue")
            sections.append("- No tasks due today or overdue.")
            sections.append("")
        if this_week:
            sections.append("## Teamwork — This Week")
            for t in this_week:
                status = _teamwork_status_line(t, base_url, headers, use_ai)
                sections.append(f"- [ ] {t['content']} ({t['project']}) — {t['due_info']} — *{status}*")
            sections.append("")

        # Non-meeting tasks with suggested activities from client context
        if non_meeting_tasks:
            sections.append("## Teamwork — Tasks (non-meeting, this week)")
            for t in non_meeting_tasks:
                status = _teamwork_status_line(t, base_url, headers, use_ai)
                sections.append(f"- [ ] **{t['content']}** ({t['project']}) — {t['due_info']} — *{status}*")
                client = _task_to_client(client_map, t) if client_map else None
                if client:
                    last_comment, _ = _fetch_task_comments(base_url, headers, t["task_id"])
                    activities = _suggested_activities_for_task(repo_root, client, t, last_comment, use_ai)
                    if activities:
                        sections.append(f"  **Suggested activities ({client}):**")
                        for a in activities:
                            sections.append(f"  - {a}")
            sections.append("")
        # Optional: Teamwork by client (when _meta/teamwork-clients.txt exists)
        if client_map and tasks_list:
            by_client = {}
            for t in tasks_list:
                for sub, client in client_map.items():
                    if sub.lower() in (t.get("project") or "").lower():
                        by_client.setdefault(client, []).append(t)
                        break
            if by_client:
                sections.append("## Teamwork by client")
                for client in sorted(by_client.keys()):
                    tasks = by_client[client]
                    sections.append(f"- **{client}:** {len(tasks)} task(s) due (today/overdue/this week)")
                sections.append("")
    # else: don't add Teamwork section if not configured

    # Tasks from planner
    planner_tasks = _read_planner_tasks(meta)
    if planner_tasks:
        sections.append("## Tasks (from _meta/planner.md)")
        for line in planner_tasks:
            sections.append(line)
        sections.append("")

    # Workspace
    inbox_n = _inbox_count(repo_root)
    last = _last_sync(repo_root)
    sections.append("## Workspace")
    sections.append(f"- Inbox: {inbox_n} unfiled transcript(s)")
    sections.append(f"- Last sync: {last or 'never'}")
    sections.append("")
    # Inbox one-liners (Phase 2: AI summary per unfiled transcript)
    one_liners = _inbox_one_liners(repo_root)
    if one_liners:
        sections.append("## Inbox (one-line summaries)")
        for fname, one in one_liners:
            sections.append(f"- **{fname}:** {one}")
        sections.append("")

    content = "\n".join(sections).strip() + "\n"
    briefing_path.write_text(content, encoding="utf-8")
    print(f"Briefing written to {briefing_path}\n")
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import ste_log
        ste_log.record(content, "morning")    # advisory only
    except Exception:
        pass

    # Terminal summary: Teamwork day, recent comments, one-sentence client call agendas
    n_today = len([t for t in tasks_list if t.get("filter_source") == "today"])
    n_overdue = len([t for t in tasks_list if t.get("filter_source") == "overdue"])
    n_week = len(this_week)
    if tasks_list:
        print("  **Today (Teamwork):** ", end="")
        parts = []
        if n_overdue:
            parts.append(f"{n_overdue} overdue")
        if n_today:
            parts.append(f"{n_today} due today")
        if n_week:
            parts.append(f"{n_week} this week")
        print(", ".join(parts) + ".")
        # Recent comments: up to 3 from today/overdue tasks (status line already has comment or AI summary)
        if today_overdue and base_url and headers:
            recent = []
            for t in today_overdue[:3]:
                status = _teamwork_status_line(t, base_url, headers, False)
                if status and len(status) < 70:
                    recent.append(f'"{status[:60]}..."' if len(status) > 60 else f'"{status}"')
                elif status:
                    recent.append(f'"{status[:50]}..."')
            if recent:
                print("  **Recent:** " + "; ".join(recent))
    if preps:
        print("  **Client calls:**")
        agenda_cache = {}
        for time_str, title, ctx_path in preps:
            client = ctx_path.split("/")[0]
            if client not in agenda_cache and _get_api_key()[0]:
                agenda_cache[client] = _one_sentence_call_agenda(repo_root, client)
            agenda = agenda_cache.get(client)
            agenda_str = f" — {agenda}" if agenda else ""
            print(f"    {time_str} {client}{agenda_str}")
    if inbox_n > 0:
        print(f"  **Inbox:** {inbox_n} unfiled.")
    print(f"  Open: {briefing_path}")


if __name__ == "__main__":
    main()
    sys.exit(0)
