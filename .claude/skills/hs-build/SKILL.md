---
name: hs-build
description: Use when the user asks to build, configure, or change something in a client's HubSpot portal that spans more than one object or workflow — "/hs-build <client> <what>", "build the territory routing", "set up the pipeline for X", "stand this up in sandbox", "port these Marketo flows". Also when turning a transcript ask or UAT row into a portal change outside a client that has its own UAT skill.
---

# HubSpot build loop

You are the orchestrator. You own the design, the conversation with the user, and the final
check. Agents do the reading, the building, and the attacking. Design is never delegated.

**Small change?** One property, one workflow edit, or one list: skip this loop, do it
inline, and back up first. Use the loop when a change touches 2 or more objects or
workflows, or any data load.

## Files
- Spec: `<Client>/work/YYYY-MM-DD-<slug>-build-spec.md`
- Build folder: `<Client>/work/<slug>-build/`, which holds scripts, `backups/`,
  `MANIFEST.md`, and `MANUAL_STEPS.md`

## 1 · Ground (in parallel, in one message)
- `grounder`: what the client asked for and agreed to on this topic, plus SOW scope
- `portal-reader`: current state of every object and workflow the change will touch, with
  record counts

## 2 · Draft the spec
Present the architecture in 3–6 lines first: objects, what's derived from what, and which
workflows. If the user redirects, the redirect goes into the spec. Then write the spec:

```markdown
# <Client> — <build name>
Target portal: <id> (sandbox)
Token var: <NAME from <Client>/.env>
## Goal         (one paragraph, what the client gets)
## Current state (from portal-reader, with counts)
## Changes      (one row per object: type | name | internal name | what changes | derived from)
## Existing data (backfill? re-enrollment? who's affected, with counts)
## Out of scope
## Decisions    (filled by /grill)
```

Every assumption you make goes in inline as `ASSUMPTION:`. /grill hunts for these.

## 3 · Grill
**REQUIRED:** run the `grill` skill on the spec. Skip it only when the user says
`--no-grill` or "skip the grill".

## 4 · Approve
Show the user the Changes table and the Decisions. Build only after an explicit yes. Record it
in the spec as `Approved: the user YYYY-MM-DD`.

## 5 · Build
Send the `builder` agent this brief:

```
Spec: <absolute path>          Build folder: <absolute path>
Client folder: <path>          Token var: <NAME>   Target portal: <id>
Build: <which Changes rows; all unless phased>
Reuse: <any prior script in the build folder or _meta/library>
Return: your standard report.
```

Phase big builds (properties → objects/associations → workflows → data) so a mistake
surfaces before workflows depend on it. If the builder comes back `BLOCKED` or with
"Stopped on", that is a design question for the user. Take it to him and don't work around it.

## 6 · Verify (in parallel)
- `portal-reader`: read back every row of the Manifest against the spec
- `adversary`: review the spec, Manifest, and MANUAL_STEPS as a finished build: what
  breaks for existing records or at go-live

Before you tell the user anything is done, check two or three of the most important rows
yourself with a direct GET. An agent's report of success doesn't count as proof.

When read-back fails or the adversary finds a `wrong` row, send the fix to the same builder
with `SendMessage` (by its agent ID). It already holds the spec and Manifest. Spawn a new
builder only if the original is gone, and give that one the Manifest as well as the spec.

## 7 · Report and record
Report to the user, names first:
- What now works. One line on how to see it in the portal.
- Anything that failed read-back, and the adversary's findings rated `blocks` or `wrong`
- New MANUAL_STEPS lines
- What's still open

Then offer `/context-update <client>` and `/tw-update`.
