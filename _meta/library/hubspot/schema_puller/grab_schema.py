"""
HubSpot Schema Puller (CRM v3 API)
-----------------------------------
Fetches object schema (properties, pipelines, associations) from a HubSpot
portal. Only performs GET operations — never modifies the portal.

Usage:
    # One standard object
    python grab_schema.py --object contacts

    # Multiple objects
    python grab_schema.py --object contacts,deals,companies

    # Every standard + custom object on the portal
    python grab_schema.py --all

    # Custom output directory
    python grab_schema.py --object deals --output-dir ./my_schema

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

# Walk up from the *working* directory, not this script's directory. Client
# tokens live in the client folder's .env; a bare load_dotenv() resolves
# relative to this file and finds the repo-root .env instead, which has no
# HUBSPOT_* keys. Load the client .env first, then the root one for fallbacks.
load_dotenv(find_dotenv(usecwd=True))
load_dotenv()

HUB_ID = os.getenv("HUBSPOT_HUB_ID")
ACCESS_TOKEN = os.getenv("HUBSPOT_ACCESS_TOKEN")

BASE_URL = "https://api.hubapi.com"
SCHEMAS_ENDPOINT = f"{BASE_URL}/crm/v3/schemas"
PROPERTIES_ENDPOINT = f"{BASE_URL}/crm/v3/properties/{{object_type}}"
PIPELINES_ENDPOINT = f"{BASE_URL}/crm/v3/pipelines/{{object_type}}"
ASSOCIATIONS_ENDPOINT = f"{BASE_URL}/crm/v4/associations/{{from_object}}/{{to_object}}/labels"

STANDARD_OBJECTS = [
    "contacts", "companies", "deals", "tickets", "line_items",
    "products", "quotes", "calls", "emails", "meetings", "notes", "tasks",
]

# Objects that support pipelines (associations don't apply the same way to all)
PIPELINE_OBJECTS = {"deals", "tickets"}

# Polite delay between requests (seconds)
REQUEST_DELAY = 0.2


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

def list_custom_object_types() -> list[str]:
    """GET /crm/v3/schemas — returns fully-qualified names of custom objects."""
    resp = requests.get(SCHEMAS_ENDPOINT, headers=_headers())
    _raise_for_status(resp)
    data = resp.json()
    return [s["fullyQualifiedName"] for s in data.get("results", [])]


def get_properties(object_type: str) -> list[dict]:
    """GET /crm/v3/properties/{objectType}"""
    url = PROPERTIES_ENDPOINT.format(object_type=object_type)
    resp = requests.get(url, headers=_headers())
    _raise_for_status(resp)
    return resp.json().get("results", [])


def get_pipelines(object_type: str) -> list[dict]:
    """GET /crm/v3/pipelines/{objectType} — only valid for pipeline-backed objects."""
    url = PIPELINES_ENDPOINT.format(object_type=object_type)
    resp = requests.get(url, headers=_headers())
    if resp.status_code in (400, 404):
        return []  # object doesn't support pipelines
    _raise_for_status(resp)
    return resp.json().get("results", [])


def get_association_labels(from_object: str, to_object: str) -> list[dict]:
    """GET /crm/v4/associations/{fromObjectType}/{toObjectType}/labels"""
    url = ASSOCIATIONS_ENDPOINT.format(from_object=from_object, to_object=to_object)
    resp = requests.get(url, headers=_headers())
    if not resp.ok:
        return []
    return resp.json().get("results", [])


def build_object_schema(object_type: str, associate_with: list[str]) -> dict:
    print(f"  Properties...")
    properties = get_properties(object_type)
    time.sleep(REQUEST_DELAY)

    pipelines = []
    if object_type in PIPELINE_OBJECTS:
        print(f"  Pipelines...")
        pipelines = get_pipelines(object_type)
        time.sleep(REQUEST_DELAY)

    associations = {}
    for to_object in associate_with:
        if to_object == object_type:
            continue
        labels = get_association_labels(object_type, to_object)
        if labels:
            associations[to_object] = labels
        time.sleep(REQUEST_DELAY)

    return {
        "objectType": object_type,
        "properties": properties,
        "pipelines": pipelines,
        "associationLabels": associations,
    }


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def write_schema_json(object_type: str, schema: dict, output_dir: Path) -> Path:
    filename = f"{object_type}__schema.json"
    filepath = output_dir / filename
    filepath.write_text(json.dumps(schema, indent=2, ensure_ascii=False))
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
        description="Fetch HubSpot object schema (properties/pipelines/associations) via the CRM v3 API (read-only)."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--object",
        metavar="TYPE[,TYPE...]",
        help="Comma-separated object type(s), e.g. contacts,deals or a custom object fully-qualified name.",
    )
    group.add_argument(
        "--all",
        action="store_true",
        help="Fetch schema for all standard objects plus every custom object on the portal.",
    )
    parser.add_argument(
        "--output-dir",
        metavar="DIR",
        default="./schema_output",
        help="Directory to write JSON files (default: ./schema_output).",
    )
    args = parser.parse_args()

    validate_env()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.all:
        print("Fetching custom object list...")
        custom_objects = list_custom_object_types()
        object_types = STANDARD_OBJECTS + custom_objects
    else:
        object_types = [o.strip() for o in args.object.split(",") if o.strip()]

    print(f"Pulling schema for {len(object_types)} object type(s): {', '.join(object_types)}")

    saved = 0
    for object_type in object_types:
        print(f"\n{object_type}:")
        try:
            schema = build_object_schema(object_type, associate_with=object_types)
        except SystemExit:
            print(f"  [SKIP] {object_type} failed, continuing.")
            continue
        filepath = write_schema_json(object_type, schema, output_dir)
        print(f"  Saved: {filepath.name}")
        saved += 1

    print(f"\nDone. {saved} object schema(s) written to: {output_dir.resolve()}")


if __name__ == "__main__":
    main()
