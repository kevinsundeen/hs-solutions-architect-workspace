#!/usr/bin/env python3
"""
Optional LLM calls for Phase 2 (summaries, prep briefs, context enrichment).
Uses OPENAI_API_KEY or ANTHROPIC_API_KEY from env. Returns None if no key or on error.
"""

import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.request

try:
    import certifi
    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CONTEXT = ssl.create_default_context()


def _preferred_provider_from_env() -> str:
    """
    Returns 'openai', 'anthropic', or 'claude-cli' when the user explicitly prefers one.

    Supported env vars:
    - S2_LLM_PROVIDER=openai|anthropic|claude-cli
    - LLM_PROVIDER=openai|anthropic|claude-cli
    - PREFER_ANTHROPIC=true (shorthand for anthropic)

    claude-cli: shells out to the `claude` binary (Claude Code CLI) using the
    authenticated claude.ai session — no API key needed.
    """
    provider = (os.environ.get("S2_LLM_PROVIDER") or os.environ.get("LLM_PROVIDER") or "").strip().lower()
    if provider in ("openai", "anthropic", "claude-cli"):
        return provider
    prefer_anthropic = (os.environ.get("PREFER_ANTHROPIC") or "").strip().lower()
    if prefer_anthropic in ("1", "true", "yes", "y", "on"):
        return "anthropic"
    return ""


def _strict_provider() -> bool:
    """
    When strict is enabled and the preferred provider is unavailable (missing key),
    do not fall back to the other provider.
    """
    return _env_truthy("S2_LLM_PROVIDER_STRICT")


def _get_api_key(prefer: str = "") -> tuple[str | None, str]:
    """Return (api_key, provider) for OpenAI or Anthropic. provider is 'openai' or 'anthropic'."""
    prefer = (prefer or _preferred_provider_from_env() or "").strip().lower()
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    # S2_ANTHROPIC_API_KEY is the organization key — prefer it over a personal ANTHROPIC_API_KEY.
    anthropic_key = os.environ.get("S2_ANTHROPIC_API_KEY", "").strip() or os.environ.get("ANTHROPIC_API_KEY", "").strip()

    if prefer == "anthropic" and anthropic_key:
        return anthropic_key, "anthropic"
    if prefer == "openai" and openai_key:
        return openai_key, "openai"
    if prefer in ("openai", "anthropic") and _strict_provider():
        return None, ""

    # Default precedence (historical behavior): OpenAI first.
    if openai_key:
        return openai_key, "openai"
    if anthropic_key:
        return anthropic_key, "anthropic"
    return None, ""


def _get_perplexity_key() -> str | None:
    """Return PERPLEXITY_API_KEY if set."""
    return os.environ.get("PERPLEXITY_API_KEY", "").strip() or None


def _env_truthy(key: str) -> bool:
    v = (os.environ.get(key) or "").strip().lower()
    return v in ("1", "true", "yes", "y", "on")


def _log_usage(prefix: str, model: str | None, usage: dict) -> None:
    if not _env_truthy("S2_LLM_LOG_USAGE"):
        return
    if not isinstance(usage, dict):
        return
    in_tok = usage.get("input_tokens")
    out_tok = usage.get("output_tokens")
    if not isinstance(in_tok, int) or not isinstance(out_tok, int):
        return
    cache_create = usage.get("cache_creation_input_tokens")
    cache_read = usage.get("cache_read_input_tokens")
    extra = []
    if isinstance(cache_create, int):
        extra.append(f"cache_create_input_tokens={cache_create}")
    if isinstance(cache_read, int):
        extra.append(f"cache_read_input_tokens={cache_read}")
    extra_s = f" ({', '.join(extra)})" if extra else ""
    model_s = model or "(default)"
    print(f"[llm_helper] {prefix} usage: model={model_s} input_tokens={in_tok} output_tokens={out_tok}{extra_s}", file=sys.stderr)
    if _env_truthy("S2_LLM_LOG_USAGE_VERBOSE"):
        try:
            print(f"[llm_helper] {prefix} usage_raw: {usage!r}", file=sys.stderr)
        except Exception:
            pass


def _cache_enabled() -> bool:
    """
    Enable Anthropic prompt caching for large, repeated instruction blocks.
    """
    return _env_truthy("S2_LLM_CACHE")


def _cache_ttl() -> str:
    ttl = (os.environ.get("S2_LLM_CACHE_TTL") or "1h").strip()
    return ttl if ttl in ("5m", "1h") else "1h"


def perplexity_research(instruction: str, user_text: str, max_tokens: int = 4000) -> str | None:
    """
    Call Perplexity Sonar API for web-grounded research. Uses live search.
    instruction = system prompt, user_text = research query + context.
    Returns reply text or None. Requires PERPLEXITY_API_KEY.
    """
    api_key = _get_perplexity_key()
    if not api_key:
        return None
    model = os.environ.get("PERPLEXITY_MODEL", "sonar")
    url = "https://api.perplexity.ai/chat/completions"
    body = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": instruction[:8000]},
            {"role": "user", "content": user_text[:12000]},
        ],
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120, context=_SSL_CONTEXT) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"[llm_helper] Perplexity HTTPError {e.code}: {e.reason}")
        try:
            print(e.read().decode(errors="replace")[:1500])
        except Exception:
            pass
        return None
    except Exception as e:
        print(f"[llm_helper] Perplexity error: {e}")
        return None
    choice = data.get("choices", [{}])[0]
    return (choice.get("message") or {}).get("content", "").strip() or None


# ── TypeSafe Jev (typed judgments: choice / noul / score) ─────────────────────
# Jev returns labels and probabilities, never text. Use it wherever a prompt ends in
# "reply with exactly one of ...". Docs: https://docs.typesafe.ai/api.md
# State limit is 32k tokens (state + longest question); callers must trim long input.
# Meeting content sent here goes to a third-party API; callers decide what to include.

JEV_URL = "https://api.typesafe.ai/v1/systemone"


def _get_jev_key() -> str | None:
    return (os.environ.get("TYPESAFE_API_KEY") or "").strip() or None


def jev_available() -> bool:
    return bool(_get_jev_key()) and not _env_truthy("S2_JEV_DISABLE")


def jev_evaluate(state, questions: dict, model: str | None = None) -> dict | None:
    """
    POST one state + a map of questions. Returns the `answers` map, or None on error.
    Retries 429 and 5xx (529 overloaded, Cloudflare 520s) and timeouts with backoff.
    """
    api_key = _get_jev_key()
    if not api_key:
        return None
    body = {"state": state, "model": model or os.environ.get("S2_JEV_MODEL", "jev-latest"), "questions": questions}
    payload = json.dumps(body).encode()
    for attempt in range(4):
        req = urllib.request.Request(
            JEV_URL,
            data=payload,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60, context=_SSL_CONTEXT) as resp:
                data = json.loads(resp.read().decode())
            _log_usage("Jev", data.get("model"), data.get("usage") or {})
            return data.get("answers") or None
        except urllib.error.HTTPError as e:
            if (e.code == 429 or e.code >= 500) and attempt < 3:
                try:
                    wait = float(e.headers.get("retry-after") or 0)
                except ValueError:
                    wait = 0
                time.sleep(wait or 2 ** attempt)
                continue
            try:
                detail = e.read().decode(errors="replace")[:500]
            except Exception:
                detail = ""
            print(f"[llm_helper] Jev HTTPError {e.code}: {detail}", file=sys.stderr)
            return None
        except (TimeoutError, urllib.error.URLError) as e:
            if attempt < 3:
                time.sleep(2 ** attempt)
                continue
            print(f"[llm_helper] Jev error: {e}", file=sys.stderr)
            return None
        except Exception as e:
            print(f"[llm_helper] Jev error: {e}", file=sys.stderr)
            return None
    return None


def jev_choice(state, instructions, criteria: dict, model: str | None = None) -> dict | None:
    """One Choice question. Returns {choice, probabilities, confidence} or None."""
    answers = jev_evaluate(state, {"q": {"type": "choice", "instructions": instructions, "criteria": criteria}}, model)
    return (answers or {}).get("q")


def jev_noul(state, instructions, criteria: dict | None = None, model: str | None = None) -> float | None:
    """One yes/no question. Returns P(yes) in [0, 1] or None."""
    q = {"type": "noul", "instructions": instructions}
    if criteria:
        q["criteria"] = criteria
    answer = (jev_evaluate(state, {"q": q}, model) or {}).get("q") or {}
    value = answer.get("noul")
    return float(value) if isinstance(value, (int, float)) else None


def _claude_cli_message(text: str, instruction: str, max_tokens: int, model: str | None = None) -> str | None:
    """
    Call the Claude Code CLI (`claude -p`) as a subprocess, using the authenticated
    claude.ai session. No API key required — billed to whatever account Claude Code
    is logged into (e.g. a team workspace account).

    Falls back gracefully to None if the binary is missing or the call fails.
    """
    import shutil
    import subprocess as _sp

    claude_bin = (
        os.environ.get("CLAUDE_CLI_PATH", "").strip()
        or shutil.which("claude")
        or os.path.expanduser("~/.local/bin/claude")
    )
    if not os.path.isfile(claude_bin):
        print(f"[llm_helper] claude-cli: binary not found at {claude_bin}", file=sys.stderr)
        return None

    # Fold system + user into a single prompt (claude -p has no separate system turn)
    full_prompt = f"{instruction}\n\n---\n\n{text}"
    cmd = [claude_bin, "--print", full_prompt]
    if model and isinstance(model, str) and "claude" in model.lower():
        cmd += ["--model", model]

    try:
        result = _sp.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            out = result.stdout.strip()
            return out or None
        print(f"[llm_helper] claude-cli exit {result.returncode}: {result.stderr[:300]}", file=sys.stderr)
        return None
    except _sp.TimeoutExpired:
        print("[llm_helper] claude-cli timed out after 120s", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[llm_helper] claude-cli error: {e}", file=sys.stderr)
        return None


def summarize(
    text: str,
    instruction: str,
    max_tokens: int = 300,
    model: str | None = None,
    max_input_chars: int | None = None,
) -> str | None:
    """
    Send text + instruction to LLM; return model's reply or None.
    instruction is e.g. "Summarize in one short sentence." or "List 3-5 bullet points."
    max_input_chars: truncate user text (default 12000 for OpenAI chat path; Anthropic same).
    """
    if not text.strip():
        return None

    limit = max_input_chars if max_input_chars is not None else 12000
    text = text[:limit]

    # claude-cli: shell out to the Claude Code binary, no API key needed
    if _preferred_provider_from_env() == "claude-cli":
        try:
            return _claude_cli_message(text, instruction, max_tokens, model=model)
        except Exception as e:
            print(f"[llm_helper] summarize error: {e}", file=sys.stderr)
            return None

    # If a model is explicitly provided, infer preferred provider from it.
    inferred = ""
    if model and isinstance(model, str):
        ml = model.strip().lower()
        if "claude" in ml:
            inferred = "anthropic"
        elif ml.startswith("gpt-") or "deep-research" in ml or "o4" in ml:
            inferred = "openai"
    api_key, provider = _get_api_key(prefer=inferred)
    if not api_key:
        return None
    try:
        if provider == "openai":
            return _openai_chat(text, instruction, max_tokens, model=model)
        if provider == "anthropic":
            return _anthropic_message(text, instruction, max_tokens, model=model)
    except Exception as e:
        print(f"[llm_helper] summarize error: {e}", file=sys.stderr)
        return None
    return None


def _openai_chat(text: str, instruction: str, max_tokens: int, model: str | None = None) -> str | None:
    api_key, _ = _get_api_key(prefer="openai")
    if not api_key:
        return None
    model_name = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    # Deep research / Responses API path: use /v1/responses for models like o4-mini-deep-research
    if "deep-research" in model_name:
        url = "https://api.openai.com/v1/responses"
        input_text = text[:12000]
        body = {
            "model": model_name,
            "instructions": instruction,
            "input": input_text,
            "max_output_tokens": max_tokens,
            # Enable web access for deep research models.
            "tools": [{"type": "web_search"}],
        }
        # Log request for debugging (no full content to keep output readable)
        print("[llm_helper] Deep-research request:")
        print(f"  URL: {url}")
        print(f"  model: {model_name}")
        print(f"  max_output_tokens: {max_tokens}")
        print(f"  tools: {body['tools']}")
        print(f"  instructions length: {len(instruction)} chars")
        print(f"  input length: {len(input_text)} chars")
        print(f"  instructions (first 300 chars): {instruction[:300]!r}")
        print(f"  input (first 300 chars): {input_text[:300]!r}")
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        # Deep research can run 10+ min; use 10 min read timeout so accepted requests can finish.
        timeout_sec = int(os.environ.get("OPENAI_DEEP_RESEARCH_TIMEOUT", "600"))
        print(f"  timeout: {timeout_sec}s")
        max_retries = 4  # initial + 3 retries on 429
        data = None
        for attempt in range(max_retries):
            if attempt > 0:
                print(f"[llm_helper] Retry {attempt}/{max_retries - 1}...")
            print("[llm_helper] Sending request...")
            try:
                with urllib.request.urlopen(req, timeout=timeout_sec, context=_SSL_CONTEXT) as resp:
                    data = json.loads(resp.read().decode())
                print("[llm_helper] Deep-research response received.")
                break
            except urllib.error.HTTPError as e:
                body_text = ""
                try:
                    body_text = e.read().decode(errors="replace")
                except Exception:
                    pass
                print(
                    "[llm_helper] OpenAI deep-research HTTPError "
                    f"{e.code} {getattr(e, 'reason', '')}".strip()
                )
                if body_text:
                    print("[llm_helper] Response body (truncated):")
                    print(body_text[:4000])
                if e.code == 429 and attempt < max_retries - 1:
                    # TPM resets per minute: wait long enough for the bucket to reset
                    wait_sec = 65.0
                    try:
                        err_obj = json.loads(body_text)
                        msg = (err_obj.get("error") or {}).get("message") or ""
                        if "tokens per min" in msg or "TPM" in msg:
                            wait_sec = 65.0  # let the minute window roll over
                        else:
                            match = re.search(r"try again in (\d+)ms", msg, re.I)
                            if match:
                                wait_sec = max(2.0, int(match.group(1)) / 1000.0)
                    except Exception:
                        pass
                    print(f"[llm_helper] Rate limited (429). Waiting {wait_sec:.0f}s before retry...")
                    time.sleep(wait_sec)
                    continue
                return None
            except Exception as e:
                print(f"[llm_helper] OpenAI deep-research error: {e}")
                return None
        if data is None:
            return None
        # Responses API: status "incomplete" + max_output_tokens means we need a higher limit
        status = data.get("status", "")
        incomplete = data.get("incomplete_details") or {}
        if status == "incomplete" and incomplete.get("reason") == "max_output_tokens":
            usage = data.get("usage") or {}
            out_tok = usage.get("output_tokens", 0)
            print(f"[llm_helper] Response incomplete: hit max_output_tokens (used {out_tok} output tokens). Increase max_output_tokens for deep research.")
        # Extract text: top-level output_text, or output[].content[].text, or output[].content[].output_text
        if "output_text" in data:
            result = (data.get("output_text") or "").strip() or None
            if result:
                return result
        out = []
        for item in data.get("output", []):
            # Message block: content list with output_text / text parts
            for content in item.get("content", []):
                if content.get("type") in ("output_text", "text"):
                    out.append(content.get("text", ""))
            # Some shapes have a direct "text" key on the item
            if item.get("text"):
                out.append(item["text"])
        result = ("\n".join(out)).strip() or None
        if not result:
            # Log response shape so we can fix parsing when API returns unexpected structure
            print("[llm_helper] Deep-research response had no extractable content. Response shape:")
            print(f"  Top-level keys: {list(data.keys())}")
            for k in data:
                v = data[k]
                if isinstance(v, list):
                    print(f"  {k}: list len={len(v)}")
                    if v and isinstance(v[0], dict):
                        print(f"    first item keys: {list(v[0].keys())}")
                elif isinstance(v, str):
                    print(f"  {k}: str len={len(v)}, first 200 chars: {v[:200]!r}")
                else:
                    print(f"  {k}: {type(v).__name__} = {repr(v)[:150]}")
            print("[llm_helper] Raw response (truncated 3000 chars):")
            print(json.dumps(data, indent=2)[:3000])
        return result

    # Default path: Chat Completions
    # Newer models (gpt-5.4, gpt-5-mini) require max_completion_tokens instead of max_tokens.
    url = "https://api.openai.com/v1/chat/completions"
    use_completion_tokens = model_name.startswith("gpt-5") or "gpt-5" in model_name
    body = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": instruction},
            {"role": "user", "content": text},
        ],
    }
    if use_completion_tokens:
        body["max_completion_tokens"] = max_tokens
    else:
        body["max_tokens"] = max_tokens
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30, context=_SSL_CONTEXT) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode(errors="replace")
        except Exception:
            pass
        err_msg = body[:800] if body else e.reason
        print(f"[llm_helper] OpenAI HTTP {e.code}: {err_msg}", file=sys.stderr)
        raise
    choice = data.get("choices", [{}])[0]
    return (choice.get("message") or {}).get("content", "").strip() or None


def _anthropic_request(api_key: str, body: dict) -> dict:
    url = "https://api.anthropic.com/v1/messages"
    headers: dict[str, str] = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers=headers,
        method="POST",
    )
    timeout_sec = int(os.environ.get("ANTHROPIC_TIMEOUT", "120"))
    with urllib.request.urlopen(req, timeout=timeout_sec, context=_SSL_CONTEXT) as resp:
        return json.loads(resp.read().decode())


THINKING_MIN_TOKENS = 1024


def _min_tokens(model: str, max_tokens: int) -> int:
    """5.5 models think by default, and max_tokens covers the thinking too: a one-word gate at
    max_tokens=8 ends inside the thinking block and returns no text. Raise small budgets rather
    than turning thinking off — off, the call-coach gate answered SKIP on a client weekly sync
    3/3, on it answered COACH 3/3 (2026-10-08). Short prompts still return short answers."""
    if (model or "").lower().startswith(("claude-sonnet-5", "claude-haiku-5", "claude-opus-5", "claude-fable-5")):
        return max(max_tokens, THINKING_MIN_TOKENS)
    return max_tokens


def _anthropic_message(text: str, instruction: str, max_tokens: int, model: str | None = None) -> str | None:
    org_key = os.environ.get("S2_ANTHROPIC_API_KEY", "").strip()
    personal_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    api_key = org_key or personal_key
    system: str | list[dict]
    if _cache_enabled():
        system = [
            {
                "type": "text",
                "text": instruction,
                "cache_control": {"type": "ephemeral", "ttl": _cache_ttl()},
            }
        ]
    else:
        system = instruction
    body = {
        "model": model or os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5"),
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": text}],
    }
    body["max_tokens"] = _min_tokens(body["model"], max_tokens)
    try:
        data = _anthropic_request(api_key, body)
    except urllib.error.HTTPError as e:
        # Org key out of credit/invalid — fall back to personal key if we have a different one.
        if api_key == org_key and personal_key and personal_key != org_key:
            try:
                err_body = e.read().decode(errors="replace")
            except Exception:
                err_body = ""
            print(
                f"[llm_helper] S2_ANTHROPIC_API_KEY failed ({e.code}: {err_body[:200]}); "
                "falling back to personal ANTHROPIC_API_KEY",
                file=sys.stderr,
            )
            data = _anthropic_request(personal_key, body)
        else:
            raise
    _log_usage("Anthropic", body.get("model"), data.get("usage") or {})
    for block in data.get("content", []):
        if block.get("type") == "text":
            return block.get("text", "").strip() or None
    return None


