Run the Marketo Smart Campaign export summarizer on the provided file.

Usage: /marketo <path-to-campaign-export.json>

Execute this command and print the output:

```bash
s2 marketo "$ARGUMENTS" --md
```

The script extracts triggers, filters, and flow steps locally without sending the file to an LLM. It outputs:
- Trigger type(s) and smart list filter logic
- Every flow step, in order, with action type and target values
- Any nested choice/wait-step branching

After printing the summary, offer to flag anything that looks like it needs a HubSpot-side equivalent (e.g. a "Change Data Value" step implies a workflow property-set action) if the context is a Marketo→HubSpot migration.
