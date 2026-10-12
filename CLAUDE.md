# CLAUDE.md

Guidance for Claude Code (claude.ai/code) in this repository.

## What This Repo Is

A client engagement workspace for a HubSpot solutions architect. It is **not a traditional software
project**: truth lives in Markdown, transcripts, and deliverables. Stdlib-only Python scripts keep
each client's context current and add optional AI summaries. Client folders are local and
gitignored by default (see `.gitignore`).

## CLI and layout

`bin/s2 <cmd>` runs everything in `_meta/scripts/` and auto-loads the root `.env`. `s2 help` lists
every command. Daily use: `s2 sync`, `s2 wrap-up`, `s2 fetch`, `s2 context <client>`, `s2 morning`.
New client: `s2 new client <Name>` (creates `transcripts/`, `work/`, `exports/`, `documents/`).

- **GTM JSON exports:** Tag Assistant logs run 10-20 MB and workspace exports hold 100+ tags. Never
  read either directly. Use `s2 gtm <file>` / `/gtm` (runtime logs) or `s2 gtm-workspace <file>` /
  `/gtm-workspace` (container config) first. Marketo exports: `s2 marketo <file>` / `/marketo`.
- **Portal reads:** `/schema` and `/workflows` pull and summarize a portal's schema or workflows.
  Read the summary, not the raw JSON.
- **Scheduled jobs** are playbooks: `s2 playbook new <name>` writes `_meta/playbooks/<name>.toml`;
  `s2 playbook sync` installs them.

## Transcript Naming Convention

`[YYYY-MM-DD]_[client-name]_[attendees]_[topic-keywords].txt`, e.g.
`2026-01-15_demo_alex-jordan_kickoff.txt`. Files in a client's `transcripts/` folder are indexed by
`update-context.py`. Details: `_meta/system/templates/transcript-naming-guide.md`.

## Ground Rules for Claude

- **Do not fabricate UI paths, button names, or feature behavior for third-party tools** (HubSpot, Salesforce, Marketo, etc.). If you don't have a sourced answer, say so and suggest the user verify in the product docs or by navigating the UI directly.
- Claims about specific technical capabilities must be sourced from a project doc, transcript, or verified external reference, not inferred from general training knowledge.
- When conversing with the user, aim for density of insight over verbosity.

### Scope guardrails

- "Don't X yet" / "hold on X" is a hard stop for the rest of the session unless the user lifts it.
- Before any write to a portal or external system, state the target in one line (sandbox / UAT / prod). Default to sandbox or UAT.
- When the user says "edit it" or "take care of it", make the change; don't hand back a proposal.

### Before recommending

- Check for a prior decision first (`grounder`: calls, decision log, SOW) and cite it if found.
- Run HubSpot design choices past `hs-docs` for limits (uniqueness on existing props, synced
  fields, calculated vs. plain props) and native options before proposing.
- Client-volunteered work is not ours to build. Client emails go through the account manager.

### Transcript sourcing (Fathom summaries vs. source material)

Every transcript file has two parts, separated by a `## Transcript` heading:
- **Above `## Transcript`** — Fathom's auto-generated `## Summary`, `## Key Takeaways`, `## Topics`, and `## Next Steps`. This is Fathom's paraphrase, not verbatim. Use it only for orientation and to jump to timestamps.
- **Below `## Transcript`** — the verbatim, timestamped dialogue (`[HH:MM:SS] Speaker: ...`). This is the source of truth.

Rules:
- **Any factual claim about what was said, decided, committed to, or described in a meeting must be grounded in the verbatim dialogue below `## Transcript`** — never quoted or paraphrased from Fathom's summary/takeaways/action items.
- When you cite a meeting, cite the source line (the speaker + timestamp), not the Fathom bullet.
- If a Fathom takeaway and the verbatim dialogue disagree, the verbatim dialogue wins. Fathom summaries drop nuance and occasionally misattribute — treat them as a table of contents, not evidence.
- To read only the source dialogue and skip Fathom's summary, slice from the `## Transcript` marker down, e.g. `sed -n '/^## Transcript/,$p' <file>`.
- The same rule applies to the Fathom MCP tools: `get_meeting_summary` is Fathom's paraphrase; `get_meeting_transcript` is source. Ground factual claims in the transcript.

## Delegation (orchestrator + project agents)

The main session orchestrates: design, decisions, and anything the user reads. Delegate by agent
name (`.claude/agents/`). Use `general-purpose` only when none of these fits:

| Job | Agent |
|---|---|
| What a client said, agreed, or asked for (calls, SOW, docs) | `grounder` |
| What's configured or stored in a portal; build read-back | `portal-reader` |
| How HubSpot works: API, limits, UI paths, tier gating | `hs-docs` |
| Rubric labeling across many shards | `classifier` |
| Executing an approved build spec | `builder` |
| Attacking a plan, build, or deliverable before the user sees it | `adversary` |
| Committing, pushing, or opening a PR for finished work | `shipper` |

Overlay agents appear here after `s2 setup --overlay PATH`.

- Keep small jobs in the main session. Delegate when the agent would read context you don't
  already hold.
- When a delegated result needs fixes, send them to the same agent with `SendMessage` rather than
  spawning a fresh one.
- Multi-object HubSpot builds go through `/hs-build` (ground, spec, `/grill`, approve, build,
  verify). Settle open decisions with `/grill`, or `/grill-deep` for loose ideas.
- Discuss architecture with the user before building. Check an agent's claims against the source
  before repeating them.

## Script tests

`bin/s2 test` runs `_meta/scripts/tests/` (unittest, fast). It needs Python 3.11+; an older system
`python3` fails on import. A PostToolUse hook (`test-on-edit.py`) runs the suite after any edit to a
`_meta/scripts/*.py` file and blocks with the failure until it is fixed.

## Drive linkage (local file ↔ Google Doc/Sheet)

- After pushing a local deliverable to Drive as a Doc or Sheet, register it:
  `bin/s2 drive register --local "<path>" --drive-id <id> --kind doc|sheet`. Other commands:
  `check`, `list`, `mark-synced`, `open` (`s2 help`).
- When a drift prompt appears, ask the user before pushing, then `mark-synced`. Update in place
  (sheets: `writeSpreadsheet`/`batchWrite`) so the Drive link survives; never create a replacement doc.
- **Comment safety:** `replaceDocumentWithMarkdown` destroys every comment thread with no warning.
  Run `listComments` first. If any threads exist, use `findAndReplace`, `batchModifyText`, or
  `replaceRangeWithMarkdown` on the changed section instead, unless the user says the threads are expendable.
- HTML comments (`<!-- -->`) never survive a push to Drive.

## Global Context Files

- `_meta/clients/hubspot-api-reference.md` — HubSpot API reference (for HubSpot questions, delegate to `hs-docs`)
- `_meta/library/hubspot/` — HubSpot client, schema puller, workflow grabber, workflow API notes
