Run the HubSpot workflow grabber + token-safe summarizer for a client portal.

Usage: `/workflows <client-folder-name> [--include-disabled]`

Example: `/workflows Acme` or `/workflows Acme --include-disabled`

Parse `$ARGUMENTS`: the first word is the client folder name (must match a top-level directory in the repo, e.g. `Acme`, `Globex`). If `--include-disabled` follows, pass it through; otherwise only active workflows are pulled.

Execute this command and print the output:

```bash
cd "<repo-root>/<client-folder-name>" && \
python3 "<repo-root>/_meta/library/hubspot/workflow_grabber/grab_workflows.py" --all --output-dir ./work/workflows_output <include-disabled-flag> && \
python3 "<repo-root>/_meta/library/hubspot/workflow_grabber/parse_flows.py" ./work/workflows_output
```

- Substitute `<repo-root>` with the absolute path to this repo.
- `grab_workflows.py` needs `HUBSPOT_HUB_ID` and `HUBSPOT_ACCESS_TOKEN` — it reads `.env` starting from the current directory and walking up, so running from inside the client folder picks up that client's `.env`. If the client's HubSpot integration uses a differently-named token variable (check the client's other scripts if `.env` validation fails), tell the user rather than guessing at a variable name.
- Raw workflow JSON lands in `<client>/work/workflows_output/*.json` — do not read these files directly; only the summarizer's stdout output should inform your response.
- The summarizer prints, per workflow: enrollment type/re-enrollment, enrollment filters, and every action (property-set actions rendered as `set <prop> = <value>`).
- After printing the summary, offer to flag anything that looks off: workflows with no enrollment filters (enroll-everyone), actions that set the same property as another active workflow (possible conflict), or disabled workflows that still reference live properties.
