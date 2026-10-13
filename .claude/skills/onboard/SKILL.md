---
name: onboard
description: Guided first-run setup for a new user of this workspace. Interviews the user about their role, clients, and tools, then fills .env one key at a time, creates their first real client, and runs the first sync. Trigger on "/onboard", "onboard me", "set this up for me", "walk me through this workspace", "I just installed this", "how do I use this", or when the user drops ONBOARDING.md into the chat.
---

# Onboard

The user just ran the installer. They may not know VS Code, the terminal, or what this workspace
does. Your job: get them from an empty workspace to one real client with real context, in about
20 minutes, and explain only what they need at each step.

## Rules

- Ask **one question at a time**. Wait for the answer before you continue.
- Before you run a command, say in one line what it does and what it changes on their Mac.
- Never ask the user to paste a key into the chat. Keys go in `.env` through `bin/s2 setup`, or
  the user edits `.env` in VS Code. Never print `.env` contents.
- Do not write to any external system (HubSpot, Slack, Google, Teamwork) during onboarding.
- Do not invent where a key lives in a vendor's UI. Point the user to the vendor's help docs.
- If the user says "skip", skip that step and continue.
- Keep each message short. End each message with the one thing the user does next.

## Steps

### 1. Show the finished state (3 min)

If `Acme-Example/` is missing, run `bin/s2 setup` to create it. Then show the user, in order:

1. `Acme-Example/transcripts/` holds the raw call.
2. `transcripts/transcript-index.md` is the index that `s2` builds.
3. `context.md` is the client summary. Without an AI key it is still a blank template. Fill it
   now while the user watches: replace each placeholder in Company Overview, Key Contacts,
   Project Goals, Current Status, and Key Decisions with facts from the verbatim dialogue below
   `## Transcript`. Cite the speaker and timestamp for each fact, and delete any placeholder the
   call does not answer.

Then explain in two sentences: calls go in and a client summary comes out. Claude reads that
summary at the start of each session, so it remembers every client.

### 2. Interview (5 min)

Ask these questions, one at a time:

1. What is your role, and what do you do most days for clients?
2. Which clients are active now? (names only)
3. Where do your client notes and files live today? (Obsidian, Claude Desktop projects, Google
   Drive, local folders, nowhere)
4. Which call recorder do you use? (Fathom or something else)
5. Which other tools do you want Claude to use? (HubSpot, Slack, Teamwork, Google Docs)

Write the answers to `_meta/me.md` as a short profile. Tell the user that this file stays on
their Mac and is not committed.

### 3. Keys, only the ones they need (5 min)

Use the answers from step 2 to choose keys from the table in `ONBOARDING.md`. Skip the rest.
For each key: say what it unlocks, point to the vendor's help docs, and ask the user to run
`bin/s2 setup` in the terminal (it prompts for empty keys only). Fathom users need
`S2_FATHOM_API_KEY` and `S2_FATHOM_RECORDED_BY` (their own work email). HubSpot tokens belong in
the client folder's own `.env`, not the root `.env`.

### 4. First real client (5 min)

Choose one active client from step 2. Run `bin/s2 new client <Name>`. Then:

- If they use Fathom and the key is set: run `bin/s2 wrap-up`, then confirm that transcripts
  arrived in `<Name>/transcripts/`.
- If they have existing notes (Obsidian, Drive, Claude Desktop): ask them to copy the files into
  `<Name>/documents/`, or ask for the folder path and copy the files yourself after they confirm.
  Do not move or delete their originals.
- Then run `bin/s2 context <Name>` and show them the new `context.md`.

### 5. First real question (2 min)

Ask the user for a real question about that client. Answer it with the `grounder` agent and cite
the transcript line. This shows the payoff.

### 6. Wrap up

Show what now works, in a list of three items or fewer. Then offer two next steps, ranked by their
answers to step 2: for example, more clients, a time-logging skill, or the HubSpot agents. Tell
them they can delete `Acme-Example/` when they no longer need it.
