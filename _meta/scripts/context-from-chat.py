#!/usr/bin/env python3
"""
Append a session status update to a client's context.md, sourced from the
current Claude Code conversation instead of a Fathom transcript.

Always uses the cheapest available model (gpt-4o-mini / claude-haiku-5-5) to
do the summarization, regardless of S2_LLM_PROVIDER's default model — this is
a cheap, frequent, mid-conversation call, not a deep-research one.

Usage:
    python context-from-chat.py <client-name> <text-file>
    python context-from-chat.py <client-name> -   # read raw text from stdin
"""

import os
import sys
from pathlib import Path
from datetime import datetime

CHEAP_MODEL_BY_PROVIDER = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-haiku-5-5",
}

INSTRUCTION = """You are extracting a session status update for a client engagement tracker.
From the conversation excerpt below (a raw dump of what was discussed, decided, or built in a
work session), produce a terse markdown status update with these sections:

## Current status
3-5 bullets: what was discussed, decided, or built in this session. Be concrete — name specific
systems, fields, files, or decisions. No fluff, no filler, no restating the obvious.

## Next steps
1-5 bullets: what happens next, and who owns it if known.

## Open questions / blockers
0-3 bullets. Omit this section entirely if there are none.

If the excerpt has no substantive client work in it, reply with exactly: No substantive update.
"""


def _load_env(repo_root: Path) -> None:
    for name in (".env", "env"):
        f = repo_root / name
        if f.is_file():
            for line in f.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip().strip("'\"")
                if k and k not in os.environ:
                    os.environ[k] = v
            return


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent.parent
    _load_env(repo_root)

    if len(sys.argv) < 3:
        print("Usage: python context-from-chat.py <client-name> <text-file|->")
        sys.exit(1)

    client = sys.argv[1]
    text_arg = sys.argv[2]
    client_dir = repo_root / client
    context_md = client_dir / "context.md"
    if not context_md.is_file():
        print(f"No context.md in {client}")
        sys.exit(1)

    if text_arg == "-":
        raw_text = sys.stdin.read()
    else:
        raw_text = Path(text_arg).read_text(encoding="utf-8", errors="replace")

    if not raw_text.strip():
        print("No conversation text provided.")
        sys.exit(1)

    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))
    import llm_helper

    # Bypass llm_helper.summarize()'s claude-cli path on purpose: this repo's
    # .env sets S2_LLM_PROVIDER=claude-cli, which shells out to the `claude`
    # binary and picks up the user's global CLAUDE.md on every
    # call. This is a frequent, mechanical, cheap-model call — go straight to
    # the OpenAI/Anthropic API so the output is plain and the model is cheap.
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    anthropic_key = os.environ.get("S2_ANTHROPIC_API_KEY", "").strip() or os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if openai_key:
        provider, api_key = "openai", openai_key
    elif anthropic_key:
        provider, api_key = "anthropic", anthropic_key
    else:
        print("Set OPENAI_API_KEY or ANTHROPIC_API_KEY in .env")
        sys.exit(1)

    model = CHEAP_MODEL_BY_PROVIDER[provider]

    if provider == "openai":
        result = llm_helper._openai_chat(raw_text, INSTRUCTION, 500, model=model)
    else:
        result = llm_helper._anthropic_message(raw_text, INSTRUCTION, 500, model=model)
    if not result:
        print("No response from LLM")
        sys.exit(1)

    result = result.strip()
    if result.lower().startswith("no substantive update"):
        print("No substantive update — context.md left unchanged.")
        return

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    block = f"\n\n---\n_Session update — {timestamp} (via conversation, {model})_\n\n{result}\n"

    with context_md.open("a", encoding="utf-8") as f:
        f.write(block)

    print(f"Appended session update to {context_md}")


if __name__ == "__main__":
    main()
