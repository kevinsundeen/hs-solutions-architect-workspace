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
