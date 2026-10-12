"""
HubSpot Schema Summarizer (CRM v3 API JSON)
--------------------------------------------
Token-safe reader for schema JSON pulled by grab_schema.py. Prints, per object:
property count by group/type, which properties are required/calculated/custom,
pipeline stage names, and association labels — without loading the full
property-definition JSON (options, validation rules, etc.) into context.

Use it to diff a portal's schema against a spec or compare two portals without
loading megabytes of raw property JSON into context.

Usage:
    python parse_schema.py                       # scans ./schema_output
    python parse_schema.py ./my_schema           # scans a given directory
    python parse_schema.py path/to/deals__schema.json
    python parse_schema.py --custom-only         # only show non-HubSpot-default properties

Read-only. Never calls the API — operates on already-exported JSON files.
"""
import argparse
import glob
import json
import os


def summarize_properties(properties: list[dict], custom_only: bool) -> None:
    if custom_only:
        properties = [p for p in properties if not p.get("hubspotDefined")]

    by_group = {}
    for p in properties:
        group = p.get("groupName", "(none)")
        by_group.setdefault(group, []).append(p)

    print(f"  PROPERTIES: {len(properties)} total, {len(by_group)} group(s)")
    for group, props in sorted(by_group.items(), key=lambda kv: -len(kv[1])):
        print(f"    [{group}] ({len(props)})")
        for p in props:
            flags = []
            if p.get("required"):
                flags.append("required")
            if p.get("calculated"):
                flags.append("calculated")
            if not p.get("hubspotDefined"):
                flags.append("custom")
            flag_str = f"  ({', '.join(flags)})" if flags else ""
            opts = p.get("options") or []
            opt_str = f"  [{len(opts)} options]" if opts else ""
            print(f"      - {p.get('name')}: {p.get('type')}/{p.get('fieldType')}{flag_str}{opt_str}")


def summarize_pipelines(pipelines: list[dict]) -> None:
    if not pipelines:
        return
    print(f"  PIPELINES: {len(pipelines)}")
    for pl in pipelines:
        stages = pl.get("stages", [])
        stage_names = ", ".join(str(s.get("label") or s.get("id") or "?") for s in stages)
        print(f"    - {pl.get('label')} [{pl.get('id')}]: {stage_names}")


def summarize_associations(associations: dict) -> None:
    if not associations:
        return
    print(f"  ASSOCIATION LABELS:")
    for to_object, labels in associations.items():
        label_names = ", ".join(str(l.get("label") or l.get("typeId") or "?") for l in labels)
        print(f"    - -> {to_object}: {label_names}")


def summarize(path: str, custom_only: bool) -> None:
    d = json.load(open(path))
    print("\n" + "=" * 78)
    print(f"{d.get('objectType')}")
    summarize_properties(d.get("properties", []), custom_only)
    summarize_pipelines(d.get("pipelines", []))
    summarize_associations(d.get("associationLabels", {}))


def main():
    ap = argparse.ArgumentParser(description="Summarize HubSpot schema JSON (properties/pipelines/associations).")
    ap.add_argument("target", nargs="?", default="./schema_output",
                    help="Directory of *__schema.json files, or a single .json file (default: ./schema_output)")
    ap.add_argument("--custom-only", action="store_true",
                    help="Only show properties that aren't HubSpot-default.")
    args = ap.parse_args()

    if os.path.isfile(args.target):
        files = [args.target]
    else:
        files = sorted(glob.glob(os.path.join(args.target, "*__schema.json")))
    if not files:
        print(f"No schema JSON found at: {args.target}")
        return
    for f in files:
        summarize(f, args.custom_only)


if __name__ == "__main__":
    main()
