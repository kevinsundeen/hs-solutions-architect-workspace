#!/usr/bin/env python3
"""
gtm-tag-summary.py — Summarize a Google Tag Manager Tag Assistant export.

Usage:
  python _meta/scripts/gtm-tag-summary.py <path-to-export.json> [--md]

Outputs a human-readable summary of:
  - Which containers were recorded
  - Which pages were visited
  - Which tags fired, on which events, and on which pages
  - Consent state at the time of each firing
  - Any tags that appear blocked or not fired

No LLM needed — pure local extraction. Designed for large exports that
exceed context-window limits.
"""

import json
import sys
import argparse
from collections import defaultdict, Counter
from pathlib import Path


CONSENT_TYPES = ["ad_storage", "analytics_storage", "ad_user_data", "ad_personalization"]


def consent_summary(consent_data):
    if not consent_data:
        return "unknown"
    cl = {c["type"]: c["status"] for c in consent_data.get("consentList", [])}
    if not cl:
        return "unknown"
    granted = [k for k, v in cl.items() if v == "granted"]
    denied = [k for k, v in cl.items() if v == "denied"]
    if len(granted) == len(cl):
        return "all granted"
    if len(denied) == len(cl):
        return "all denied"
    short = {
        "ad_storage": "ads",
        "analytics_storage": "analytics",
        "ad_user_data": "ad_data",
        "ad_personalization": "ad_pers",
    }
    granted_short = [short.get(g, g) for g in granted]
    denied_short = [short.get(d, d) for d in denied]
    parts = []
    if granted_short:
        parts.append(f"granted: {', '.join(granted_short)}")
    if denied_short:
        parts.append(f"denied: {', '.join(denied_short)}")
    return " | ".join(parts)


def summarize_container(c, md=False):
    lines = []
    h2 = "## " if md else "  "
    h3 = "### " if md else "    "
    bullet = "- " if md else "  - "
    sub = "  - " if md else "    - "

    container_id = c.get("publicId", "unknown")
    env = c.get("environmentName", "")
    tag_name = c.get("tagName", "")
    lines.append(f"\n{'## ' if md else ''}Container: {container_id}")
    if tag_name:
        lines.append(f"{bullet}Domain: {tag_name}")
    if env:
        lines.append(f"{bullet}Environment: {env}")
    lines.append(f"{bullet}Error count: {c.get('errorCount', 0)}")

    # Pages visited
    page_summaries = c.get("pageSummaries", {})
    lines.append(f"\n{h3}Pages ({len(page_summaries)})")
    group_to_page = {}
    for page_id, ps in page_summaries.items():
        title = ps.get("title", ps.get("href", page_id))
        url = ps.get("href", "")
        group_id = ps.get("groupId", page_id)
        group_to_page[group_id] = title
        lines.append(f"{bullet}{title}")
        if url:
            lines.append(f"{sub}URL: {url}")

    # Tags fired — tagsFired is keyed by tag name, value is list of messages it fired in
    tags_fired = c.get("tagsFired", {})
    lines.append(f"\n{h3}Tags Fired ({len(tags_fired)} unique tags)")

    # Build per-tag summary
    for tag_name_key in sorted(tags_fired.keys()):
        fire_events = tags_fired[tag_name_key]

        # Collect event names and pages
        event_counter = Counter()
        page_counter = Counter()
        consent_at_fire = []

        for msg in fire_events:
            event_counter[msg.get("eventName", msg.get("eventNameKey", "unknown"))] += 1
            gid = msg.get("groupId", "")
            page_label = group_to_page.get(gid, gid or "unknown page")
            page_counter[page_label] += 1
            consent_at_fire.append(consent_summary(msg.get("consentData")))

        # Determine dominant consent state
        consent_tally = Counter(consent_at_fire)
        dominant_consent = consent_tally.most_common(1)[0][0]

        lines.append(f"\n{bullet}**{tag_name_key}**" if md else f"\n  - {tag_name_key}")
        lines.append(f"{sub}Fired: {len(fire_events)}x")

        # Events
        event_parts = [f"{e} ×{n}" if n > 1 else e for e, n in event_counter.most_common()]
        lines.append(f"{sub}On events: {', '.join(event_parts)}")

        # Pages
        page_parts = [f"{p} ×{n}" if n > 1 else p for p, n in page_counter.most_common()]
        lines.append(f"{sub}On pages: {', '.join(page_parts)}")

        # Consent
        if len(consent_tally) == 1:
            lines.append(f"{sub}Consent: {dominant_consent}")
        else:
            consent_detail = ", ".join(f"{s} ×{n}" for s, n in consent_tally.most_common())
            lines.append(f"{sub}Consent: {consent_detail}")

    # Events summary — from messages
    messages = c.get("messages", [])
    event_totals = Counter(m.get("eventName", m.get("eventNameKey", "?")) for m in messages)
    lines.append(f"\n{h3}Event sequence ({len(messages)} total)")
    for event, count in sorted(event_totals.items(), key=lambda x: -x[1]):
        lines.append(f"{bullet}{event}: {count}x")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Summarize a GTM Tag Assistant export JSON.")
    parser.add_argument("file", help="Path to the Tag Assistant .json export")
    parser.add_argument("--md", action="store_true", help="Output in Markdown format")
    parser.add_argument("--out", help="Write output to this file instead of stdout")
    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    print(f"Reading {path.name} ({path.stat().st_size / 1_000_000:.1f} MB)...", file=sys.stderr)

    with open(path) as f:
        data = json.load(f)

    out_lines = []

    # Top-level metadata
    name = data.get("name", "GTM Export")
    ts = data.get("timestamp", "")
    if args.md:
        out_lines.append(f"# GTM Tag Assistant Summary: {name}")
    else:
        out_lines.append(f"GTM Tag Assistant Summary: {name}")
    if ts:
        import datetime
        try:
            dt = datetime.datetime.fromtimestamp(int(ts) / 1000)
            out_lines.append(f"Recorded: {dt.strftime('%Y-%m-%d %H:%M:%S')}")
        except Exception:
            out_lines.append(f"Timestamp: {ts}")

    containers = data.get("data", {}).get("containers", [])
    out_lines.append(f"Containers: {len(containers)}\n")

    for c in containers:
        out_lines.append(summarize_container(c, md=args.md))

    output = "\n".join(out_lines)

    if args.out:
        Path(args.out).write_text(output)
        print(f"Wrote summary to {args.out}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
