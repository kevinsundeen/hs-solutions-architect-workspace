import json
import os
import plistlib
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import job_health as jh  # noqa: E402

THU = datetime(2026, 10, 8, 16, 0).astimezone()  # a Thursday


class ScheduleTests(unittest.TestCase):
    def test_interval(self):
        pl = {"StartInterval": 300}
        self.assertEqual(jh.next_fire(pl, THU), THU + timedelta(minutes=5))
        self.assertEqual(jh.grace(pl), timedelta(minutes=30))
        self.assertEqual(jh.grace({"StartInterval": 900}), timedelta(minutes=45))

    def test_weekly_calendar(self):
        handoff = {"StartCalendarInterval": {"Weekday": 5, "Hour": 15, "Minute": 0}}  # Fri
        self.assertEqual(jh.next_fire(handoff, THU), datetime(2026, 10, 9, 15, 0).astimezone())
        week_plan = {"StartCalendarInterval": {"Weekday": 1, "Hour": 6, "Minute": 30}}  # Mon
        self.assertEqual(jh.next_fire(week_plan, THU), datetime(2026, 10, 12, 6, 30).astimezone())

    def test_list_of_times_picks_earliest(self):
        pl = {"StartCalendarInterval": [{"Hour": 23, "Minute": 0}, {"Hour": 6, "Minute": 30}]}
        self.assertEqual(jh.next_fire(pl, THU), datetime(2026, 10, 8, 23, 0).astimezone())

    def test_keepalive_has_no_schedule(self):
        self.assertIsNone(jh.next_fire({"KeepAlive": True}, THU))


class HeartbeatTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.agents, self.hb = root / "agents", root / "hb"
        self.agents.mkdir()
        (self.agents / "com.s2.week-handoff.plist").write_bytes(plistlib.dumps(
            {"Label": "com.s2.week-handoff", "StartCalendarInterval": {"Weekday": 5, "Hour": 15, "Minute": 0}}))

    def tearDown(self):
        self.tmp.cleanup()

    def test_write_sets_next_due_from_plist(self):
        jh.write_heartbeat("week-handoff", True, now=THU, hb_dir=self.hb, agents=self.agents)
        cur = json.loads((self.hb / "week-handoff.json").read_text())
        self.assertEqual(cur["next_due"], (datetime(2026, 10, 9, 17, 0).astimezone()).isoformat())
        jh.write_heartbeat("week-handoff", False, error="boom", now=THU, hb_dir=self.hb, agents=self.agents)
        cur = json.loads((self.hb / "week-handoff.json").read_text())
        self.assertEqual(cur["last_error"], "boom")
        self.assertIn("last_ok", cur)

    def test_seed_only_jobs_without_a_file(self):
        made = jh.seed(now=THU, hb_dir=self.hb, agents=self.agents)
        self.assertEqual(made, ["week-handoff"])  # other WRAPPED jobs have no plist here
        self.assertEqual(jh.seed(now=THU, hb_dir=self.hb, agents=self.agents), [])

    def test_run_records_only_under_launchd(self):
        calls = []
        with mock.patch.object(jh, "_safe_write", lambda *a: calls.append(a)):
            with mock.patch.dict(os.environ, {"XPC_SERVICE_NAME": "0"}):
                self.assertEqual(jh.run("week-handoff", lambda: 0), 0)
            self.assertEqual(calls, [])
            with mock.patch.dict(os.environ, {"XPC_SERVICE_NAME": "com.s2.week-handoff"}):
                jh.run("week-handoff", lambda: 0)
                jh.run("week-handoff", lambda x: x, 3)
                with self.assertRaises(SystemExit):
                    jh.run("week-handoff", lambda: sys.exit(2))
                with self.assertRaises(ValueError):
                    jh.run("week-handoff", lambda: (_ for _ in ()).throw(ValueError("bad token")))
        self.assertEqual([c[1] for c in calls], [True, False, False, False])
        self.assertEqual(calls[1][2], "exit 3")
        self.assertEqual(calls[2][2], "exit 2")
        self.assertIn("bad token", calls[3][2])


class ProblemTests(unittest.TestCase):
    LISTING = "PID\tStatus\tLabel\n13719\t-15\tcom.s2.slack-bridge\n-\t0\tcom.s2.timelog\n-\t1\tcom.s2.post-call\n-\t0\tcom.other.x\n"

    def test_parse_and_flag(self):
        rows = jh.parse_launchctl(self.LISTING)
        self.assertEqual(set(rows), {"slack-bridge", "timelog", "post-call"})
        with tempfile.TemporaryDirectory() as d:
            agents = Path(d)
            (agents / "com.s2.slack-bridge.plist").write_bytes(plistlib.dumps({"KeepAlive": True}))
            lines = jh.launchd_problems(rows, agents)
            self.assertEqual(lines, ["✖ post-call: last launchd run exited 1"])  # running bridge is fine
            rows["slack-bridge"]["pid"] = None
            self.assertTrue(any("slack-bridge: not running" in l for l in jh.launchd_problems(rows, agents)))

    def test_auth(self):
        env = {"SLACK_USER_TOKEN": "u", "SLACK_BOT_TOKEN": "b", "TEAMWORK_API_KEY": "k"}
        lines = jh.auth_problems(env, slack_fn=lambda t: "invalid_auth" if t == "b" else None,
                                 teamwork_fn=lambda: (_ for _ in ()).throw(RuntimeError("401 Unauthorized")))
        self.assertEqual(lines, ["✖ auth: SLACK_BOT_TOKEN invalid_auth", "✖ auth: Teamwork 401 Unauthorized"])
        self.assertEqual(jh.auth_problems(env, slack_fn=lambda t: None, teamwork_fn=lambda: None), [])

    def test_auth_skips_teamwork_without_key(self):
        def boom():
            raise AssertionError("teamwork checked")
        self.assertEqual(jh.auth_problems({}, slack_fn=lambda t: None, teamwork_fn=boom), [])

    def test_heartbeats_flags_missed(self):
        d = Path(tempfile.mkdtemp())
        (d / "a.json").write_text(json.dumps({"next_due": "2026-01-01T00:00:00+00:00"}), encoding="utf-8")
        hb = jh.heartbeats(d, now=datetime.fromisoformat("2026-01-02T00:00:00+00:00"))
        self.assertTrue(hb["a"]["missed"])


if __name__ == "__main__":
    unittest.main()
