#!/usr/bin/env python3
"""Tell the workspace owner something: Slack DM when tokens are set, otherwise stdout.

Needs SLACK_USER_TOKEN (to find who "me" is) and SLACK_BOT_TOKEN (to send); with only one
set it raises SlackError. Stdlib only.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request


class SlackError(RuntimeError):
    pass


def slack_api(method: str, token: str, **params) -> dict:
    if not token:
        raise SlackError(f"{method}: no token")
    data = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}).encode()
    req = urllib.request.Request(f"https://slack.com/api/{method}", data=data,
                                 headers={"Authorization": f"Bearer {token}",
                                          "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode())
    if not body.get("ok"):
        raise SlackError(f"{method}: {body.get('error')} {body.get('needed') or ''}".strip())
    return body


def dm_self(text: str, env=os.environ, api=slack_api) -> str:
    user_tok, bot_tok = env.get("SLACK_USER_TOKEN", ""), env.get("SLACK_BOT_TOKEN", "")
    if not (user_tok or bot_tok):
        print(f"[notify] {text}", flush=True)
        return "stdout"
    if not (user_tok and bot_tok):
        missing = "SLACK_USER_TOKEN" if not user_tok else "SLACK_BOT_TOKEN"
        raise SlackError(f"{missing} missing (the other Slack token is set)")
    me = api("auth.test", user_tok)["user_id"]
    ch = api("conversations.open", bot_tok, users=me)["channel"]["id"]
    api("chat.postMessage", bot_tok, channel=ch, text=text[:39000], unfurl_links="false")
    return "slack"
