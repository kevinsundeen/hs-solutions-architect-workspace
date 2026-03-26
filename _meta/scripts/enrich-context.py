#!/usr/bin/env python3
"""
Phase 2: AI-enrich a client's context with Current status, Next steps, Key themes from recent transcripts.
Writes to context-ai.md (or appends a section to context.md). Run: python enrich-context.py <client-name>
Requires OPENAI_API_KEY or ANTHROPIC_API_KEY in env.
"""

import os
import sys
from pathlib import Path
from datetime import datetime


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

    if len(sys.argv) < 2:
        print("Usage: python enrich-context.py <client-name>")
        sys.exit(1)
    client = sys.argv[1]
    client_dir = repo_root / client
    context_md = client_dir / "context.md"
    if not context_md.is_file():
        print(f"No context.md in {client}")
        sys.exit(1)

    # Optional: add script dir for llm_helper
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))
    try:
        import llm_helper
    except ImportError:
        print("LLM helper not found. Set OPENAI_API_KEY or ANTHROPIC_API_KEY in .env")
        sys.exit(1)
    if not llm_helper._get_api_key()[0]:
        print("Set OPENAI_API_KEY or ANTHROPIC_API_KEY in .env")
        sys.exit(1)

    # Gather: context.md + last 2-3 transcripts
    parts = [context_md.read_text(encoding="utf-8", errors="replace")[:8000]]
    trans_dir = client_dir / "transcripts"
    if trans_dir.is_dir():
        for f in sorted(trans_dir.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)[:3]:
            parts.append(f"Transcript {f.name}:\n" + f.read_text(encoding="utf-8", errors="replace")[:5000])
    # Optionally include deep research background if it exists
    research_bg = client_dir / "research-background.md"
    if research_bg.is_file():
        parts.append("\n\nExternal background:\n" + research_bg.read_text(encoding="utf-8", errors="replace")[:4000])
    text = "\n\n".join(parts)

    from prompts_loader import get_prompt

    prompt = get_prompt("enrich-context")
    if not prompt:
        prompt = "Summarize context, recent transcripts, and external background (if present) into Current status, Next steps, and Key themes. Use markdown bullets."

    result = llm_helper.summarize(text, prompt, max_tokens=600)
    if not result:
        print("No response from LLM")
        sys.exit(1)

    out_path = client_dir / "context-ai.md"
    out_path.write_text(
        f"# AI-generated status — {client}\n*Last run: {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n\n{result}\n",
        encoding="utf-8",
    )
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()

