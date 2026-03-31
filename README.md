# HS Solutions Architect Workspace

This is a **repeatable workspace for running HubSpot client delivery** without losing track of what happened, what was decided, and what’s next.

In plain English:
- You drop meeting transcripts into the right place.
- A script turns those transcripts into a clean index and updates the client’s `context.md`.
- Optionally, another script generates a short AI status summary (`context-ai.md`) so you can ramp back up in minutes.

---

## What you need (read this first)

### Do you need Cursor?
**You don’t *have* to use Cursor**, but this repo is built assuming you will **open the folder in Cursor** (or another AI IDE) so you can:
- `@` reference `context.md` and transcripts when you ask questions
- edit deliverables and SOWs with the same context the scripts maintain
- run terminal commands from the repo root without path confusion

If you skip Cursor, you can still use **any editor + Terminal**—everything works the same; you just lose the “AI pair programmer” workflow.

### What about Claude Code (or similar)?
**You can use it**—this is just files and scripts, so any tool that can open the repo and run shell commands is fine.

That said, **this workspace is not really designed around Claude Code** (or any single CLI-first agent) as the main way to work. The happy path we have in mind is: **open the folder in an editor** (especially one with good `@file` / project context), edit markdown, run the Python scripts when you need them. Claude Code is a valid way to do that, but we don’t document Claude-specific flows, hooks, or project rules—so expect to **adapt** rather than get a turnkey Claude Code experience.

### Do you need Python?
**Yes.** The scripts are Python 3. From the repo:

```bash
python3 --version
```

Run scripts with `python3` (examples below use `python3`).

### Do you need API keys?
**Depends what you want to automate.**

| Feature | Needs API keys? | What to set |
|--------|------------------|-------------|
| Folder structure + editing `context.md` by hand | **No** | — |
| `update-context.py` (index + refresh `context.md` from files on disk) | **No** | — |
| `enrich-context.py` (AI writes `context-ai.md`) | **Yes** | `OPENAI_API_KEY` **or** `ANTHROPIC_API_KEY` in `.env` |
| `fathom-fetch-inbox.py` / `fathom-fetch.sh` (pull transcripts from Fathom into `_inbox/`) | **Yes** | `FATHOM_API_KEY` in `.env` |
| `fathom-webhook-inbox.py` (receive transcripts via webhook) | **Optional** | `FATHOM_WEBHOOK_SECRET` recommended; `FATHOM_API_KEY` not required for the listener itself |
| `auto-rename-transcripts.py` (basic rename from heuristics) | **No** | — |
| `auto-rename-transcripts.py` (smarter topic names via AI) | **Yes** | `OPENAI_API_KEY` **or** `ANTHROPIC_API_KEY` |

**Bottom line:** you can run the whole **manual** workflow (drop `.txt` transcripts, run `update-context.py`) with **zero** API keys. Keys only unlock **Fathom** and **LLM** features.

### One-time setup (copy-paste order)
1. Clone this repo and open the folder in **Cursor** (File → Open Folder).
2. In Terminal, at the repo root, create your secrets file:
   ```bash
   cp .env.example .env
   ```
3. Edit `.env` only for features you use:
   - `FATHOM_API_KEY=` for automatic Fathom fetch
   - `OPENAI_API_KEY=` or `ANTHROPIC_API_KEY=` for `enrich-context.py` and AI topic naming
4. Never commit `.env` (it’s gitignored).

### The absolute minimum path (no API keys)
1. `./scripts/new-client.sh "Your Client Name"`
2. Put transcript `.txt` files in `Your Client Name/transcripts/`
3. Run:
   ```bash
   python3 _meta/scripts/update-context.py "Your Client Name"
   ```
That’s it. Everything else is optional.

---

## Who this is for
- HubSpot solutions architects
- Delivery/implementation leads who run meetings, capture transcripts, and keep `context.md` current
- Teams who want “meeting transcript → usable client context” to be fast and consistent

## The problem it solves
Client delivery gets messy fast:
- Transcripts end up in random places (or never get reviewed).
- “What did we decide last week?” takes 20 minutes of hunting.
- You onboard someone new and they have no single source of truth.

This workspace makes the default behavior the good behavior: **everything goes into the right folder, and the context stays current**.

## What this gives you (outcomes)
- **Faster ramp-up**: open a client folder and you can understand the last 30–90 days quickly.
- **Less context switching**: stop rebuilding the same background before every call.
- **Fewer dropped threads**: transcripts are indexed, and recent activity is visible in `context.md`.
- **Better continuity**: if you step away for a week, you can recover the narrative.

## What it does (mechanically)
For each client, you keep:
- `context.md`: your human-maintained “source of truth” (plus auto-updated sections)
- `transcripts/`: raw transcript files
- `transcripts/transcript-index.md`: auto-generated index of transcripts
- `documents/deliverables/`: draft + final deliverables
- `context-ai.md` (optional): AI-generated “current status / next steps / themes”

## What you get
- `TEMPLATE_CLIENT/` a starter client folder scaffold
- `scripts/new-client.sh` to create a new client folder from the scaffold
- `_meta/scripts/` reusable automation for:
  - `fathom-fetch-inbox.py` (end-of-day transcript fetch into `_inbox/`)
  - `fathom-webhook-inbox.py` (webhook listener that writes transcripts into `_inbox/`)
  - `update-context.py` (updates `transcripts/transcript-index.md` and `context.md`)
  - `enrich-context.py` (LLM-generated `context-ai.md`, if keys are configured)
  - `auto-rename-transcripts.py` (optional naming + context refresh)

## What a normal day looks like
1. You have calls.
2. Transcripts land in `_inbox/` (automatically via fetch or webhook).
3. You move each transcript into the right client’s `transcripts/` folder.
4. You run one command to refresh the client’s context:
   - transcript index updates
   - “Recent transcripts” in `context.md` updates
   - deliverables lists update
5. (Optional) you generate an AI status summary for quick refresh before the next call.

## Quick Start
1. Create a client folder:
   - `./scripts/new-client.sh "Acme Corp"`
2. (Optional) enable automation keys:
   - copy `.env.example` → `.env`
   - set `FATHOM_API_KEY` if you want transcript ingestion
   - set `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` if you want `context-ai.md`
3. Refresh a client’s context anytime:
   - `python3 _meta/scripts/update-context.py "Acme Corp"`
4. (Optional) generate AI status:
   - `python3 _meta/scripts/enrich-context.py "Acme Corp"`

## Recommended Transcript Workflow
- Fetch transcripts into `_inbox/`:
  - `./_meta/scripts/fathom-fetch.sh`
- Move the transcript `.txt` files into a client folder:
  - `_inbox/2026-03-25_weekly-sync.txt` → `Acme Corp/transcripts/`
- Optional: normalize naming automatically while you drag files in:
  - `python3 _meta/scripts/auto-rename-transcripts.py "Acme Corp"`
- Refresh the client context:
  - `python3 _meta/scripts/update-context.py "Acme Corp"`
- Optional: AI-generated “what’s going on” summary:
  - `python3 _meta/scripts/enrich-context.py "Acme Corp"`

## Data Safety Rules
- Treat this repo as **structure + automation**, not as a place to publish client data.
- Never commit secrets/tokens; use `.env` locally.
- Keep real client transcripts/exports in a private repo (this repo’s `.gitignore` is set up to help prevent accidents).
