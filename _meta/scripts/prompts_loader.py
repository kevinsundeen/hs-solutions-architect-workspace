#!/usr/bin/env python3
"""
Load prompts from _meta/prompts/<key>.txt. Edit those files to change AI behavior; fallback to built-in defaults if missing.
"""

from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

_DEFAULTS = {
    "enrich-context": """Based on the context and recent transcripts, output exactly three sections in markdown:

## Current status (3-5 bullets)
## Next steps (3-5 bullets)
## Key themes / open questions (last 30 days) (2-4 bullets)

No other commentary. Use markdown headers and bullet lists.""",
    "morning-prep-brief": "Based on the context and last transcript, give 3-5 bullet points to prep for a meeting with this client: current focus, open questions, last call takeaways, suggested talking points. One line per bullet, no numbering.",
    "morning-call-agenda-one-sentence": 'In exactly one short sentence, give the agenda or main focus for this client call. No preamble. Example: "Weekly touchbase; lifecycle cleanup and reporting scope."',
    "task-status-summary": "In one short sentence, state: current state of this task, what (if anything) is blocking, and what's next. No preamble.",
    "task-suggested-activities": "Given the client context and this task, suggest 2-4 concrete activities to keep the task moving (e.g. next step, who to follow up with, doc to update, decision to unblock). One short line per activity. No preamble or numbering.",
    "inbox-one-liner": "In one short sentence, what is this meeting about and what was agreed or next step?",
    "week-summary": "In 2-3 sentences, summarize this client's week: what calls or work happened, main topics, and any blockers or next steps. For standup.",
    "transcript-topic": "Based on this transcript preview, output ONLY a short filename-safe topic in 2-6 words, kebab-case. Examples: 360-workshop-service, discovery-kickoff, weekly-sync. No other text, no quotes.",
    "weekly-report-boss": """Turn the following raw weekly activity into a concise, professional report suitable for sending to my boss.

Include:
- Brief intro (1–2 sentences) summarizing the week.
- Key client work: which clients, what meetings or deliverables, main outcomes.
- Blockers or risks (if any).
- Next week priorities (2–4 bullets).

Keep it to about 1–2 pages. Professional tone. Use clear headings and bullets.""",
    "deep-research-spec": "Given this client's context, list 5-10 specific things to research about their company, industry, products, buyers, competitors, and tech stack that would help a HubSpot solutions architect. Use bullet points.",
    "deep-research-summary": "Summarize the external research into 3-7 bullets that describe who this client is, what they sell, who they sell to, key tech or integrations, and any strategic considerations. Write for a HubSpot solutions architect. No preamble.",
}


def get_prompt(key: str) -> str:
    """Return prompt text for the given key. Reads _meta/prompts/<key>.txt if present, else built-in default."""
    path = _PROMPTS_DIR / f"{key}.txt"
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return _DEFAULTS.get(key, "")

