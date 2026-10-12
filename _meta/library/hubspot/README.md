# HubSpot Library

Scripts and reference docs for read-only HubSpot portal work.

## What ships

| Path | Purpose | Inputs | Outputs |
|---|---|---|---|
| `hs_client.py` | Reusable v3/v4 client (stdlib only): pinned notes, preflight validation, retry-after handling, upsert | Imported by your own scripts | API responses |
| `schema_puller/grab_schema.py` | Pull object property schemas | `--object contacts,deals` or `--all` | JSON files in `--output-dir` |
| `schema_puller/parse_schema.py` | Summarize pulled schema, token-safe | Directory from `grab_schema.py` | Readable summary |
| `workflow_grabber/grab_workflows.py` | Fetch workflow JSON from the Automation v4 API | Workflow IDs or `--all` | JSON files + metadata |
| `workflow_grabber/parse_flows.py` | Summarize flow JSON (enrollment + property-set actions), token-safe | Directory of flow JSON or one file | Per-flow summary |
| `hubspot-workflow-api.md` | Tested notes on the workflows API | | |
| `hubspot-cca-documentation/` | Custom code action reference | | |

## Prerequisites

- `pip install requests python-dotenv` (the grabbers use them; `hs_client.py` is stdlib only).
- `HUBSPOT_ACCESS_TOKEN` and `HUBSPOT_HUB_ID` in a `.env`. The grabbers search upward from your
  current working directory first (so run them from the client folder that holds its own `.env`),
  then fall back to the workspace root `.env`.

## Example

```bash
cd <Client>
python3 ../_meta/library/hubspot/schema_puller/grab_schema.py --all --output-dir ./work/schema_output
python3 ../_meta/library/hubspot/schema_puller/parse_schema.py ./work/schema_output
```

## Reference

- [HubSpot API documentation](https://developers.hubspot.com/docs/api/overview)
- `_meta/clients/hubspot-api-reference.md` for common endpoints and payloads
