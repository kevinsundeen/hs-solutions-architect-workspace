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


def _get_api_key() -> tuple[str | None, str]:
    """Return (api_key, provider) for OpenAI or Anthropic. provider is 'openai' or 'anthropic'."""
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if key:
        return key, "openai"
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key:
        return key, "anthropic"
    return None, ""


def _get_perplexity_key() -> str | None:
    """Return PERPLEXITY_API_KEY if set."""
    return os.environ.get("PERPLEXITY_API_KEY", "").strip() or None


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


def summarize(text: str, instruction: str, max_tokens: int = 300, model: str | None = None) -> str | None:
    """
    Send text + instruction to LLM; return model's reply or None.
    instruction is e.g. "Summarize in one short sentence." or "List 3-5 bullet points."
    """
    if not text.strip():
        return None
    api_key, provider = _get_api_key()
    if not api_key:
        return None
    try:
        if provider == "openai":
            return _openai_chat(text, instruction, max_tokens, model=model)
        if provider == "anthropic":
            return _anthropic_message(text, instruction, max_tokens)
    except Exception as e:
        print(f"[llm_helper] summarize error: {e}", file=sys.stderr)
        return None
    return None


def _openai_chat(text: str, instruction: str, max_tokens: int, model: str | None = None) -> str | None:
    api_key, _ = _get_api_key()
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
            print(
                "[llm_helper] Response incomplete: hit max_output_tokens "
                f"(used {out_tok} output tokens). Increase max_output_tokens for deep research."
            )
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
            {"role": "user", "content": text[:12000]},
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


def _anthropic_message(text: str, instruction: str, max_tokens: int) -> str | None:
    api_key, _ = _get_api_key()
    url = "https://api.anthropic.com/v1/messages"
    body = {
        "model": os.environ.get("ANTHROPIC_MODEL", "claude-3-5-haiku-20241022"),
        "max_tokens": max_tokens,
        "system": instruction,
        "messages": [{"role": "user", "content": text[:12000]}],
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30, context=_SSL_CONTEXT) as resp:
        data = json.loads(resp.read().decode())
    for block in data.get("content", []):
        if block.get("type") == "text":
            return block.get("text", "").strip() or None
    return None

