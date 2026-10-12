---
name: context-update
description: Append a session status update (current status, in-flight work, next steps, blockers) to a client's context.md, sourced from the current conversation instead of a transcript. Trigger on "/context-update", "update context for [client]", "log this to context", "save this to [client]'s context", "update the client context with what we did", or when the user explicitly asks to persist mid-conversation progress into a client's context file.
---

# Context Update (mid-conversation)

the user's client folders each have a `context.md` that tracks engagement status. Normally it's
refreshed from Fathom transcripts (`s2 context <client>`). This skill lets him push a status
update straight from the current conversation — no transcript required — for work discussed,
decided, or built mid-session (builds, decisions, blockers, next steps).

The summarization step (raw conversation → tidy status bullets) always runs on the cheapest
available model (`gpt-4o-mini` or `claude-haiku-5-5`), never the main conversation model. That
work happens inside `context-from-chat.py` — you do not need to pick the model yourself.

## Steps

1. **Identify the client.** Infer from the conversation or ask if ambiguous — client folder
   names match the directories at the repo root (e.g. `Acme`, `Globex`,
   `Initech (Parent Co)`). Confirm the client's `context.md` exists before proceeding.

2. **Extract the raw material.** Write a plain-text dump of what happened *in this conversation*
   relevant to that client — decisions made, systems/fields/files touched, status changes, open
   questions, next steps, owners. Do not pre-summarize or polish this into bullets yourself — that
   is the cheap model's job downstream. Just capture the substance faithfully and completely.
   Write it to a temp file in the scratchpad directory, e.g. `context-update-<client>.txt`.

3. **Run the merge script:**
   ```bash
   ./bin/s2 context-from-chat "<Client Folder Name>" /path/to/temp-file.txt
   ```
   This calls the cheap model to condense the dump into `## Current status` / `## Next steps` /
   `## Open questions / blockers` and appends a dated block to the client's `context.md`. If
   nothing substantive happened, the script prints "No substantive update" and leaves the file
   untouched — that's expected, not an error.

4. **Confirm to the user** what was appended (or that nothing was, if the script said so) — don't
   just say "done," show the actual bullets that landed in context.md so he can catch anything
   wrong before it accumulates.

## Notes

- This appends — it never rewrites or deletes existing context.md content. Safe to run multiple
  times per session if there's a natural checkpoint (e.g., after a decision lands).
- Don't invoke this automatically at the end of every conversation — only when the user asks, or
  when a skill/workflow he's running explicitly calls for a status checkpoint.
