#!/usr/bin/env python3
"""
Full context update for one client: structure + AI summary + Teamwork tasks in one context.md.

Usage: python context-full.py <client-name>

1. Runs update-context.py (transcript index, deliverables, recent transcripts list).
2. If OPENAI/ANTHROPIC key: summarizes engagement from context + last 5–7 transcripts + research-background,
   writes result into context.md as ## AI summary (replacing or adding).
3. If Teamwork configured + _meta/teamwork-clients.txt: fetches tasks assigned to you for this client's project(s),
   writes ## Teamwork — My tasks into context.md.

Result: context.md is the single up-to-date source (structure + AI + tasks).
"""

import json
import os
import re
import ssl
import subprocess
import sys
import urllib.request
from pathlib import Path


def _dialogue(text: str) -> str:
    """Verbatim dialogue below the `## Transcript` marker; whole text if there is no marker."""
    i = text.find("\n## Transcript")
    return text[i + 1:] if i != -1 else text

try:
    import certifi
    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CONTEXT = ssl.create_default_context()


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


def _get_project_substrings_for_client(meta: Path, client_name: str) -> list[str]:
    """Return list of Teamwork project substrings that map to this client (from teamwork-clients.txt)."""
    f = meta / "teamwork-clients.txt"
    if not f.is_file():
        return []
    out = []
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip()
        if val == client_name and key:
            out.append(key)
    return out


def _fetch_my_teamwork_tasks_for_client(site: str, api_key: str, project_substrings: list[str]) -> list[dict]:
    """Fetch tasks assigned to me, filter to those in projects matching any of project_substrings."""
    import base64
    if "." in site and " " not in site:
        base_url = f"https://{site}"
    else:
        base_url = f"https://{site}.teamwork.com"
    auth = base64.b64encode(f":{api_key}".encode()).decode()
    headers = {"Authorization": f"Basic {auth}", "Content-Type": "application/json"}
    try:
        req = urllib.request.Request(f"{base_url}/me.json", headers=headers)
        with urllib.request.urlopen(req, timeout=10, context=_SSL_CONTEXT) as resp:
            me = json.loads(resp.read().decode())
        person_id = str(me.get("person", {}).get("id", ""))
        if not person_id:
            return []
    except Exception:
        return []

    seen = set()
    out = []
    for filter_name in ("overdue", "today", "thisweek"):
        try:
            url = f"{base_url}/tasks.json?filter={filter_name}&pageSize=50"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10, context=_SSL_CONTEXT) as resp:
                data = json.loads(resp.read().decode())
        except Exception:
            continue
        for t in data.get("todo-items", []):
            tid = t.get("id")
            if tid in seen:
                continue
            rp = (t.get("responsible-party-ids") or "").strip()
            if person_id not in rp.split(","):
                continue
            project = (t.get("project-name") or "")
            if not project_substrings or any(sub.lower() in project.lower() for sub in project_substrings):
                seen.add(tid)
                due = t.get("due-date") or ""
                due_ymd = due[:10] if due and len(due) >= 10 else ""
                out.append({
                    "content": (t.get("content") or "").strip(),
                    "due_ymd": due_ymd,
                    "project": project,
                })
    return out


def _replace_or_add_section(content: str, section_title: str, new_body: str) -> str:
    """Replace existing ## section_title... with new content, or append if missing."""
    pattern = re.compile(r"\n## " + re.escape(section_title) + r"\n.*?(?=\n## |\Z)", re.DOTALL)
    new_section = f"\n## {section_title}\n\n{new_body.strip()}\n\n"
    if pattern.search(content):
        return pattern.sub(new_section, content, count=1)
    # Append before ## Transcripts if present, else at end
    if "## Transcripts" in content:
        content = content.replace("## Transcripts", new_section + "## Transcripts", 1)
    else:
        content = content.rstrip() + "\n\n" + new_section
    return content


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent.parent
    meta = repo_root / "_meta"
    _load_env(repo_root)

    if len(sys.argv) < 2:
        print("Usage: s2 context <client-name>   (or: python context-full.py <client-name>)")
        sys.exit(1)
    client = sys.argv[1]
    client_dir = repo_root / client
    context_path = client_dir / "context.md"
    if not context_path.is_file():
        print(f"No context.md in {client}")
        sys.exit(1)

    # 1) Run update-context.py for structure (transcript index, deliverables, recent list)
    print(f"Updating context for: {client}")
    subprocess.run(
        [sys.executable, str(script_dir / "update-context.py"), str(client_dir)],
        cwd=str(repo_root),
        check=True,
    )
    content = context_path.read_text(encoding="utf-8", errors="replace")

    # 2) AI summary: deeper engagement state from context + more transcripts + research-background
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))
    try:
        import llm_helper
        from prompts_loader import get_prompt
    except ImportError:
        llm_helper = None
    if llm_helper and llm_helper._get_api_key()[0]:
        parts = [content[:8000]]
        trans_dir = client_dir / "transcripts"
        if trans_dir.is_dir():
            for f in sorted(trans_dir.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)[:7]:
                parts.append(f"Transcript {f.name}:\n" + _dialogue(f.read_text(encoding="utf-8", errors="replace"))[:5000])
        research_bg = client_dir / "research-background.md"
        if research_bg.is_file():
            parts.append("\n\nExternal background:\n" + research_bg.read_text(encoding="utf-8", errors="replace")[:4000])
        prompt = get_prompt("enrich-context") or (
            "Based on the context and recent transcripts, output exactly three sections in markdown:\n"
            "## Current status (3-5 bullets)\n## Next steps (3-5 bullets)\n"
            "## Key themes / open questions (2-4 bullets)\nNo other commentary."
        )
        enrich_model = os.environ.get("CONTEXT_ENRICH_MODEL") or os.environ.get("OPENAI_MODEL")
        text = "\n\n".join(parts)
        result = llm_helper.summarize(text, prompt, max_tokens=800, model=enrich_model, max_input_chars=len(text))
        if result:
            content = _replace_or_add_section(content, "AI summary", result)
            # Keep context-ai.md in sync for backward compatibility
            (client_dir / "context-ai.md").write_text(
                f"# AI-generated status — {client}\n*Refreshed by s2 context*\n\n{result}\n",
                encoding="utf-8",
            )
            print("  ✓ AI summary updated (context.md + context-ai.md)")
    else:
        print("  (No OPENAI/ANTHROPIC key — skipping AI summary)")

    # 3) Teamwork: my tasks for this client
    site = os.environ.get("TEAMWORK_SITE", "").strip()
    tw_key = os.environ.get("TEAMWORK_API_KEY", "").strip()
    if site and tw_key:
        project_subs = _get_project_substrings_for_client(meta, client)
        tasks = _fetch_my_teamwork_tasks_for_client(site, tw_key, project_subs) if project_subs else []
        if tasks:
            lines = []
            for t in tasks[:20]:
                due = f" — due {t['due_ymd']}" if t["due_ymd"] else ""
                lines.append(f"- [ ] {t['content'][:120]}{due}")
            body = "\n".join(lines) + "\n"
            content = _replace_or_add_section(content, "Teamwork — My tasks", body)
            print(f"  ✓ Teamwork: {len(tasks)} task(s) for this client")
        elif project_subs:
            content = _replace_or_add_section(content, "Teamwork — My tasks", "No outstanding tasks assigned to you for this client.\n")
            print("  ✓ Teamwork: no tasks for this client")
        else:
            print("  (Teamwork configured but no project mapping for this client in _meta/teamwork-clients.txt)")
    else:
        print("  (Teamwork not configured — set TEAMWORK_SITE and TEAMWORK_API_KEY for tasks)")

    context_path.write_text(content, encoding="utf-8")
    print("Done.")


if __name__ == "__main__":
    main()
