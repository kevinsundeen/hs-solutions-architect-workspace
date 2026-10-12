import importlib.util
import json
import plistlib
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import playbook as pbm  # noqa: E402


def ok(out="", rc=0, err=""):
    return SimpleNamespace(returncode=rc, stdout=out, stderr=err)


class ScheduleTests(unittest.TestCase):
    def test_interval(self):
        self.assertEqual(pbm.launchd_schedule({"every": "5m"}), {"StartInterval": 300, "RunAtLoad": False})
        self.assertEqual(pbm.parse_interval("90s"), 90)
        self.assertEqual(pbm.parse_interval("2h"), 7200)
        with self.assertRaises(pbm.PlaybookError):
            pbm.parse_interval("5 minutes")

    def test_weekday_times_expand(self):
        s = pbm.launchd_schedule({"at": ["07:00", "13:30"], "days": "weekdays"})
        cal = s["StartCalendarInterval"]
        self.assertEqual(len(cal), 10)
        self.assertIn({"Hour": 13, "Minute": 30, "Weekday": 5}, cal)

    def test_single_daily_time_is_a_dict(self):
        self.assertEqual(pbm.launchd_schedule({"at": "06:30"})["StartCalendarInterval"], {"Hour": 6, "Minute": 30})

    def test_named_days(self):
        cal = pbm.launchd_schedule({"at": ["15:00"], "days": ["Fri", "mon"]})["StartCalendarInterval"]
        self.assertEqual([e["Weekday"] for e in cal], [5, 1])

    def test_bad_values(self):
        for sched in ({"at": ["25:00"]}, {"at": ["7am"]}, {"at": ["07:00"], "days": ["funday"]}):
            with self.assertRaises(pbm.PlaybookError):
                pbm.launchd_schedule(sched)

    def test_keep_alive(self):
        self.assertEqual(pbm.launchd_schedule({"keep_alive": True}), {"KeepAlive": True, "RunAtLoad": True})


class ValidateTests(unittest.TestCase):
    def pb(self, **kw):
        base = {"name": "x", "schedule": {"every": "5m"}, "step": [{"run": "true"}]}
        base.update(kw)
        return base

    def test_valid(self):
        pbm.validate(self.pb())

    def test_two_schedule_modes(self):
        with self.assertRaises(pbm.PlaybookError):
            pbm.validate(self.pb(schedule={"every": "5m", "at": ["07:00"]}))

    def test_step_needs_one_kind(self):
        with self.assertRaises(pbm.PlaybookError):
            pbm.validate(self.pb(step=[{"run": "a", "dm": "b"}]))
        with self.assertRaises(pbm.PlaybookError):
            pbm.validate(self.pb(step=[]))

    def test_shipped_playbooks_load(self):
        for name in pbm.names():
            pbm.load(name)


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.pdir, self.agents = self.tmp / "pb", self.tmp / "agents"
        self.pdir.mkdir(); self.agents.mkdir()
        (self.pdir / "demo.toml").write_text('[schedule]\nevery = "5m"\n[[step]]\nrun = "echo hi"\n')
        self.calls = []
        self.lc = lambda *a: self.calls.append(a)

    def sync(self, **kw):
        import job_health
        orig, job_health.seed = job_health.seed, lambda: []
        try:
            return pbm.sync(pdir=self.pdir, agents=self.agents, launchctl=self.lc, **kw)
        finally:
            job_health.seed = orig

    def test_creates_then_unchanged(self):
        out = self.sync()
        self.assertTrue(out[0].startswith("+ demo"))
        pl = plistlib.loads((self.agents / "com.s2.demo.plist").read_bytes())
        self.assertEqual(pl["ProgramArguments"][-2:], ["run", "demo"])
        self.assertEqual(pl["StartInterval"], 300)
        self.assertTrue(self.sync()[0].startswith("= demo"))

    def test_refuses_hand_made_plist(self):
        (self.agents / "com.s2.demo.plist").write_bytes(plistlib.dumps({"Label": "com.s2.demo",
                                                                        "ProgramArguments": ["python3", "inbox.py"]}))
        out = self.sync()
        self.assertTrue(out[0].startswith("✖ demo"))
        self.assertEqual(self.calls, [])

    def test_removes_orphans_but_not_others(self):
        self.sync()
        (self.pdir / "demo.toml").unlink()
        (self.agents / "com.s2.inbox.plist").write_bytes(plistlib.dumps({"ProgramArguments": ["python3", "inbox.py"]}))
        out = self.sync()
        self.assertIn("- demo: playbook gone, unloading", out)
        self.assertFalse((self.agents / "com.s2.demo.plist").exists())
        self.assertTrue((self.agents / "com.s2.inbox.plist").exists())

    def test_dry_run_writes_nothing(self):
        self.sync(dry_run=True)
        self.assertFalse((self.agents / "com.s2.demo.plist").exists())
        self.assertEqual(self.calls, [])


class ExecuteTests(unittest.TestCase):
    def pb(self, steps):
        return {"name": "t", "schedule": {"every": "1m"}, "step": steps}

    def test_prev_flows_and_if_output_skips(self):
        sent, ran = [], []
        def sh(cmd, timeout, stdin=None):
            ran.append(cmd)
            return ok("")
        rc = pbm.execute(self.pb([{"run": "watch"}, {"dm": "{prev}", "if_output": True}]),
                         env={}, dm_fn=lambda t, e: sent.append(t), sh=sh)
        self.assertEqual((rc, sent, ran), (0, [], ["watch"]))

    def test_dm_gets_previous_output(self):
        sent = []
        rc = pbm.execute(self.pb([{"run": "watch"}, {"dm": "Heads up\n{prev}", "if_output": True}]),
                         env={}, dm_fn=lambda t, e: sent.append(t), sh=lambda c, t, stdin=None: ok("  line  \n"))
        self.assertEqual(sent, ["Heads up\nline"])

    def test_failure_stops_and_returns_code(self):
        sent = []
        rc = pbm.execute(self.pb([{"run": "boom"}, {"dm": "never"}]), env={},
                         dm_fn=lambda t, e: sent.append(t), sh=lambda c, t, stdin=None: ok(rc=3, err="bad"))
        self.assertEqual((rc, sent), (3, []))

    def test_queue_pipes_prev_to_stdin(self):
        seen = []
        def sh(cmd, timeout, stdin=None):
            seen.append((cmd, stdin))
            return ok('{"kind": "fyi"}' if cmd == "propose" else "q-1")
        orig = pbm.QUEUE
        pbm.QUEUE = Path(tempfile.mkstemp(suffix=".py")[1])
        try:
            pbm.execute(self.pb([{"run": "propose"}, {"queue": True}]), env={}, sh=sh)
        finally:
            pbm.QUEUE = orig
        self.assertEqual(seen[1][1], '{"kind": "fyi"}')
        self.assertEqual(seen[1][0][-2:], ["create", "--stdin"])

    def test_queue_step_skipped_without_queue_script(self):
        seen = []
        def sh(cmd, timeout, stdin=None):
            seen.append(cmd)
            return ok("out")
        orig = pbm.QUEUE
        pbm.QUEUE = Path(tempfile.mkdtemp()) / "missing.py"
        try:
            self.assertEqual(pbm.execute(self.pb([{"run": "propose"}, {"queue": True}]), env={}, sh=sh), 0)
        finally:
            pbm.QUEUE = orig
        self.assertEqual(seen, ["propose"])

    def test_dry_run_runs_nothing(self):
        def sh(*a, **k):
            raise AssertionError("ran")
        self.assertEqual(pbm.execute(self.pb([{"run": "x"}, {"dm": "y"}]), dry_run=True, env={},
                                     dm_fn=sh, sh=sh), 0)
