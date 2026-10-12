import os
import subprocess
import tempfile
import unittest
from pathlib import Path

S2 = Path(__file__).resolve().parents[1] / "s2"


class DispatcherTests(unittest.TestCase):
    def run_s2(self, *args):
        return subprocess.run(["bash", str(S2), *args], capture_output=True, text=True)

    def test_help_lists_core_commands(self):
        out = self.run_s2("help").stdout
        for cmd in ("setup", "new client", "sync", "context", "find", "playbook"):
            self.assertIn(cmd, out)

    def test_unknown_command_falls_through_to_cmd_dir(self):
        cmd_dir = S2.parent / "cmd"
        cmd_dir.mkdir(exist_ok=True)
        probe = cmd_dir / "zz-probe.sh"
        probe.write_text('#!/usr/bin/env bash\necho "probe $*"\n')
        probe.chmod(0o755)
        try:
            r = self.run_s2("zz-probe", "a", "b")
            self.assertEqual(r.stdout.strip(), "probe a b")
        finally:
            probe.unlink()
            try:
                cmd_dir.rmdir()
            except OSError:
                pass

    def test_unknown_command_without_cmd_exits_1(self):
        r = self.run_s2("no-such-thing")
        self.assertEqual(r.returncode, 1)
        self.assertIn("Unknown command", r.stderr)


class TempRootTests(unittest.TestCase):
    """Run a copy of s2 inside a throwaway repo layout so no client folder lands in the real repo."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        scripts = self.root / "_meta" / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "s2").write_text(S2.read_text())
        (scripts / "s2").chmod(0o755)
        (scripts / "pyresolve.sh").write_text((S2.parent / "pyresolve.sh").read_text())

    def tearDown(self):
        self.tmp.cleanup()

    def run_s2(self, *args):
        return subprocess.run(["bash", str(self.root / "_meta" / "scripts" / "s2"), *args],
                              capture_output=True, text=True)

    def test_new_client_with_space_uses_template(self):
        tdir = self.root / "_meta" / "system" / "templates"
        tdir.mkdir(parents=True)
        (tdir / "client-context-template.md").write_text("# [Client Name] - Context\n")
        r = self.run_s2("new", "client", "Acme Widgets")
        self.assertEqual(r.returncode, 0, r.stderr)
        text = (self.root / "Acme Widgets" / "context.md").read_text()
        self.assertIn("Acme Widgets", text)

    def test_new_client_without_template_writes_stub(self):
        r = self.run_s2("new", "client", "A&B")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("# A&B - Context", (self.root / "A&B" / "context.md").read_text())

    def test_new_client_rejects_slash_and_dot(self):
        self.assertEqual(self.run_s2("new", "client", "a/b").returncode, 1)
        self.assertEqual(self.run_s2("new", "client", ".hidden").returncode, 1)

    def test_status_lists_spaced_client_on_one_line(self):
        self.run_s2("new", "client", "Acme Widgets")
        lines = [l for l in self.run_s2("status").stdout.splitlines() if "Acme Widgets" in l]
        self.assertEqual(len(lines), 1)

    def test_subcommand_with_slash_rejected(self):
        r = self.run_s2("../x")
        self.assertEqual(r.returncode, 1)


class PythonResolveTests(unittest.TestCase):
    RESOLVE = S2.parent / "pyresolve.sh"

    def resolve(self, env_extra, path=None):
        env = {k: v for k, v in os.environ.items() if k != "S2_PYTHON"}
        env.update(env_extra)
        if path is not None:
            env["PATH"] = path
        return subprocess.run(["/bin/bash", "-c", f'source "{self.RESOLVE}"; s2_python'],
                              capture_output=True, text=True, env=env)

    def fake_python(self, d, name, minor):
        p = Path(d) / name
        p.write_text(f'#!/bin/sh\n[ "$1" = "-c" ] && exit $(( {minor} >= 11 ? 0 : 1 ))\nexit 0\n')
        p.chmod(0o755)
        return p

    def test_override_wins(self):
        r = self.resolve({"S2_PYTHON": "/x/py"})
        self.assertEqual(r.stdout.strip(), "/x/py")

    def test_skips_old_python_and_picks_first_qualifying(self):
        with tempfile.TemporaryDirectory() as d:
            self.fake_python(d, "python3.12", 12)
            self.fake_python(d, "python3", 9)
            r = self.resolve({}, path=f"{d}:/usr/bin:/bin")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(r.stdout.strip().endswith("/python3.12"))

    def test_fails_with_hint_when_none_qualifies(self):
        with tempfile.TemporaryDirectory() as d:
            self.fake_python(d, "python3", 9)
            r = self.resolve({}, path=d)
            if Path("/opt/homebrew/bin/python3").exists() or Path("/usr/local/bin/python3").exists():
                self.skipTest("a fixed-path python exists on this machine")
            self.assertEqual(r.returncode, 1)
            self.assertIn("Python 3.11+ required → brew install python@3.12", r.stderr)
