#!/usr/bin/env python3
"""First-run setup for the workspace. Safe to re-run: it never overwrites your files or values.

Usage: s2 setup [--overlay PATH] [--no-smoke] [--keep-demo]
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SAMPLE_NAME = "2026-01-15_demo_alex-jordan_kickoff.txt"
INSTALL = {
    "claude": "npm install -g @anthropic-ai/claude-code",
}
OPTIONAL = {
    "gh": "brew install gh  (only needed if you open pull requests from the CLI)",
}


def check_prereqs(which=shutil.which, version=sys.version_info) -> list[str]:
    probs = []
    if tuple(version[:2]) < (3, 11):
        probs.append("Python 3.11+ required → brew install python@3.12")
    for tool, cmd in INSTALL.items():
        if not which(tool):
            probs.append(f"{tool} not found → {cmd}")
    return probs


def _parse(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            k, _, v = s.partition("=")
            out[k.strip()] = v.strip()
    return out


def write_env(example: Path, env: Path, ask=input) -> list[str]:
    if not env.exists():
        shutil.copyfile(example, env)
    current = _parse(env.read_text(encoding="utf-8"))
    lines = env.read_text(encoding="utf-8").splitlines()
    filled = []
    for key in _parse(example.read_text(encoding="utf-8")):
        if current.get(key):
            continue
        try:
            val = ask(f"{key} (Enter to skip): ").strip()
        except KeyboardInterrupt:
            val = ""
        except EOFError:
            break  # no more input: keep what was answered, skip the rest
        if key not in current:
            lines.append(f"{key}={val}")
        elif val:
            lines = [f"{key}={val}" if l.split("=", 1)[0].strip() == key else l for l in lines]
        if val:
            filled.append(key)
    env.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return filled


def _link(src: Path, dst: Path) -> str:
    if dst.is_symlink():
        dst.unlink()
    elif dst.exists():
        return f"kept {dst} (your file, not replaced)"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.symlink_to(src.resolve())
    return f"linked {dst}"


def _git_exclude(root: Path, rels: list[str]) -> None:
    """Keep overlay symlinks out of `git add` (the allowlist .gitignore would otherwise track them)."""
    git = root / ".git"
    if not git.is_dir() or not rels:
        return
    info = git / "info"
    info.mkdir(exist_ok=True)
    exclude = info / "exclude"
    text = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
    existing = text.splitlines()
    new = [r for r in dict.fromkeys(rels) if r not in existing]
    if not new:
        return
    with exclude.open("a", encoding="utf-8") as fh:
        if text and not text.endswith("\n"):
            fh.write("\n")
        fh.write("\n".join(new) + "\n")


def link_overlay(overlay: Path, root: Path) -> list[str]:
    actions = []
    made: list[str] = []

    def add(src: Path, dst: Path) -> None:
        action = _link(src, dst)
        actions.append(action)
        if action.startswith("linked"):
            made.append(dst.relative_to(root).as_posix())

    for src in sorted((overlay / "agents").glob("*.md")):
        add(src, root / ".claude/agents" / src.name)
    for src in sorted(p for p in (overlay / "skills").glob("*") if p.is_dir()):
        add(src, root / ".claude/skills" / src.name)
    for src in sorted(p for p in (overlay / "scripts").glob("*") if p.is_file()):
        add(src, root / "_meta/scripts" / src.name)
    for src in sorted((overlay / "scripts/cmd").glob("*.sh")):
        add(src, root / "_meta/scripts/cmd" / src.name)
    _git_exclude(root, made)
    return actions


def render_mcp(example: Path, out: Path, home: str) -> bool:
    if out.exists() or not example.exists():
        return False
    out.write_text(example.read_text(encoding="utf-8").replace("{{HOME}}", home), encoding="utf-8")
    return True


def smoke_test(root: Path, run=subprocess.run, keep: bool = False) -> bool:
    demo = root / "Demo"
    if demo.exists():
        print("✖ smoke test skipped: a Demo/ folder already exists")
        return False
    s2 = str(root / "bin" / "s2")
    ok = False
    try:
        run([s2, "new", "client", "Demo"], cwd=root, capture_output=True, text=True)
        shutil.copyfile(root / "examples/sample-transcript.txt", demo / "transcripts" / SAMPLE_NAME)
        run([s2, "context", "Demo"], cwd=root, capture_output=True, text=True)
        index = demo / "transcripts" / "transcript-index.md"
        ok = index.is_file() and SAMPLE_NAME in index.read_text(encoding="utf-8")
    except OSError as e:
        print(f"✖ smoke test error: {e}")
    finally:
        if not keep and demo.exists():
            shutil.rmtree(demo)
    return ok


USAGE = "Usage: s2 setup [--overlay PATH] [--no-smoke] [--keep-demo]"


def overlay_arg(argv: list[str]) -> Path | None:
    if "--overlay" not in argv:
        return None
    i = argv.index("--overlay")
    if i + 1 >= len(argv) or argv[i + 1].startswith("--"):
        raise ValueError("--overlay needs a PATH")
    return Path(argv[i + 1]).expanduser()


def main(argv: list[str]) -> int:
    try:
        overlay = overlay_arg(argv)
    except ValueError:
        print(USAGE)
        return 2
    for tool, cmd in OPTIONAL.items():
        if not shutil.which(tool):
            print(f"  ! {tool} not found (optional) → {cmd}")
    probs = check_prereqs()
    if probs:
        print("Fix these first, then re-run s2 setup:")
        print("\n".join(f"  ✖ {p}" for p in probs))
        return 1
    filled = write_env(ROOT / ".env.example", ROOT / ".env")
    print(f"✓ .env ready ({len(filled)} key(s) added)")
    if overlay:
        if not (overlay / "agents").is_dir():
            print(f"✖ {overlay} doesn't look like the overlay (no agents/ folder)")
            return 1
        for a in link_overlay(overlay, ROOT):
            print(f"  {a}")
    if render_mcp(ROOT / ".mcp.json.example", ROOT / ".mcp.json", str(Path.home())):
        print("✓ .mcp.json written")
    if "--no-smoke" in argv:
        return 0
    ok = smoke_test(ROOT, keep="--keep-demo" in argv)
    print("✓ smoke test PASS" if ok else "✖ smoke test FAIL — run: s2 new client Demo && s2 context Demo")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
