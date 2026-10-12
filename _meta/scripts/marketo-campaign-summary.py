#!/usr/bin/env python3
"""
marketo-campaign-summary.py
cross-client utility

Parses a Marketo Smart Campaign JSON export (combined flow + smart list format,
or flow-only) and prints a readable plain-text summary of triggers, filters,
and flow steps. No LLM, no API calls.

Usage:
  python marketo-campaign-summary.py campaign-12345-full.json
  python marketo-campaign-summary.py campaign-12345-full.json --md     # markdown output
  python marketo-campaign-summary.py campaign-12345-full.json --out summary.md

Input: JSON exported via the browser console hack documented in
  _meta/export-marketo-campaign-to-json.md
"""

import argparse
import json
import sys
from pathlib import Path


# ── Helpers ────────────────────────────────────────────────────────────────────

def _short_name(full_name: str) -> str:
    """Strip program prefix from asset names. 'program.Campaign Name' → 'Campaign Name'
    Marketo tokens ({{...}}) are returned unchanged."""
    if "{{" in full_name:
        return full_name
    return full_name.split(".", 1)[-1].strip() if "." in full_name else full_name


def _condition_str(cond: dict) -> str | None:
    """Render a single condition as a short string. Returns None if empty/unconfigured."""
    display = cond.get("displayName") or cond.get("name", "")
    op = cond.get("op", "")
    vals = cond.get("val", [])

    # Skip system/unconfigured conditions
    if not op and not vals:
        return None
    if display in ("Date of Activity", "Min. Number of Times") and not op:
        return None

    val_strs = [_short_name(str(v)) for v in vals if v is not None]
    val_part = ", ".join(f'"{v}"' for v in val_strs) if val_strs else ""

    parts = [display]
    if op:
        parts.append(op)
    if val_part:
        parts.append(val_part)
    return " ".join(parts)


def _render_conditions(conditions: list[dict]) -> list[str]:
    """Return list of non-empty condition strings for a trigger/filter."""
    out = []
    for c in conditions:
        s = _condition_str(c)
        if s:
            out.append(s)
    return out


# ── Smart List ─────────────────────────────────────────────────────────────────

def render_smart_list(smart_list: dict, md: bool) -> list[str]:
    metas = smart_list.get("smartCampaignSmartlistMetas", [])
    match_type = smart_list.get("smartCampaignRuleMatchType", "all").upper()
    custom_logic = smart_list.get("smartCampaignCustomRuleLogic", "")

    triggers = [m for m in metas if m.get("trigger")]
    filters  = [m for m in metas if not m.get("trigger")]

    lines = []
    H2 = "## " if md else ""
    H3 = "### " if md else ""
    BOLD = "**" if md else ""

    lines.append(f"{H2}SMART LIST")
    lines.append("")

    # Triggers
    if triggers:
        lines.append(f"{H3}TRIGGERS  (contact qualifies if ANY trigger fires)")
        for item in sorted(triggers, key=lambda x: x.get("order", 0)):
            name = item.get("displayName") or item.get("name", "")
            conds = _render_conditions(item.get("conditions", []))
            if md:
                lines.append(f"- **{name}**")
                for c in conds:
                    lines.append(f"  - {c}")
            else:
                lines.append(f"  {item.get('order', '?')}. {name}")
                for c in conds:
                    lines.append(f"       {c}")
        lines.append("")

    # Filters
    if filters:
        logic_note = f"custom logic: {custom_logic}" if custom_logic else f"all must match ({match_type})"
        lines.append(f"{H3}FILTERS  ({logic_note})")
        for item in sorted(filters, key=lambda x: x.get("order", 0)):
            name = item.get("displayName") or item.get("name", "")
            conds = _render_conditions(item.get("conditions", []))
            if md:
                lines.append(f"- **{name}**")
                for c in conds:
                    lines.append(f"  - {c}")
            else:
                lines.append(f"  {item.get('order', '?')}. {name}")
                for c in conds:
                    lines.append(f"       {c}")
        lines.append("")

    if not triggers and not filters:
        lines.append("  (no smart list rules configured)")
        lines.append("")

    return lines


# ── Flow ───────────────────────────────────────────────────────────────────────

def render_flow_step(step: dict, md: bool) -> list[str]:
    order = step.get("order", "?")
    step_type = step.get("displayName") or step.get("name", "")
    actions = step.get("actions", [])
    lines = []

    if md:
        lines.append(f"**{order}. {step_type}**")
    else:
        lines.append(f"  {order}. {step_type}")

    for action in actions:
        if action.get("doNothing") and not action.get("condition"):
            continue

        attr = action.get("val") or action.get("displayName") or ""
        attr = _short_name(str(attr)) if attr else ""

        # Resolve new value from options
        new_val = None
        for opt in (action.get("options") or []):
            if opt.get("name") == "New Value":
                new_val = opt.get("val")
                break

        # Choice condition (if/unless on a flow step)
        cond = action.get("condition")
        cond_str = None
        if cond:
            cond_name = cond.get("displayName") or cond.get("name", "")
            cond_op = cond.get("op", "")
            cond_vals = cond.get("val", [])
            cond_val_str = ", ".join(
                f'"{_short_name(str(v))}"' for v in cond_vals if v is not None
            )
            cond_str = f"IF {cond_name} {cond_op} {cond_val_str}".strip()

        # Build the line
        if new_val is not None:
            new_val_display = _short_name(str(new_val))
            line = f'       {attr} → "{new_val_display}"'
        elif attr:
            line = f"       {attr}"
        else:
            continue

        if cond_str:
            line = f"       [{cond_str}]  {line.strip()}"

        if md:
            lines.append(f"  - {line.strip()}")
        else:
            lines.append(line)

    return lines


def render_flow(flow: dict, md: bool) -> list[str]:
    metas = flow.get("smartCampaignFlowMetas", [])
    lines = []
    H2 = "## " if md else ""

    lines.append(f"{H2}FLOW")
    lines.append("")

    if not metas:
        lines.append("  (no flow steps)")
        lines.append("")
        return lines

    for step in sorted(metas, key=lambda x: x.get("order", 0)):
        lines.extend(render_flow_step(step, md))
        lines.append("")

    return lines


# ── Main ───────────────────────────────────────────────────────────────────────

def summarize(data: dict, md: bool) -> str:
    # Support both combined format {campaignId, flow, smartList} and flow-only
    if "flow" in data and "campaignId" in data:
        flow = data["flow"]
        smart_list = data.get("smartList")
        campaign_id = data["campaignId"]
    else:
        flow = data
        smart_list = None
        campaign_id = str(data.get("Id", "?"))

    name = _short_name(flow.get("Name", "Unknown Campaign"))
    is_active = "Yes" if flow.get("IsActive") else "No"
    parent = flow.get("smartCampaignParentProgramName", "")

    lines = []
    SEP = "---" if md else ("─" * 60)
    H1 = "# " if md else ""

    lines.append(f"{H1}CAMPAIGN: {name}")
    if parent:
        lines.append(f"Program: {_short_name(parent)}")
    lines.append(f"ID: {campaign_id}  |  Active: {is_active}")
    lines.append("")
    lines.append(SEP)
    lines.append("")

    if smart_list:
        lines.extend(render_smart_list(smart_list, md))
        lines.append(SEP)
        lines.append("")

    lines.extend(render_flow(flow, md))

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Render a Marketo campaign export as a readable summary"
    )
    parser.add_argument("json_file", help="Path to campaign JSON export")
    parser.add_argument("--md", action="store_true", help="Output as markdown")
    parser.add_argument("--out", help="Write output to file instead of stdout")
    args = parser.parse_args()

    path = Path(args.json_file)
    if not path.exists():
        print(f"[ERROR] File not found: {path}", file=sys.stderr)
        sys.exit(1)

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    output = summarize(data, md=args.md)

    if args.out:
        out_path = Path(args.out)
        out_path.write_text(output, encoding="utf-8")
        print(f"Written to {out_path}")
    else:
        print(output)


if __name__ == "__main__":
    main()
