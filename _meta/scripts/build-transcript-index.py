#!/usr/bin/env python3
"""
Build a workspace-wide transcript index.

Writes two files to _meta/:
  transcript-index.jsonl  — one JSON object per line, machine-readable
  transcript-index.md     — human-readable markdown table

Each entry:
  { date, client, topic, filename, path, size_chars, mtime_iso }

Usage:
  python build-transcript-index.py [--root /path/to/S2]
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


SKIP = {"_meta", "_inbox", "Archive", "Templates", "bin", "clients",
        "s2-ui", "node_modules", ".git", ".claude", "OCT 27"}


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def transcript_dirs(root: Path):
    """Yield (client_name, transcripts_dir) for all active clients."""
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        if d.name.startswith(".") or d.name in SKIP:
            continue
        if not (d / "context.md").exists():
            continue
        # Some clients capitalise "Transcripts"
        for tname in ("transcripts", "Transcripts"):
            td = d / tname
            if td.is_dir():
                yield d.name, td
                break


def parse_topic(filename: str) -> str:
    stem = Path(filename).stem
    # Strip leading date segment (YYYY-MM-DD_)
    stem = re.sub(r"^\d{4}-\d{2}-\d{2}_", "", stem)
    # Strip leading client slug (word(s) before next underscore group)
    stem = re.sub(r"^[a-z0-9-]+_", "", stem, count=1)
    return stem.replace("-", " ").title() or Path(filename).stem


def build_entries(root: Path) -> list[dict]:
    entries = []
    for client, td in transcript_dirs(root):
        for tx in sorted(td.glob("*.txt"), reverse=True):
            if tx.name == "transcript-index.md":
                continue
            stat = tx.stat()
            mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
            # Infer date from filename prefix; fall back to mtime
            m = re.match(r"(\d{4}-\d{2}-\d{2})", tx.name)
            date_str = m.group(1) if m else mtime.strftime("%Y-%m-%d")
            entries.append({
                "date": date_str,
                "client": client,
                "topic": parse_topic(tx.name),
                "filename": tx.name,
                "path": str(tx.relative_to(root)),
                "size_chars": stat.st_size,
                "mtime_iso": mtime.strftime("%Y-%m-%dT%H:%M:%SZ"),
            })
    entries.sort(key=lambda e: e["date"], reverse=True)
    return entries


def write_jsonl(entries: list[dict], out: Path) -> None:
    with open(out, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


def write_md(entries: list[dict], out: Path) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# Transcript Index",
        f"*Last Updated: {now} — {len(entries)} transcripts across {len(set(e['client'] for e in entries))} clients*",
        "",
        "| Date | Client | Topic | File |",
        "|------|--------|-------|------|",
    ]
    for e in entries:
        lines.append(f"| {e['date']} | {e['client']} | {e['topic']} | `{e['filename']}` |")
    lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    root = repo_root()
    if "--root" in sys.argv:
        idx = sys.argv.index("--root")
        root = Path(sys.argv[idx + 1]).resolve()

    meta = root / "_meta"
    entries = build_entries(root)

    write_jsonl(entries, meta / "transcript-index.jsonl")
    write_md(entries, meta / "transcript-index.md")

    print(f"[transcript-index] {len(entries)} transcripts indexed across "
          f"{len(set(e['client'] for e in entries))} clients → _meta/transcript-index.jsonl + .md")


if __name__ == "__main__":
    main()
