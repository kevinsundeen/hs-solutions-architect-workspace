import contextlib
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import notify  # noqa: E402


class DmSelfTests(unittest.TestCase):
    def test_stdout_without_tokens(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(notify.dm_self("hello", env={}, api=None), "stdout")
        self.assertEqual(buf.getvalue(), "[notify] hello\n")

    def test_slack_with_tokens(self):
        calls = []

        def api(method, token, **p):
            calls.append((method, token, p))
            return {"auth.test": {"user_id": "U1"}, "conversations.open": {"channel": {"id": "D1"}}}.get(method, {})
        env = {"SLACK_USER_TOKEN": "u", "SLACK_BOT_TOKEN": "b"}
        self.assertEqual(notify.dm_self("x" * 40000, env=env, api=api), "slack")
        self.assertEqual([c[:2] for c in calls], [("auth.test", "u"), ("conversations.open", "b"),
                                                   ("chat.postMessage", "b")])
        self.assertEqual(len(calls[2][2]["text"]), 39000)

    def test_one_token_raises(self):
        # Half-configured Slack is a broken setup, not "no Slack": fail loud so the job shows red.
        for env in ({"SLACK_USER_TOKEN": "u"}, {"SLACK_BOT_TOKEN": "b"}):
            with self.assertRaisesRegex(notify.SlackError, "SLACK_(USER|BOT)_TOKEN missing"):
                notify.dm_self("hi", env=env, api=None)
