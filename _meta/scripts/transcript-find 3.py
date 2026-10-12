#!/usr/bin/env python3
"""
Semantic search over a client's transcripts: "where did the client say X?"

Two-stage search:
  1. BM25 (stdlib, no deps) over small line windows built from the verbatim
     `## Transcript` section of each file — never the Fathom summary above it.
  2. Jev (TypeSafe) rerank: one Score question per BM25 candidate, fanned out
     with a thread pool in small chunks, asking how directly the passage
     answers/evidences the query. Falls back to BM25 order if Jev is
     unavailable.

Usage:
  python3 _meta/scripts/transcript-find.py <Client-Folder> "query" \
      [--since YYYY-MM-DD] [--top 10] [--candidates 60] [--context 1] [--json]

Examples:
  python3 _meta/scripts/transcript-find.py Acme "pricing discussion"
  python3 _meta/scripts/transcript-find.py "Initech (Parent Co)" \
      "integration scope" --since 2026-06-01 --top 5

Env:
  Uses the same Jev credentials as llm_helper.py (JEV_PERSONAL_S2_API_KEY or
  TYPESAFE_API_KEY in repo-root .env). No live Jev call happens without one.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import llm_helper  # noqa: E402

S2_ROOT = _SCRIPT_DIR.parent.parent


def load_env(s2_root: Path) -> None:
    """Load .env from repo root if vars not already set (mirrors post-call.py's loader,
    so this script also works when run directly, not just via `s2`)."""
    for name in (".env", "env"):
        f = s2_root / name
        if not f.is_file():
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip("'\"")
            if k and k not in os.environ:
                os.environ[k] = v
        return

LINE_RE = re.compile(r"^\[(\d{2}:\d{2}:\d{2})\]\s+([^:]+):\s*(.*)$")
TOKEN_RE = re.compile(r"[a-z0-9]+")

# Lines this short (word count) are dropped as candidate anchors unless they
# are pulled in only as neighbor-context for a real hit ("Yeah.", "Mm-hmm.").
MIN_ANCHOR_WORDS = 4

JEV_CHUNK_SIZE = 8  # concurrent Jev requests per fan-out batch
JEV_MAX_WORKERS = 8

SCORE_LEVELS = [
    "Unrelated — the passage has nothing to do with the query",
    "Tangential — mentions the general topic but does not address the query",
    "Partial — implies or hints at an answer, or covers part of it",
    "Direct — clearly answers or states evidence for the query",
]


@dataclass
class TranscriptLine:
    file: str
    date: str
    idx: int          # position within this file's verbatim lines
    ts: str
    speaker: str
    text: str


@dataclass
class Candidate:
    anchor: TranscriptLine
    window: list  # list[TranscriptLine], includes anchor + neighbors
    bm25: float = 0.0
    jev_score: float | None = None
    jev_confidence: float | None = None

    def passage_text(self) -> str:
        return "\n".join(f"{l.speaker} [{l.ts}]: {l.text}" for l in self.window)

    def anchor_repr(self) -> str:
        return f"{self.anchor.file} · {self.anchor.speaker} [{self.anchor.ts}]"


# ── Parsing ─────────────────────────────────────────────────────────────────

def date_from_filename(name: str) -> str | None:
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", name)
    return m.group(1) if m else None


def parse_transcript(path: Path) -> list[TranscriptLine]:
    """Return verbatim lines below `## Transcript`. Skips the Fathom summary above it."""
    text = path.read_text(errors="replace")
    marker = text.find("## Transcript")
    if marker < 0:
        return []
    body = text[marker + len("## Transcript"):]
    date = date_from_filename(path.name) or ""
    lines: list[TranscriptLine] = []
    idx = 0
    for raw in body.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        m = LINE_RE.match(raw)
        if not m:
            continue
        ts, speaker, content = m.groups()
        content = content.strip()
        if not content:
            continue
        lines.append(TranscriptLine(file=path.name, date=date, idx=idx, ts=ts, speaker=speaker.strip(), text=content))
        idx += 1
    return lines


def is_thin(text: str) -> bool:
    words = TOKEN_RE.findall(text.lower())
    return len(words) < MIN_ANCHOR_WORDS


def build_windows(lines: list[TranscriptLine], context: int) -> list[Candidate]:
    """One window per real (non-thin) line, that line plus `context` neighbors each side."""
    candidates = []
    for i, line in enumerate(lines):
        if is_thin(line.text):
            continue
        lo = max(0, i - context)
        hi = min(len(lines), i + context + 1)
        candidates.append(Candidate(anchor=line, window=lines[lo:hi]))
    return candidates


# ── Stage 1: stdlib BM25 ────────────────────────────────────────────────────

def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


class BM25:
    """Minimal Okapi BM25 over a list of pre-tokenized documents. Stdlib only."""

    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs = docs
        self.doc_len = [len(d) for d in docs]
        self.avgdl = (sum(self.doc_len) / len(docs)) if docs else 0.0
        self.freqs = [Counter(d) for d in docs]
        df: Counter = Counter()
        for d in docs:
            for term in set(d):
                df[term] += 1
        n = len(docs)
        self.idf = {term: math.log(1 + (n - freq + 0.5) / (freq + 0.5)) for term, freq in df.items()}

    def score(self, query_terms: list[str], i: int) -> float:
        freqs = self.freqs[i]
        dl = self.doc_len[i] or 1
        total = 0.0
        for term in query_terms:
            f = freqs.get(term, 0)
            if f == 0:
                continue
            idf = self.idf.get(term, 0.0)
            total += idf * (f * (self.k1 + 1)) / (f + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1)))
        return total


def bm25_rank(candidates: list[Candidate], query: str) -> list[Candidate]:
    docs = [tokenize(c.passage_text()) for c in candidates]
    bm25 = BM25(docs)
    q_terms = tokenize(query)
    for i, c in enumerate(candidates):
        c.bm25 = bm25.score(q_terms, i)
    return sorted(candidates, key=lambda c: c.bm25, reverse=True)


# ── Stage 2: Jev rerank ─────────────────────────────────────────────────────

def jev_score_one(query: str, candidate: Candidate) -> tuple[float | None, float | None]:
    """One Score question for one candidate. Returns (score, confidence) or (None, None)."""
    state = {
        "query": query,
        "meeting": f"{candidate.anchor.file} ({candidate.anchor.date})",
        "passage": candidate.passage_text(),
    }
    instructions = (
        f'How directly does `passage` answer or provide evidence for the query: "{query}"? '
        "Judge `passage` only; `meeting` is context, not evidence."
    )
    answers = llm_helper.jev_evaluate(
        state,
        {"q": {"type": "score", "instructions": instructions, "criteria": SCORE_LEVELS}},
    )
    q = (answers or {}).get("q") or {}
    score = q.get("score")
    conf = q.get("confidence")
    return (float(score) if isinstance(score, (int, float)) else None,
            float(conf) if isinstance(conf, (int, float)) else None)


def jev_rerank(candidates: list[Candidate], query: str) -> bool:
    """Fan out one Jev Score call per candidate, chunked. Mutates candidates in place.
    Returns True if Jev ran (even partially), False if unavailable/entirely failed."""
    if not llm_helper.jev_available():
        return False
    ran_any = False
    for start in range(0, len(candidates), JEV_CHUNK_SIZE):
        chunk = candidates[start:start + JEV_CHUNK_SIZE]
        with ThreadPoolExecutor(max_workers=min(JEV_MAX_WORKERS, len(chunk))) as pool:
            futures = {pool.submit(jev_score_one, query, c): c for c in chunk}
            for fut in as_completed(futures):
                c = futures[fut]
                try:
                    score, conf = fut.result()
                except Exception as e:
                    print(f"[transcript-find] Jev error on {c.anchor_repr()}: {e}", file=sys.stderr)
                    continue
                if score is not None:
                    ran_any = True
                c.jev_score, c.jev_confidence = score, conf
    return ran_any


# ── CLI ──────────────────────────────────────────────────────────────────────

def collect_lines(client_dir: Path, since: str | None) -> list[TranscriptLine]:
    transcripts_dir = client_dir / "transcripts"
    if not transcripts_dir.is_dir():
        return []
    lines: list[TranscriptLine] = []
    for path in sorted(transcripts_dir.glob("*.txt")):
        file_date = date_from_filename(path.name)
        if since and file_date and file_date < since:
            continue
        lines.extend(parse_transcript(path))
    return lines


def main() -> int:
    load_env(S2_ROOT)
    ap = argparse.ArgumentParser(description="Semantic search over a client's transcripts.")
    ap.add_argument("client", help="Client folder name, e.g. Acme or 'Initech (Parent Co)'")
    ap.add_argument("query", help="What to search for, e.g. 'pricing discussion'")
    ap.add_argument("--since", help="Only search transcripts whose filename date is >= YYYY-MM-DD")
    ap.add_argument("--top", type=int, default=10, help="Number of results to show (default 10)")
    ap.add_argument("--candidates", type=int, default=60, help="BM25 candidates passed to Jev rerank (default 60)")
    ap.add_argument("--context", type=int, default=1, help="Neighbor lines each side of the hit (default 1)")
    ap.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    ap.add_argument("--verbose", action="store_true", help="Show per-call Jev token usage")
    args = ap.parse_args()
    if not args.verbose:
        # One Jev call per candidate; per-call usage lines from .env's S2_LLM_LOG_USAGE drown the results.
        os.environ["S2_LLM_LOG_USAGE"] = "0"
        os.environ["S2_LLM_LOG_USAGE_VERBOSE"] = "0"

    client_dir = S2_ROOT / args.client
    if not client_dir.is_dir():
        print(f"error: client folder not found: {client_dir}", file=sys.stderr)
        return 2

    lines = collect_lines(client_dir, args.since)
    if not lines:
        print(f"No verbatim transcript lines found under {client_dir / 'transcripts'}"
              + (f" since {args.since}" if args.since else ""), file=sys.stderr)
        return 1

    candidates = build_windows(lines, args.context)
    if not candidates:
        print("No candidate lines after filtering thin/filler lines.", file=sys.stderr)
        return 1

    ranked = bm25_rank(candidates, args.query)
    shortlist = ranked[:max(args.candidates, args.top)]

    jev_ran = jev_rerank(shortlist, args.query)

    if jev_ran:
        results = sorted(
            shortlist,
            key=lambda c: (c.jev_score if c.jev_score is not None else -1.0, c.bm25),
            reverse=True,
        )
    else:
        results = shortlist  # already BM25-sorted

    top = results[:args.top]

    if args.json:
        out = {
            "query": args.query,
            "client": args.client,
            "reranked": jev_ran,
            "results": [
                {
                    "file": c.anchor.file,
                    "speaker": c.anchor.speaker,
                    "timestamp": c.anchor.ts,
                    "date": c.anchor.date,
                    "line": c.anchor.text,
                    "window": [f"{l.speaker} [{l.ts}]: {l.text}" for l in c.window],
                    "bm25_score": round(c.bm25, 4),
                    "jev_score": c.jev_score,
                    "jev_confidence": c.jev_confidence,
                }
                for c in top
            ],
        }
        print(json.dumps(out, indent=2))
        return 0

    if not jev_ran:
        print("[Jev unavailable — showing BM25-only order. Set TYPESAFE_API_KEY / JEV_PERSONAL_S2_API_KEY to rerank.]\n")

    if not top:
        print("No results.")
        return 0

    for c in top:
        score_bits = []
        if c.jev_score is not None:
            score_bits.append(f"jev={c.jev_score:.2f}")
            if c.jev_confidence is not None:
                score_bits.append(f"conf={c.jev_confidence:.2f}")
        score_bits.append(f"bm25={c.bm25:.2f}")
        print(f"{c.anchor.file} · {c.anchor.speaker} [{c.anchor.ts}]  ({', '.join(score_bits)})")
        print(f"  {c.anchor.text}")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
