#!/usr/bin/env python3
"""
drive-link.py — track the linkage between local deliverable files and the Google
Drive Doc/Sheet they were pushed to, and flag when the local copy has drifted.

Registry: _meta/drive-links.json  (repo-relative paths, committed to git)
State:    _meta/.drive-links-state.json  (last drift set reported; gitignored)

Subcommands
  register    Record a local file <-> Drive file linkage
  mark-synced Update the recorded hash after pushing an update to Drive
  check       Report which linked files have changed locally since last push
  list        Show all linkages
  unlink      Remove a linkage
  open        Print (and optionally open) the Drive URL for a local file

Hook subcommands (read hook JSON on stdin, emit hookSpecificOutput JSON)
  hook-post-edit  PostToolUse: nudge when a linked file drifts
  hook-capture    PostToolUse on google-docs MCP creates: nudge to register
  hook-session    SessionStart: surface any outstanding drift

Stdlib only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "_meta" / "drive-links.json"
STATE = ROOT / "_meta" / ".drive-links-state.json"

DOC_URL = "https://docs.google.com/document/d/{id}/edit"
SHEET_URL = "https://docs.google.com/spreadsheets/d/{id}/edit"

SKIP_DIRS = {"_meta", "_inbox", "Archive", "Templates", ".git", "bin", "mcps"}


# --------------------------------------------------------------------------- io


def load_registry() -> list[dict]:
    if not REGISTRY.exists():
        return []
    try:
        data = json.loads(REGISTRY.read_text())
    except Exception:
        return []
    if isinstance(data, dict):  # tolerate {"links": [...]}
        data = data.get("links", [])
    return data if isinstance(data, list) else []


def save_registry(links: list[dict]) -> None:
    links.sort(key=lambda e: e.get("local_path", ""))
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY.write_text(json.dumps(links, indent=2) + "\n")


def load_state() -> dict:
    if not STATE.exists():
        return {}
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {}


def save_state(state: dict) -> None:
    try:
        STATE.write_text(json.dumps(state, indent=2) + "\n")
    except Exception:
        pass


# ----------------------------------------------------------------------- paths


def rel(path: str | Path) -> str:
    """Normalize any path (absolute, relative, ~) to a repo-relative posix path."""
    p = Path(os.path.expanduser(str(path)))
    if not p.is_absolute():
        p = (Path.cwd() / p) if (Path.cwd() / p).exists() else (ROOT / p)
    try:
        p = p.resolve()
    except Exception:
        pass
    try:
        return p.relative_to(ROOT).as_posix()
    except ValueError:
        return p.as_posix()


def abspath(rel_path: str) -> Path:
    p = Path(rel_path)
    return p if p.is_absolute() else ROOT / p


def detect_client(rel_path: str) -> str:
    first = rel_path.split("/")[0]
    return "" if first in SKIP_DIRS or first.startswith("_") else first


def file_hash(path: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 16), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def find(links: list[dict], target: str) -> dict | None:
    r = rel(target)
    for e in links:
        if e.get("local_path") == r:
            return e
    # fall back to basename match so `check "Foo.md"` works from anywhere
    base = Path(r).name.lower()
    matches = [e for e in links if Path(e.get("local_path", "")).name.lower() == base]
    return matches[0] if len(matches) == 1 else None


def infer_kind(drive_id: str, url: str, local_path: str) -> str:
    if "spreadsheets" in (url or ""):
        return "sheet"
    if "/document/" in (url or ""):
        return "doc"
    return "sheet" if Path(local_path).suffix.lower() in {".xlsx", ".csv", ".tsv"} else "doc"


def url_for(entry: dict) -> str:
    if entry.get("drive_url"):
        return entry["drive_url"]
    tmpl = SHEET_URL if entry.get("kind") == "sheet" else DOC_URL
    return tmpl.format(id=entry.get("drive_id", ""))


# ------------------------------------------------------------------- drift core


def drifted(links: list[dict] | None = None, only: list[str] | None = None) -> list[dict]:
    """Return entries whose local file hash differs from the last pushed hash."""
    links = load_registry() if links is None else links
    wanted = {rel(p) for p in only} if only else None
    out = []
    for e in links:
        lp = e.get("local_path", "")
        if wanted is not None and lp not in wanted:
            continue
        if e.get("paused"):
            continue
        p = abspath(lp)
        if not p.exists():
            e = {**e, "status": "missing"}
            out.append(e)
            continue
        h = file_hash(p)
        if h and h != e.get("pushed_sha256"):
            out.append({**e, "status": "changed", "current_sha256": h})
    return out


def drift_line(e: dict) -> str:
    if e.get("status") == "missing":
        return f"  [missing locally] {e['local_path']} -> {url_for(e)}"
    return (
        f"  {e['local_path']}\n"
        f"      {e.get('kind', 'doc')}: {e.get('title') or '(untitled)'} -> {url_for(e)}\n"
        f"      last pushed: {e.get('pushed_at', '?')}"
    )


# -------------------------------------------------------------------- commands


def cmd_register(args) -> int:
    links = load_registry()
    lp = rel(args.local)
    p = abspath(lp)
    if not p.exists():
        print(f"Error: local file not found: {lp}", file=sys.stderr)
        return 1

    drive_id = args.drive_id
    if not drive_id and args.url:
        m = re.search(r"/d/([A-Za-z0-9_-]{10,})", args.url)
        drive_id = m.group(1) if m else None
    if not drive_id:
        print("Error: need --drive-id or a --url containing /d/<id>", file=sys.stderr)
        return 1

    kind = args.kind or infer_kind(drive_id, args.url or "", lp)
    entry = find(links, lp) or {}
    is_new = not entry
    entry.update(
        {
            "local_path": lp,
            "drive_id": drive_id,
            "drive_url": args.url or (SHEET_URL if kind == "sheet" else DOC_URL).format(id=drive_id),
            "kind": kind,
            "title": args.title or entry.get("title") or p.stem,
            "client": args.client or entry.get("client") or detect_client(lp),
            "pushed_sha256": file_hash(p),
            "pushed_at": now(),
        }
    )
    if args.note:
        entry["note"] = args.note
    if is_new:
        links.append(entry)
    save_registry(links)
    print(f"{'Linked' if is_new else 'Updated link'}: {lp}\n  -> {url_for(entry)}")
    return 0


def cmd_mark_synced(args) -> int:
    links = load_registry()
    touched = []
    targets = args.local or [e["local_path"] for e in drifted(links)]
    for t in targets:
        e = find(links, t)
        if not e:
            print(f"Not linked (nothing to mark): {rel(t)}", file=sys.stderr)
            continue
        p = abspath(e["local_path"])
        if not p.exists():
            print(f"Missing locally, skipped: {e['local_path']}", file=sys.stderr)
            continue
        e["pushed_sha256"] = file_hash(p)
        e["pushed_at"] = now()
        touched.append(e["local_path"])
    if touched:
        save_registry(links)
        save_state({})  # drift cleared; let the hook re-report fresh changes
        for t in touched:
            print(f"Marked synced: {t}")
    elif not targets:
        print("Nothing drifted — all linked files match Drive.")
    return 0


def cmd_check(args) -> int:
    d = drifted(only=args.local or None)
    if args.json:
        print(json.dumps(d, indent=2))
        return 1 if d else 0
    if not d:
        print("All linked deliverables are in sync with Drive.")
        return 0
    print(f"{len(d)} linked file(s) changed locally since the last Drive push:\n")
    for e in d:
        print(drift_line(e))
    print("\nPush the updates, then run: s2 drive mark-synced")
    return 1


def cmd_list(args) -> int:
    links = load_registry()
    if args.client:
        links = [e for e in links if (e.get("client", "").lower() == args.client.lower())]
    if args.json:
        print(json.dumps(links, indent=2))
        return 0
    if not links:
        print("No Drive linkages recorded yet.")
        return 0
    stale = {e["local_path"] for e in drifted()}
    by_client: dict[str, list[dict]] = {}
    for e in links:
        by_client.setdefault(e.get("client") or "(unassigned)", []).append(e)
    for client in sorted(by_client):
        print(f"\n{client}")
        for e in by_client[client]:
            flag = " *DRIFTED*" if e["local_path"] in stale else ""
            print(f"  [{e.get('kind', 'doc')}] {e['local_path']}{flag}")
            print(f"      {url_for(e)}")
    print()
    return 0


def cmd_unlink(args) -> int:
    links = load_registry()
    e = find(links, args.local)
    if not e:
        print(f"Not linked: {rel(args.local)}", file=sys.stderr)
        return 1
    links.remove(e)
    save_registry(links)
    print(f"Unlinked: {e['local_path']}")
    return 0


def cmd_open(args) -> int:
    e = find(load_registry(), args.local)
    if not e:
        print(f"Not linked: {rel(args.local)}", file=sys.stderr)
        return 1
    url = url_for(e)
    print(url)
    if not args.print_only:
        subprocess.run(["open", url], check=False)
    return 0


# ----------------------------------------------------------------------- hooks


def emit(event: str, context: str) -> None:
    print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": context}}))


def read_hook() -> dict:
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}


def edited_paths(data: dict) -> list[str]:
    ti = data.get("tool_input") or {}
    paths = []
    for key in ("file_path", "notebook_path", "path"):
        if isinstance(ti.get(key), str):
            paths.append(ti[key])
    for ed in ti.get("edits") or []:
        if isinstance(ed, dict) and isinstance(ed.get("file_path"), str):
            paths.append(ed["file_path"])
    return paths


def cmd_hook_post_edit(args) -> int:
    """Nudge when a linked deliverable drifts. Scoped to the edited file when we
    know it; otherwise (e.g. a Bash-run script that rewrote an .xlsx) full scan."""
    data = read_hook()
    links = load_registry()
    if not links:
        return 0

    touched = edited_paths(data)
    d = drifted(links, only=touched or None) if touched else drifted(links)
    d = [e for e in d if e.get("status") == "changed"]
    if not d:
        return 0

    # Only speak up when the drift set changes, so repeated edits stay quiet.
    state = load_state()
    sig = {e["local_path"]: e.get("current_sha256") for e in d}
    if state.get("reported") == sig:
        return 0
    state["reported"] = sig
    state["reported_at"] = now()
    save_state(state)

    lines = [
        "Drive-linked deliverable changed locally. The Drive copy is now stale:",
        "",
    ]
    for e in d:
        lines.append(f"- {e['local_path']}")
        lines.append(f"  {e.get('kind', 'doc')} \"{e.get('title')}\": {url_for(e)}")
    lines += [
        "",
        "Ask the user whether to push the update to Drive now. If he says yes:",
        "- doc: mcp__google-docs__replaceDocumentWithMarkdown (documentId above)",
        "- sheet: mcp__google-docs__writeSpreadsheet / batchWrite on that spreadsheetId",
        "Then run: ./bin/s2 drive mark-synced \"<local_path>\"",
        "If he declines, drop it — do not re-raise this in the same session.",
    ]
    emit("PostToolUse", "\n".join(lines))
    return 0


CREATE_TOOLS = (
    "createDocument",
    "createSpreadsheet",
    "createDocumentFromTemplate",
    "copyFile",
)


def cmd_hook_capture(args) -> int:
    """After a google-docs MCP create/write call, remind Claude to record the link."""
    data = read_hook()
    tool = data.get("tool_name", "") or ""
    blob = json.dumps(data.get("tool_response") or data.get("tool_result") or "")
    m = re.search(r"(?:documentId|spreadsheetId|fileId|\"id\")\"?\s*[:=]\s*\"([A-Za-z0-9_-]{20,})\"", blob)
    if not m:
        m = re.search(r"/d/([A-Za-z0-9_-]{20,})", blob)
    if not m:
        return 0
    drive_id = m.group(1)

    known = {e.get("drive_id") for e in load_registry()}
    if drive_id in known:
        return 0

    is_sheet = "preadsheet" in tool or "preadsheet" in blob[:400]
    kind = "sheet" if is_sheet else "doc"
    emit(
        "PostToolUse",
        (
            f"A Drive {kind} was just created/updated (id: {drive_id}) and is not in the "
            "linkage registry. If it came from a local file in this repo, record the "
            "linkage now so future local edits prompt a re-push:\n\n"
            f'  ./bin/s2 drive register --local "<repo-relative local file>" '
            f'--drive-id {drive_id} --kind {kind}\n\n'
            "Skip this only if there is no local source file (ad-hoc doc)."
        ),
    )
    return 0


def cmd_hook_session(args) -> int:
    d = [e for e in drifted() if e.get("status") == "changed"]
    if not d:
        return 0
    lines = [f"{len(d)} Drive-linked deliverable(s) have local changes not yet pushed to Drive:"]
    for e in d[:12]:
        lines.append(f"- {e['local_path']} -> {url_for(e)}")
    if len(d) > 12:
        lines.append(f"- ...and {len(d) - 12} more (./bin/s2 drive check)")
    lines.append("Mention this if the user's work touches these files; otherwise do not act on it.")
    emit("SessionStart", "\n".join(lines))
    return 0


# ------------------------------------------------------------------------- cli


def main() -> int:
    ap = argparse.ArgumentParser(prog="drive-link", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("register", help="record a local file <-> Drive file linkage")
    p.add_argument("--local", required=True)
    p.add_argument("--drive-id")
    p.add_argument("--url")
    p.add_argument("--kind", choices=["doc", "sheet"])
    p.add_argument("--title")
    p.add_argument("--client")
    p.add_argument("--note")
    p.set_defaults(func=cmd_register)

    p = sub.add_parser("mark-synced", help="update recorded hash after pushing to Drive")
    p.add_argument("local", nargs="*")
    p.set_defaults(func=cmd_mark_synced)

    p = sub.add_parser("check", help="report linked files that changed locally")
    p.add_argument("local", nargs="*")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("list", help="show all linkages")
    p.add_argument("--client")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("unlink", help="remove a linkage")
    p.add_argument("local")
    p.set_defaults(func=cmd_unlink)

    p = sub.add_parser("open", help="print/open the Drive URL for a local file")
    p.add_argument("local")
    p.add_argument("--print-only", action="store_true")
    p.set_defaults(func=cmd_open)

    for name, fn in (
        ("hook-post-edit", cmd_hook_post_edit),
        ("hook-capture", cmd_hook_capture),
        ("hook-session", cmd_hook_session),
    ):
        p = sub.add_parser(name)
        p.set_defaults(func=fn)

    args = ap.parse_args()
    if not getattr(args, "func", None):
        ap.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # hooks must never break the session
        if len(sys.argv) > 1 and sys.argv[1].startswith("hook-"):
            print(f"drive-link hook error: {exc}", file=sys.stderr)
            sys.exit(0)
        raise
