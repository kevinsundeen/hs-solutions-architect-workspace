Run the HubSpot schema puller + token-safe summarizer for a client portal.

Usage: `/schema <client-folder-name> <object1,object2,...|all>`

Example: `/schema Acme contacts,deals` or `/schema Acme all`

Parse `$ARGUMENTS`: the first word is the client folder name (must match a top-level directory in the repo, e.g. `Acme`, `Globex`). Everything after it is either `all` or a comma-separated list of object types (e.g. `contacts,deals,companies`, or a custom object's fully-qualified name).

Execute this command and print the output:

```bash
cd "<repo-root>/<client-folder-name>" && \
python3 "<repo-root>/_meta/library/hubspot/schema_puller/grab_schema.py" --<all-or-object-flag> --output-dir ./work/schema_output && \
python3 "<repo-root>/_meta/library/hubspot/schema_puller/parse_schema.py" ./work/schema_output
```

- Substitute `<repo-root>` with the absolute path to this repo.
- If the objects arg is `all`, use `--all`; otherwise use `--object <comma-separated-list>`.
- `grab_schema.py` needs `HUBSPOT_HUB_ID` and `HUBSPOT_ACCESS_TOKEN` — it reads `.env` starting from the current directory and walking up, so running from inside the client folder picks up that client's `.env` (per workspace convention: client tokens live in the client dir, not the repo root).
- Raw schema JSON lands in `<client>/work/schema_output/*.json` — do not read these files directly; only the summarizer's stdout output should inform your response.
- After printing the summary, offer to flag anything that looks off: properties with no group, pipelines with unusually few/many stages, or association labels that seem missing for objects the client actively uses.
