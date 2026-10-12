"""
HubSpot Workflow Grabber (v4 API)
---------------------------------
Fetches workflow JSON from a HubSpot portal using the Automation v4 API.
Only performs GET/POST read operations — never modifies the portal.

Usage:
    # Single workflow
    python grab_workflows.py --workflow-id 12345678

    # All active workflows
    python grab_workflows.py --all

    # All workflows (including disabled)
    python grab_workflows.py --all --include-disabled

    # Custom output directory
    python grab_workflows.py --all --output-dir ./my_workflows

Requires a .env file with:
    HUBSPOT_HUB_ID=your_hub_id
    HUBSPOT_ACCESS_TOKEN=your_private_app_token
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import find_dotenv, load_dotenv

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# Walk up from the *working* directory, not this script's directory: client tokens live in
# the client folder's .env. Then load the root .env for fallbacks.
load_dotenv(find_dotenv(usecwd=True))
load_dotenv()

HUB_ID = os.getenv("HUBSPOT_HUB_ID")
ACCESS_TOKEN = os.getenv("HUBSPOT_ACCESS_TOKEN")

BASE_URL = "https://api.hubapi.com"
LIST_ENDPOINT = f"{BASE_URL}/automation/v4/flows"
SINGLE_ENDPOINT = f"{BASE_URL}/automation/v4/flows/{{flow_id}}"
BATCH_ENDPOINT = f"{BASE_URL}/automation/v4/flows/batch/read"

# Batch read accepts up to 25 IDs at a time (HubSpot enforced limit)
BATCH_SIZE = 25
# Polite delay between paged list requests (seconds)
PAGE_DELAY = 0.25


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _headers() -> dict:
    return {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }


def _raise_for_status(response: requests.Response) -> None:
    if not response.ok:
        try:
            detail = response.json()
        except Exception:
            detail = response.text
        print(f"[ERROR] {response.status_code} from {response.url}")
        print(json.dumps(detail, indent=2) if isinstance(detail, dict) else detail)
        sys.exit(1)


# ---------------------------------------------------------------------------
# API calls (READ-ONLY)
# ---------------------------------------------------------------------------

def list_all_workflows(include_disabled: bool = False) -> list[dict]:
    """
    Pages through GET /automation/v4/flows and returns summary objects.
    Filters to active (isEnabled=True) workflows unless include_disabled=True.
    """
    print("Fetching workflow list...")
    results = []
    params = {"limit": 100}

    while True:
        resp = requests.get(LIST_ENDPOINT, headers=_headers(), params=params)
        _raise_for_status(resp)
        data = resp.json()

        page_results = data.get("results", [])
        for wf in page_results:
            if include_disabled or wf.get("isEnabled", False):
                results.append(wf)

        next_cursor = data.get("paging", {}).get("next", {}).get("after")
        if not next_cursor:
            break

        params["after"] = next_cursor
        time.sleep(PAGE_DELAY)

    print(f"Found {len(results)} workflow(s) {'(all states)' if include_disabled else '(active only)'}.")
    return results


def get_single_workflow(flow_id: str) -> dict:
    """GET /automation/v4/flows/{flowId}"""
    url = SINGLE_ENDPOINT.format(flow_id=flow_id)
    resp = requests.get(url, headers=_headers())
    _raise_for_status(resp)
    return resp.json()


def batch_get_workflows(flow_ids: list[str]) -> list[dict]:
    """
    POST /automation/v4/flows/batch/read in chunks of BATCH_SIZE.
    Returns a flat list of full workflow objects.
    """
    all_results = []

    for i in range(0, len(flow_ids), BATCH_SIZE):
        chunk = flow_ids[i : i + BATCH_SIZE]
        payload = {
            "inputs": [{"flowId": fid, "type": "FLOW_ID"} for fid in chunk]
        }
        resp = requests.post(BATCH_ENDPOINT, headers=_headers(), json=payload)
        _raise_for_status(resp)
        data = resp.json()

        all_results.extend(data.get("results", []))

        # Surface partial errors but keep going
        if data.get("errors"):
            print(f"[WARN] {data['numErrors']} error(s) in batch {i // BATCH_SIZE + 1}:")
            for err in data["errors"]:
                print(f"  - {err.get('message', err)}")

        time.sleep(PAGE_DELAY)

    return all_results


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def sanitize_filename(name: str) -> str:
    """Strip characters that are unsafe in filenames."""
    keep = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ._-")
    sanitized = "".join(c if c in keep else "_" for c in name)
    return sanitized.strip().replace(" ", "_")


def write_workflow_json(workflow: dict, output_dir: Path) -> Path:
    flow_id = workflow.get("id", "unknown")
    name = sanitize_filename(workflow.get("name", f"workflow_{flow_id}"))
    filename = f"{name}__{flow_id}.json"
    filepath = output_dir / filename
    filepath.write_text(json.dumps(workflow, indent=2, ensure_ascii=False))
    return filepath


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def validate_env() -> None:
    missing = []
    if not HUB_ID:
        missing.append("HUBSPOT_HUB_ID")
    if not ACCESS_TOKEN:
        missing.append("HUBSPOT_ACCESS_TOKEN")
    if missing:
        print(f"[ERROR] Missing environment variable(s): {', '.join(missing)}")
        print("Create a .env file — see .env.example for the required format.")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch HubSpot workflow JSON via the Automation v4 API (read-only)."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--workflow-id",
        metavar="ID",
        help="Fetch a single workflow by its numeric ID.",
    )
    group.add_argument(
        "--all",
        action="store_true",
        help="Fetch all active workflows.",
    )
    parser.add_argument(
        "--include-disabled",
        action="store_true",
        help="When used with --all, also fetch disabled/inactive workflows.",
    )
    parser.add_argument(
        "--output-dir",
        metavar="DIR",
        default="./workflows_output",
        help="Directory to write JSON files (default: ./workflows_output).",
    )
    args = parser.parse_args()

    validate_env()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # --- Single workflow ---
    if args.workflow_id:
        print(f"Fetching workflow {args.workflow_id} (hub {HUB_ID})...")
        workflow = get_single_workflow(args.workflow_id)
        filepath = write_workflow_json(workflow, output_dir)
        print(f"Saved: {filepath}")
        return

    # --- All workflows ---
    summaries = list_all_workflows(include_disabled=args.include_disabled)
    if not summaries:
        print("No workflows found.")
        return

    flow_ids = [wf["id"] for wf in summaries]
    print(f"Fetching full details for {len(flow_ids)} workflow(s)...")
    workflows = batch_get_workflows(flow_ids)

    saved = 0
    for wf in workflows:
        filepath = write_workflow_json(wf, output_dir)
        print(f"  Saved: {filepath.name}")
        saved += 1

    print(f"\nDone. {saved} workflow(s) written to: {output_dir.resolve()}")


if __name__ == "__main__":
    main()
