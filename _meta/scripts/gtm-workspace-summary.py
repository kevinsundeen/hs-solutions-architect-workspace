#!/usr/bin/env python3
"""
gtm-workspace-summary.py — Summarize a GTM workspace/container export.

Usage:
  python _meta/scripts/gtm-workspace-summary.py <path-to-workspace.json> [--md] [--out <file>]

Outputs a human-readable summary of the container config:
  - Container metadata
  - Tags (grouped by folder), with firing triggers + consent requirements
  - Paused and flagged-for-removal tags
  - Triggers (type, event condition)
  - Variables (type)
  - Custom templates

No LLM needed. Safe for large workspace exports.
"""

import json
import sys
import argparse
from collections import defaultdict
from pathlib import Path


# Human-friendly names for GTM tag type codes
TAG_TYPE_LABELS = {
    "html": "Custom HTML",
    "gaawe": "GA4 Event",
    "awct": "Google Ads Conversion",
    "ua": "Universal Analytics",
    "googtag": "Google Tag",
    "img": "Custom Image",
    "sp": "Scrolldepth",
    "gclidw": "Conversion Linker",
    "bzi": "LinkedIn Insight Tag",
    "fls": "Floodlight",
    "adwords_remarketing": "Google Ads Remarketing",
    "bis": "Bing Ads",
    "bb": "Bizible",
    "gaawc": "Google Analytics (GA4 Config)",
}

TRIGGER_TYPE_LABELS = {
    "PAGEVIEW": "Page View",
    "DOM_READY": "DOM Ready",
    "WINDOW_LOADED": "Window Loaded",
    "CUSTOM_EVENT": "Custom Event",
    "CLICK": "All Clicks",
    "LINK_CLICK": "Link Click",
    "FORM_SUBMISSION": "Form Submit",
    "ELEMENT_VISIBILITY": "Element Visibility",
    "SCROLL_DEPTH": "Scroll Depth",
    "HISTORY_CHANGE": "History Change",
    "TIMER": "Timer",
    "TRIGGER_GROUP": "Trigger Group",
    "ALWAYS": "All Pages (Always)",
    "CONSENT_INIT": "Consent Init",
    "SERVER_SIDE_TAG_MONITOR": "Tag Monitor",
    "JAVASCRIPT_ERROR": "JS Error",
}


def tag_type_label(t):
    return TAG_TYPE_LABELS.get(t, t)


def trigger_type_label(t):
    return TRIGGER_TYPE_LABELS.get(t, t)


def get_param(params, key):
    for p in params or []:
        if p.get("key") == key:
            return p.get("value", "")
    return ""


def consent_label(tag):
    cs = tag.get("consentSettings", {})
    status = cs.get("consentStatus", "")
    if status == "NOT_SET":
        return "no consent check"
    if status == "NOT_NEEDED":
        return "no consent needed"
    ct = cs.get("consentType", {})
    types = [item.get("value", "") for item in ct.get("list", [])]
    if not types and ct.get("value"):
        types = [ct["value"]]
    if types:
        return f"requires: {', '.join(types)}"
    return status.lower() if status else ""


def trigger_condition(trigger):
    """Extract a short human-readable firing condition."""
    ttype = trigger.get("type", "")
    if ttype == "CUSTOM_EVENT":
        filters = trigger.get("customEventFilter", [])
        for f in filters:
            params = f.get("parameter", [])
            val = next((p["value"] for p in params if p.get("key") == "arg1"), "")
            if val:
                return f'event = "{val}"'
        return "custom event"
    if ttype in ("PAGEVIEW", "DOM_READY", "WINDOW_LOADED", "ALWAYS", "CONSENT_INIT"):
        filters = trigger.get("filter", [])
        if not filters:
            return "all pages"
        parts = []
        for f in filters:
            params = f.get("parameter", [])
            field = next((p["value"] for p in params if p.get("key") == "arg0"), "")
            val = next((p["value"] for p in params if p.get("key") == "arg1"), "")
            ftype = f.get("type", "EQUALS")
            op = {"EQUALS": "=", "CONTAINS": "contains", "STARTS_WITH": "starts with",
                  "ENDS_WITH": "ends with", "MATCHES_REGEX": "~"}.get(ftype, ftype)
            parts.append(f"{field} {op} {val}")
        return " AND ".join(parts)
    if ttype == "CLICK":
        filters = trigger.get("filter", [])
        if not filters:
            return "all clicks"
        parts = []
        for f in filters:
            params = f.get("parameter", [])
            field = next((p["value"] for p in params if p.get("key") == "arg0"), "")
            val = next((p["value"] for p in params if p.get("key") == "arg1"), "")
            parts.append(f"{field} = {val}")
        return " AND ".join(parts)
    if ttype == "ELEMENT_VISIBILITY":
        sel = get_param(trigger.get("parameter", []), "selector")
        return f"element: {sel}" if sel else "element visibility"
    if ttype == "SCROLL_DEPTH":
        pct = get_param(trigger.get("parameter", []), "verticalThresholdUnits")
        return f"scroll {pct}" if pct else "scroll depth"
    if ttype == "TIMER":
        interval = get_param(trigger.get("parameter", []), "interval")
        return f"every {interval}ms" if interval else "timer"
    return ""


def summarize_workspace(data, md=False):
    lines = []
    h2 = "## " if md else ""
    h3 = "### " if md else "  "
    bullet = "- " if md else "  - "
    sub = "  - " if md else "    - "
    bold = lambda s: f"**{s}**" if md else s

    cv = data.get("containerVersion", {})
    container = cv.get("container", {})
    tags = cv.get("tag", [])
    triggers = cv.get("trigger", [])
    variables = cv.get("variable", [])
    folders = cv.get("folder", [])
    builtin_vars = cv.get("builtInVariable", [])
    custom_templates = cv.get("customTemplate", [])

    # Index lookups
    trig_map = {t["triggerId"]: t for t in triggers}
    folder_map = {f["folderId"]: f["name"] for f in folders}

    export_time = data.get("exportTime", "")
    container_name = container.get("name", "unknown")
    public_id = container.get("publicId", "")
    version_id = cv.get("containerVersionId", "")

    if md:
        lines.append(f"# GTM Workspace Summary: {public_id} — {container_name}")
    else:
        lines.append(f"GTM Workspace Summary: {public_id} — {container_name}")
    if export_time:
        lines.append(f"Exported: {export_time}")
    if version_id:
        lines.append(f"Version: {version_id}")
    lines.append(f"Tags: {len(tags)}  |  Triggers: {len(triggers)}  |  Variables: {len(variables)}")

    # ── TAGS ──────────────────────────────────────────────────────────────────
    paused_tags = [t for t in tags if t.get("paused")]
    active_tags = [t for t in tags if not t.get("paused")]

    # Group by folder
    by_folder = defaultdict(list)
    for t in active_tags:
        folder_id = t.get("parentFolderId", "__none__")
        folder_label = folder_map.get(folder_id, "Unassigned") if folder_id != "__none__" else "Unassigned"
        by_folder[folder_label].append(t)

    lines.append(f"\n{h2}Active Tags ({len(active_tags)})")
    for folder_label in sorted(by_folder.keys()):
        folder_tags = by_folder[folder_label]
        lines.append(f"\n{h3}{folder_label} ({len(folder_tags)})")
        for t in sorted(folder_tags, key=lambda x: x.get("name", "")):
            name = t.get("name", "unnamed")
            ttype = tag_type_label(t.get("type", ""))
            firing_ids = t.get("firingTriggerId") or []
            blocking_ids = t.get("blockingTriggerId") or []
            firing_names = [trig_map[i]["name"] for i in firing_ids if i in trig_map]
            blocking_names = [trig_map[i]["name"] for i in blocking_ids if i in trig_map]
            consent = consent_label(t)
            firing_option = t.get("tagFiringOption", "")

            lines.append(f"\n{bullet}{bold(name)}")
            lines.append(f"{sub}Type: {ttype}")
            if firing_names:
                lines.append(f"{sub}Fires on: {', '.join(firing_names)}")
            else:
                lines.append(f"{sub}Fires on: (no trigger assigned)")
            if blocking_names:
                lines.append(f"{sub}Blocked by: {', '.join(blocking_names)}")
            if consent:
                lines.append(f"{sub}Consent: {consent}")
            if firing_option and firing_option not in ("ONCE_PER_EVENT", ""):
                lines.append(f"{sub}Firing: {firing_option.replace('_', ' ').lower()}")

    # ── PAUSED TAGS ───────────────────────────────────────────────────────────
    if paused_tags:
        lines.append(f"\n{h2}Paused Tags ({len(paused_tags)})")
        for t in sorted(paused_tags, key=lambda x: x.get("name", "")):
            name = t.get("name", "unnamed")
            ttype = tag_type_label(t.get("type", ""))
            folder_id = t.get("parentFolderId", "")
            folder_label = folder_map.get(folder_id, "") if folder_id else ""
            folder_str = f" [{folder_label}]" if folder_label else ""
            lines.append(f"{bullet}{name} ({ttype}){folder_str}")

    # ── TRIGGERS ──────────────────────────────────────────────────────────────
    lines.append(f"\n{h2}Triggers ({len(triggers)})")

    # Group triggers by type
    trig_by_type = defaultdict(list)
    for t in triggers:
        trig_by_type[trigger_type_label(t.get("type", ""))].append(t)

    for ttype in sorted(trig_by_type.keys()):
        group = trig_by_type[ttype]
        lines.append(f"\n{h3}{ttype} ({len(group)})")
        for t in sorted(group, key=lambda x: x.get("name", "")):
            condition = trigger_condition(t)
            cond_str = f" — {condition}" if condition else ""
            lines.append(f"{bullet}{t.get('name', 'unnamed')}{cond_str}")

    # ── VARIABLES ─────────────────────────────────────────────────────────────
    lines.append(f"\n{h2}Variables ({len(variables)} custom + {len(builtin_vars)} built-in)")

    var_type_labels = {
        "jsm": "Custom JS",
        "v": "Data Layer Variable",
        "k": "1st Party Cookie",
        "c": "Constant",
        "r": "Regex Table",
        "smm": "Lookup Table",
        "gas": "GA Settings",
        "u": "URL",
        "e": "Auto Event Variable",
        "ctv": "Container Version",
        "dbg": "Debug Mode",
        "f": "HTTP Referrer",
        "j": "JavaScript Variable",
        "remm": "Random Number",
    }

    var_by_type = defaultdict(list)
    for v in variables:
        label = var_type_labels.get(v.get("type", ""), v.get("type", "unknown"))
        var_by_type[label].append(v.get("name", "unnamed"))

    for vtype in sorted(var_by_type.keys()):
        names = var_by_type[vtype]
        lines.append(f"{bullet}{vtype} ({len(names)}): {', '.join(sorted(names))}")

    if builtin_vars:
        lines.append(f"{bullet}Built-in: {', '.join(v.get('name','') for v in builtin_vars)}")

    # ── CUSTOM TEMPLATES ──────────────────────────────────────────────────────
    if custom_templates:
        lines.append(f"\n{h2}Custom Templates ({len(custom_templates)})")
        for ct in custom_templates:
            lines.append(f"{bullet}{ct.get('name', 'unnamed')}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Summarize a GTM workspace/container export JSON.")
    parser.add_argument("file", help="Path to the GTM workspace export .json")
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

    output = summarize_workspace(data, md=args.md)

    if args.out:
        Path(args.out).write_text(output)
        print(f"Wrote summary to {args.out}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
