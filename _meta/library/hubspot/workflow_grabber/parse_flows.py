"""
HubSpot Flow Summarizer (v4 API JSON)
-------------------------------------
Token-safe reader for workflow JSON pulled by grab_workflows.py. Prints, per flow:
enrollment type + re-enrollment, the inline enrollment property filters, and every
action — with property-set actions rendered as `set <prop> = <value>`.

Use it to diff what a set of workflows actually does against a spec without loading
10-20 MB of raw flow JSON into context.

Usage:
    python parse_flows.py                      # scans ./workflows_output
    python parse_flows.py ./my_workflows       # scans a given directory
    python parse_flows.py path/to/one_flow.json

Read-only. Never calls the API — operates on already-exported JSON files.
"""
import argparse
import glob
import json
import os


def walk_filters(node, out):
    """Recursively pull property-filter leaves into readable strings."""
    if isinstance(node, dict):
        if node.get("property") or node.get("propertyName"):
            prop = node.get("property") or node.get("propertyName")
            op = node.get("operation", {})
            optype = op.get("operationType") or op.get("operator") or node.get("operator", "")
            vals = op.get("values") or op.get("value") or node.get("value") or node.get("values") or ""
            incl = op.get("includeObjectsWithNoValueSet")
            out.append(f"{prop} {optype} {vals}" + (f" (noValue={incl})" if incl is not None else ""))
        for k, v in node.items():
            if k in ("property", "propertyName", "operation"):
                continue
            walk_filters(v, out)
    elif isinstance(node, list):
        for x in node:
            walk_filters(x, out)


def summarize(path):
    d = json.load(open(path))
    print("\n" + "=" * 78)
    print(f"{d.get('name')}  [{d.get('id')}]  enabled={d.get('isEnabled')}  obj={d.get('objectTypeId')}")

    enr = d.get("enrollmentCriteria", {})
    print(f"  ENROLLMENT type={enr.get('type')} reEnrollment={enr.get('shouldReEnroll')}")
    leaves = []
    walk_filters(enr.get("listFilterBranch") or enr.get("filterBranch") or enr, leaves)
    for l in leaves[:40]:
        print("    -", l)

    print("  ACTIONS:")
    for a in d.get("actions", []):
        at = a.get("actionTypeId") or a.get("type")
        fields = a.get("fields", {})
        prop = fields.get("property_name") or fields.get("propertyName")
        val = fields.get("value")
        if prop:
            if isinstance(val, dict):
                if "staticValue" in val:
                    val = val.get("staticValue")
                elif "value" in val:
                    val = val.get("value")
            print(f"    [{a.get('actionId')}] set {prop} = {val}")
        else:
            refs = []
            walk_filters(fields, refs)
            print(f"    [{a.get('actionId')}] {at}" + (f"  {fields.get('name','')}" if fields.get('name') else ""))
            for r in refs[:6]:
                print("         ·", r)


def main():
    ap = argparse.ArgumentParser(description="Summarize HubSpot flow JSON (enrollment + actions).")
    ap.add_argument("target", nargs="?", default="./workflows_output",
                    help="Directory of *.json flow files, or a single .json file (default: ./workflows_output)")
    args = ap.parse_args()

    if os.path.isfile(args.target):
        files = [args.target]
    else:
        files = sorted(glob.glob(os.path.join(args.target, "*.json")))
    if not files:
        print(f"No flow JSON found at: {args.target}")
        return
    for f in files:
        summarize(f)


if __name__ == "__main__":
    main()
