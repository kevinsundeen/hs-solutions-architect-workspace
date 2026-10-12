---
name: portal-discovery
description: Read a client's live HubSpot portal (schema + workflows) and any supplied transcripts/SOW/discovery docs, then draft a first-pass CRM Architecture / data model doc grounded in what's actually configured. Use when the user asks to "audit this portal," "draft a data model for [client]," "generate a CRM architecture draft," "see what's actually built in the portal," or wants a quick first cut at recommendations before a formal discovery deliverable. Trigger on "/portal-discovery <client>". Companion to implementation-strategist — that skill provides the artifact template and consulting posture; this one supplies the live-portal evidence to fill it in.
---

# Portal Discovery

Produces a grounded first draft of a client's current-state data model by combining two
token-safe portal reads with whatever transcript/SOW/discovery material already exists —
so the user starts a discovery or audit deliverable from what's actually configured, not from
a blank page or from guessing at HubSpot behavior.

This skill supplies evidence. It does not replace judgment — every claim in the draft must
trace back to a pulled JSON file, a transcript line, or an explicit open question. Load
`implementation-strategist` alongside this skill for the artifact template and consulting
posture (business-process-before-technology, facts vs. assumptions, etc.) — don't duplicate
that methodology here.

## Steps

1. **Identify the client and confirm portal access.** Client folder must exist at the repo
   root (e.g. `Acme`, `Globex`). Confirm a `.env` exists in that folder. If the HubSpot
   token variable name is non-standard (some clients use `HUBSPOT_SANDBOX_ACCESS_TOKEN`
   instead of `HUBSPOT_ACCESS_TOKEN` — check the client's other scripts under `work/` if
   unsure), export it under the expected name for the subprocess call rather than guessing
   or asking the user to paste the token.

2. **Pull the schema.** Run the same steps as the `/schema` command:
   ```bash
   cd "<repo-root>/<client>" && \
   python3 "<repo-root>/_meta/library/hubspot/schema_puller/grab_schema.py" --all --output-dir ./work/schema_output && \
   python3 "<repo-root>/_meta/library/hubspot/schema_puller/parse_schema.py" ./work/schema_output
   ```
   Only the summarizer's stdout should inform the draft — never read the raw
   `*__schema.json` files directly.

3. **Pull the workflows.** Run the same steps as the `/workflows` command:
   ```bash
   cd "<repo-root>/<client>" && \
   python3 "<repo-root>/_meta/library/hubspot/workflow_grabber/grab_workflows.py" --all --output-dir ./work/workflows_output && \
   python3 "<repo-root>/_meta/library/hubspot/workflow_grabber/parse_flows.py" ./work/workflows_output
   ```
   Again, only the summarizer's stdout — never the raw workflow JSON.

4. **Gather supplemental context.** Check for and read (these are small enough to read
   directly, unlike the API dumps above):
   - `<client>/transcripts/transcript-index.md` and any transcripts it points to that
     discuss data model, integrations, or migration scope
   - `<client>/documents/client-provided/` for an SOW, discovery notes, or requirements doc
   - `<client>/context.md` for engagement status and prior decisions
   If the user has pointed you at a specific transcript, SOW, or doc in the conversation, use
   that instead of searching — don't re-discover what he already told you.

5. **Draft the CRM Architecture doc** using the template in
   `~/.claude/skills/implementation-strategist/methodology/artifact-guide.md` (§4 CRM
   Architecture). Populate:
   - **Object Model** — standard + custom objects from the schema pull
   - **Object Relationships** — from `associationLabels` in the schema summary
   - **Key Custom Properties** — the custom (non-`hubspotDefined`) properties per object,
     grouped by property group
   - **Pipeline Design** — pipeline stages from the schema pull
   - **Lifecycle Architecture / Governance Notes** — which workflows write to which
     properties (from the workflow summary's `set <prop> = <value>` actions) — this is
     where you can surface things like two workflows writing the same property, or
     enrollment criteria that look like enroll-everyone
   - **Data Quality Observations** (borrow this section from the Discovery Summary template)
     — properties with no group, custom objects with few properties, pipelines with unusual
     stage counts, disabled workflows still referencing live properties
   - **Open Questions** — anything the schema/workflow pull can't answer (business intent
     behind a property, whether a legacy workflow is still relied on) — flag explicitly,
     never guess at intent

6. **Save the draft** to `<client>/documents/deliverables/draft/<Client> — CRM Architecture (Draft).md`.
   Mark it clearly as a first-pass internal draft (e.g. a one-line note at the top) — this
   is the user's starting point for a real deliverable, not something to hand to the client
   as-is, so it doesn't need client-voice polishing yet.

## Notes

- Ground rules from CLAUDE.md apply throughout: never fabricate HubSpot UI/behavior details;
  every technical claim traces to the pulled JSON, a transcript, or a stated assumption
  flagged as such.
- If schema or workflow pull fails (bad token, wrong object names), report the failure and
  what you did manage to gather — a partial draft with clear gaps beats stalling entirely.
- This produces a *current-state* draft. It does not recommend a target state design —
  that's a separate, judgment-heavy step implementation-strategist's methodology covers
  once the current state is understood.
