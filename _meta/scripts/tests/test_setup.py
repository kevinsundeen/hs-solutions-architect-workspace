import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location("setup_mod", Path(__file__).resolve().parents[1] / "setup.py")
su = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(su)


def tmp() -> Path:
    return Path(tempfile.mkdtemp())


class PrereqTests(unittest.TestCase):
    def test_all_present(self):
        self.assertEqual(su.check_prereqs(which=lambda n: f"/bin/{n}", version=(3, 12)), [])

    def test_missing_tools_and_old_python(self):
        probs = su.check_prereqs(which=lambda n: None if n == "gh" else "/x", version=(3, 9))
        self.assertEqual(len(probs), 2)
        self.assertIn("brew install python@3.12", probs[0])
        self.assertIn("brew install gh", probs[1])


class EnvTests(unittest.TestCase):
    def test_write_env_fills_and_skips(self):
        d = tmp()
        (d / ".env.example").write_text("# c\nA_KEY=\nB_KEY=\n")
        answers = iter(["aaa", ""])
        filled = su.write_env(d / ".env.example", d / ".env", ask=lambda p: next(answers))
        self.assertEqual(filled, ["A_KEY"])
        self.assertEqual((d / ".env").read_text(), "# c\nA_KEY=aaa\nB_KEY=\n")

    def test_write_env_keeps_existing_values(self):
        d = tmp()
        (d / ".env.example").write_text("A_KEY=\nB_KEY=\nC_KEY=\n")
        (d / ".env").write_text("A_KEY=mine\nEXTRA=1\n")
        asked = []
        su.write_env(d / ".env.example", d / ".env", ask=lambda p: asked.append(p) or "")
        self.assertEqual([p.split()[0] for p in asked], ["B_KEY", "C_KEY"])
        text = (d / ".env").read_text()
        self.assertIn("A_KEY=mine", text)
        self.assertIn("EXTRA=1", text)
        self.assertIn("B_KEY=", text)


class OverlayTests(unittest.TestCase):
    def setUp(self):
        self.root, self.ov = tmp(), tmp()
        for rel in ("agents/tw-scribe.md", "skills/tw-time/SKILL.md", "scripts/teamwork.py", "scripts/cmd/timelog.sh"):
            p = self.ov / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("x")

    def test_links_into_core(self):
        su.link_overlay(self.ov, self.root)
        self.assertTrue((self.root / ".claude/agents/tw-scribe.md").is_symlink())
        self.assertTrue((self.root / ".claude/skills/tw-time").is_symlink())
        self.assertTrue((self.root / "_meta/scripts/teamwork.py").is_symlink())
        self.assertTrue((self.root / "_meta/scripts/cmd/timelog.sh").is_symlink())

    def test_link_overlay_keeps_real_files(self):
        real = self.root / "_meta/scripts/teamwork.py"
        real.parent.mkdir(parents=True)
        real.write_text("mine")
        actions = su.link_overlay(self.ov, self.root)
        self.assertEqual(real.read_text(), "mine")
        self.assertFalse(real.is_symlink())
        self.assertTrue(any(a.startswith("kept") and "teamwork.py" in a for a in actions))

    def test_rerun_is_idempotent(self):
        su.link_overlay(self.ov, self.root)
        self.assertTrue(all(a.startswith("linked") for a in su.link_overlay(self.ov, self.root)))

    def test_links_are_added_to_git_exclude_once(self):
        (self.root / ".git").mkdir()
        su.link_overlay(self.ov, self.root)
        su.link_overlay(self.ov, self.root)
        exclude = (self.root / ".git/info/exclude").read_text().splitlines()
        self.assertEqual(exclude.count(".claude/agents/tw-scribe.md"), 1)
        self.assertEqual(exclude.count("_meta/scripts/teamwork.py"), 1)


class McpTests(unittest.TestCase):
    def test_render_once(self):
        d = tmp()
        (d / "ex.json").write_text('{"h": "{{HOME}}"}')
        self.assertTrue(su.render_mcp(d / "ex.json", d / ".mcp.json", "/Users/s"))
        self.assertEqual((d / ".mcp.json").read_text(), '{"h": "/Users/s"}')
        self.assertFalse(su.render_mcp(d / "ex.json", d / ".mcp.json", "/other"))
        self.assertEqual((d / ".mcp.json").read_text(), '{"h": "/Users/s"}')


class SmokeTests(unittest.TestCase):
    def test_pass_when_index_mentions_transcript(self):
        root = tmp()
        (root / "examples").mkdir()
        (root / "examples/sample-transcript.txt").write_text("t")

        def run(cmd, **kw):
            if "new" in cmd:
                (root / "Demo/transcripts").mkdir(parents=True, exist_ok=True)
            if "context" in cmd:
                (root / "Demo/transcripts/transcript-index.md").write_text(su.SAMPLE_NAME)
            class R: returncode = 0; stdout = ""; stderr = ""
            return R()
        self.assertTrue(su.smoke_test(root, run=run))
        self.assertFalse((root / "Demo").exists())  # cleaned up

    def test_fail_when_index_missing(self):
        root = tmp()
        (root / "examples").mkdir()
        (root / "examples/sample-transcript.txt").write_text("t")

        def run(cmd, **kw):
            (root / "Demo/transcripts").mkdir(parents=True, exist_ok=True)
            class R: returncode = 0; stdout = ""; stderr = ""
            return R()
        self.assertFalse(su.smoke_test(root, run=run))

    def test_refuses_existing_demo(self):
        root = tmp()
        (root / "Demo").mkdir()
        self.assertFalse(su.smoke_test(root, run=lambda *a, **k: None))
        self.assertTrue((root / "Demo").exists())


if __name__ == "__main__":
    unittest.main()
