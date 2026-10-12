#!/usr/bin/env python3
"""
Job health for the S2 LaunchAgents (phase2-spec.md §2H). Stdlib only: imported by scripts that
run under different Pythons (system 3.14, Personal/.venv).

Three signals, all read by the 07:00 digest footer (decision_queue.footer_lines):
  1. Heartbeats. A job wrapped in `run(job, main)` writes `_meta/queue/heartbeats/<job>.json`
     when launchd starts it (XPC_SERVICE_NAME == com.s2.<job>); manual runs don't count.
     `next_due` is the job's next launchd fire time plus grace, read from its own plist.
  2. launchd exit status. `launchctl list` keeps the last exit code of each com.s2.* job; a
     KeepAlive job (slack-bridge) must have a PID.
  3. Auth. Slack auth.test per token, Teamwork /me.json. Expired tokens show before a job fails.

CLI
  python3 job_health.py seed       write next_due for wrapped jobs that have no heartbeat yet
  python3 job_health.py check      print every problem line (what the digest footer shows)
"""
from __future__ import annotations

import json
import os
import plistlib
import subprocess
import sys
import traceback
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HB_DIR = REPO_ROOT / "_meta" / "queue" / "heartbeats"
AGENTS = Path.home() / "Library" / "LaunchAgents"
PREFIX = "com.s2."
CAL_GRACE = timedelta(hours=2)
MIN_INTERVAL_GRACE = timedelta(minutes=30)
# Jobs wrapped with run(); `seed` gives each a heartbeat file before its first wrapped run.
WRAPPED = ("week-plan", "week-handoff", "linkedin", "post-call", "call-prep", "recall", "cb-uat-watch",
           "inbox", "meeting-prep", "task-worker")
SLACK_TOKENS = ("SLACK_USER_TOKEN", "SLACK_BOT_TOKEN", "DECISIONS_SLACK_BOT_TOKEN", "WEEK_PLAN_SLACK_BOT_TOKEN")


def _now(now: datetime | None = None) -> datetime:
    return (now or datetime.now(timezone.utc)).astimezone()


# ---- schedule ------------------------------------------------------------------------------------
def load_plist(job: str, agents: Path = AGENTS) -> dict | None:
    p = agents / f"{PREFIX}{job}.plist"
    return plistlib.loads(p.read_bytes()) if p.is_file() else None


def next_fire(plist: dict, after: datetime) -> datetime | None:
    """Next time launchd starts this job after `after` (local time). None for KeepAlive-only jobs."""
    after = after.astimezone()
    if plist.get("StartInterval"):
        return after + timedelta(seconds=int(plist["StartInterval"]))
    cal = plist.get("StartCalendarInterval")
    if not cal:
        return None
    best = None
    for e in cal if isinstance(cal, list) else [cal]:
        for d in range(0, 9):
            day = (after + timedelta(days=d)).date()
            if "Weekday" in e and (day.weekday() + 1) % 7 != int(e["Weekday"]) % 7:  # launchd: 0/7 = Sun
                continue
            hours = [int(e["Hour"])] if "Hour" in e else range(24)
            for h in hours:
                t = datetime(day.year, day.month, day.day, h, int(e.get("Minute", 0))).astimezone()
                if t > after and (best is None or t < best):
                    best = t
    return best


def grace(plist: dict) -> timedelta:
    if plist.get("StartInterval"):
        return max(MIN_INTERVAL_GRACE, timedelta(seconds=3 * int(plist["StartInterval"])))
    return CAL_GRACE


def next_due(job: str, now: datetime | None = None, agents: Path = AGENTS) -> datetime | None:
    pl = load_plist(job, agents)
    nf = next_fire(pl, _now(now)) if pl else None
    return nf + grace(pl) if nf else None


# ---- heartbeat writes ----------------------------------------------------------------------------
def write_heartbeat(job: str, ok: bool, error: str | None = None, now: datetime | None = None,
                    hb_dir: Path = HB_DIR, agents: Path = AGENTS) -> None:
    now = _now(now)
    hb_dir.mkdir(parents=True, exist_ok=True)
    p = hb_dir / f"{job}.json"
    cur = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    if ok:
        cur["last_ok"] = now.isoformat()
    else:
        cur["last_error"] = (error or "unknown")[-300:]
        cur["last_error_at"] = now.isoformat()
    nd = next_due(job, now, agents)
    if nd:
        cur["next_due"] = nd.isoformat()
    p.write_text(json.dumps(cur, indent=2) + "\n", encoding="utf-8")


def run(job: str, main, *args):
    """Call main(*args); record the outcome when launchd started this run. Returns main's result."""
    if os.environ.get("XPC_SERVICE_NAME") != f"{PREFIX}{job}":
        return main(*args)
    try:
        rc = main(*args)
    except SystemExit as e:
        code = e.code
        ok = code in (None, 0)
        _safe_write(job, ok, None if ok else f"exit {code}")
        raise
    except BaseException as e:
        _safe_write(job, False, "".join(traceback.format_exception_only(type(e), e)).strip())
        raise
    ok = rc in (None, 0)
    _safe_write(job, ok, None if ok else f"exit {rc}")
    return rc


def _safe_write(job: str, ok: bool, error: str | None) -> None:
    try:
        write_heartbeat(job, ok, error)
    except Exception as e:  # a heartbeat must never break the job
        print(f"[job_health] heartbeat write failed: {e}", file=sys.stderr)


def playbook_jobs() -> tuple[str, ...]:
    """Playbooks run through run() too (playbook.py), so they get heartbeats like WRAPPED jobs."""
    d = REPO_ROOT / "_meta" / "playbooks"
    return tuple(sorted(p.stem for p in d.glob("*.toml"))) if d.is_dir() else ()


def seed(now: datetime | None = None, hb_dir: Path = HB_DIR, agents: Path = AGENTS) -> list[str]:
    """Give each wrapped job a next_due so a job that never fires shows as missed."""
    made = []
    for job in WRAPPED + playbook_jobs():
        p = hb_dir / f"{job}.json"
        nd = next_due(job, now, agents)
        if p.is_file() or not nd:
            continue
        hb_dir.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"next_due": nd.isoformat(), "seeded": _now(now).isoformat()}, indent=2) + "\n",
                     encoding="utf-8")
        made.append(job)
    return made


# ---- launchd + auth ------------------------------------------------------------------------------
def parse_launchctl(text: str) -> dict:
    """`launchctl list` → {job: {"pid": int|None, "status": int}} for com.s2.* labels."""
    out = {}
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) != 3 or not parts[2].startswith(PREFIX):
            continue
        pid, status, label = parts
        out[label[len(PREFIX):]] = {"pid": None if pid == "-" else int(pid),
                                     "status": int(status) if status.lstrip("-").isdigit() else 0}
    return out


def launchd_problems(listing: dict, agents: Path = AGENTS) -> list[str]:
    out = []
    for job, row in sorted(listing.items()):
        pl = load_plist(job, agents) or {}
        if pl.get("KeepAlive"):
            if row["pid"] is None:
                out.append(f"✖ {job}: not running (KeepAlive job, last exit {row['status']})")
        elif row["status"] != 0:
            out.append(f"✖ {job}: last launchd run exited {row['status']}")
    return out


def _slack_auth(token: str) -> str | None:
    req = urllib.request.Request("https://slack.com/api/auth.test", data=b"",
                                 headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=15) as r:
        d = json.loads(r.read())
    return None if d.get("ok") else d.get("error", "not ok")


def _teamwork_auth() -> str | None:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import teamwork as tw
    tw.from_env().me_id()
    return None


def auth_problems(env=os.environ, slack_fn=_slack_auth, teamwork_fn=_teamwork_auth) -> list[str]:
    out = []
    for name in SLACK_TOKENS:
        tok = env.get(name)
        if not tok:
            continue
        try:
            err = slack_fn(tok)
        except Exception as e:
            err = f"unreachable ({e})"
        if err:
            out.append(f"✖ auth: {name} {err}")
    if env.get("TEAMWORK_API_KEY"):
        try:
            err = teamwork_fn()
        except BaseException as e:  # from_env exits on a missing key
            err = str(e) or type(e).__name__
        if err:
            out.append(f"✖ auth: Teamwork {str(err)[:150]}")
    return out


def problems(env=os.environ) -> list[str]:
    try:
        listing = parse_launchctl(subprocess.run(["launchctl", "list"], capture_output=True, text=True,
                                                 timeout=20).stdout)
    except Exception as e:
        return [f"✖ launchctl list failed: {e}"]
    return launchd_problems(listing) + auth_problems(env)


def load_env(path: Path = REPO_ROOT / ".env") -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def heartbeats(hb_dir: Path = HB_DIR, now: datetime | None = None) -> dict:
    now = _now(now)
    out = {}
    if not hb_dir.is_dir():
        return out
    for p in sorted(hb_dir.glob("*.json")):
        cur = json.loads(p.read_text(encoding="utf-8"))
        nd = cur.get("next_due")
        cur["missed"] = bool(nd and datetime.fromisoformat(nd) < now)
        out[p.stem] = cur
    return out


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "check"
    if cmd == "seed":
        made = seed()
        print("seeded: " + (", ".join(made) or "nothing (all have heartbeats)"))
        return 0
    if cmd == "check":
        load_env()
        lines = problems(os.environ)
        hb = heartbeats()
        lines = [f"⚠ missed: {j} (due {h.get('next_due', '')[:16]})" for j, h in hb.items() if h.get("missed")] + lines
        print("\n".join(lines) or "all jobs healthy")
        return 1 if lines else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
