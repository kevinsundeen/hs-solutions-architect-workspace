# HS Solutions Architect Workspace

A public-safe template for HubSpot client delivery work: consistent folders, transcript ingestion, and context updates.

## Who this is for
- HubSpot solutions architects
- Delivery/implementation leads who run meetings, capture transcripts, and keep `context.md` current
- Teams who want “transcript → index → client context” to be repeatable

## Why it’s useful
- You keep every client’s story in one place (`context.md` + `transcripts/` + `documents/deliverables/`), so ramp-up is fast.
- You can automatically fetch and standardize meeting transcripts (Fathom fetch or webhook).
- You can refresh the client’s transcript index and “what’s going on” context with one script.
- If you enable LLM keys, you can generate a lightweight `context-ai.md` summary from the most recent transcripts.

## What you get
- `TEMPLATE_CLIENT/` a starter client folder scaffold
- `scripts/new-client.sh` to create a new client folder from the scaffold
- `_meta/scripts/` reusable automation for:
  - `fathom-fetch-inbox.py` (end-of-day transcript fetch into `_inbox/`)
  - `fathom-webhook-inbox.py` (webhook listener that writes transcripts into `_inbox/`)
  - `update-context.py` (updates `transcripts/transcript-index.md` and `context.md`)
  - `enrich-context.py` (LLM-generated `context-ai.md`, if keys are configured)
  - `auto-rename-transcripts.py` (optional naming + context refresh)

## Quick Start
1. Create a client workspace folder:
   - `./scripts/new-client.sh "Client Name"`
2. Configure optional keys:
   - Copy `.env.example` to `.env` (recommended) and fill values you want to enable.
3. Add artifacts into the client folder:
   - Transcripts into `transcripts/` (or `_inbox/` first, then move)
   - Deliverables into `documents/deliverables/draft/` or `documents/deliverables/final/`
4. Refresh context:
   - `python _meta/scripts/update-context.py "Client Name"`
5. Optional AI enrichment:
   - `python _meta/scripts/enrich-context.py "Client Name"`

## Recommended Transcript Workflow
- Run `./_meta/scripts/fathom-fetch.sh` (from repo root) to populate `_inbox/`.
- Move the transcript `.txt` files from `_inbox/` into the matching client’s `transcripts/`.
- (Optional) run `python _meta/scripts/auto-rename-transcripts.py "Client Name"` to normalize naming.
- Run `python _meta/scripts/update-context.py "Client Name"` so `context.md` stays current.

## Data Safety Rules
- This is a template: keep real client transcripts/exports in your private repo.
- Never commit secrets/tokens; use `.env` locally and keep it out of git.
