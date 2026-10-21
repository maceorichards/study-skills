"""Tests for install.py. Run: python -m unittest discover -s tests"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("install", REPO / "install.py")
install = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(install)


def can_symlink(tmp: Path) -> bool:
    try:
        os.symlink(tmp, tmp / "probe", target_is_directory=True)
        os.unlink(tmp / "probe")
        return True
    except (OSError, NotImplementedError):
        return False


class Installer(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.course = self.tmp / "BIO101"
        (self.course / "study").mkdir(parents=True)
        (self.course / "study" / "progress.json").write_text("{}", encoding="utf-8")
        self._registry = install.REGISTRY
        install.REGISTRY = self.tmp / "installed.json"

    def tearDown(self):
        install.REGISTRY = self._registry
        shutil.rmtree(self.tmp)

    def run_main(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = install.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_no_course_dir_is_an_error(self):
        code, _, err = self.run_main()
        self.assertEqual(code, 2)
        self.assertIn("specify at least one course directory", err)

    def test_dirs_for_picks_fewest_folders(self):
        self.assertEqual(install.dirs_for(["claude", "cursor"]), [".claude/skills"])
        self.assertEqual(install.dirs_for(["codex", "cursor"]), [".agents/skills"])
        self.assertEqual(install.dirs_for(["claude", "codex"]), [".claude/skills", ".agents/skills"])
        with self.assertRaises(install.InstallError):
            install.parse_tools("claude,vim")

    def test_copy_install_update_uninstall(self):
        code, out, err = self.run_main(str(self.course), "--tools", "claude,codex")
        self.assertEqual(code, 0, err)
        for d in (".claude/skills", ".agents/skills"):
            for n in install.skill_names():
                dest = self.course / d / n
                self.assertTrue((dest / "SKILL.md").is_file())
                self.assertTrue((dest / "scripts" / "study.py").is_file())
                self.assertTrue((dest / install.MARKER).is_file())
        reg = json.loads(install.REGISTRY.read_text(encoding="utf-8"))
        self.assertEqual(reg["courses"][str(self.course.resolve())]["tools"], ["claude", "codex"])
        # update re-installs with the recorded tools
        code, out, _ = self.run_main("--update")
        self.assertEqual(code, 0)
        self.assertIn(str(self.course.resolve()), out)
        # switching tools removes the folder no longer needed
        self.run_main(str(self.course), "--tools", "claude")
        self.assertFalse((self.course / ".agents").exists())
        code, out, _ = self.run_main("--list")
        self.assertIn("tools: claude", out)
        self.run_main("--uninstall", str(self.course))
        self.assertFalse((self.course / ".claude").exists())
        self.assertTrue((self.course / "study" / "progress.json").is_file())  # data untouched

    def test_refuses_foreign_skill_folder_without_force(self):
        foreign = self.course / ".claude" / "skills" / "quiz-me"
        foreign.mkdir(parents=True)
        (foreign / "SKILL.md").write_text("mine", encoding="utf-8")
        (self.course / ".claude" / "skills" / "other-skill").mkdir()
        code, _, err = self.run_main(str(self.course), "--tools", "claude")
        self.assertEqual(code, 1)
        self.assertIn("--force", err)
        self.assertEqual((foreign / "SKILL.md").read_text(encoding="utf-8"), "mine")
        self.assertFalse((self.course / ".claude" / "skills" / "teach-me").exists())  # nothing half-done
        code, _, _ = self.run_main(str(self.course), "--tools", "claude", "--force")
        self.assertEqual(code, 0)
        self.assertNotEqual((foreign / "SKILL.md").read_text(encoding="utf-8"), "mine")
        self.run_main("--uninstall", str(self.course))
        self.assertTrue((self.course / ".claude" / "skills" / "other-skill").is_dir())  # not ours: kept

    def test_link_mode(self):
        if not can_symlink(self.tmp) and os.name != "nt":
            self.skipTest("symlinks not available")
        code, _, err = self.run_main(str(self.course), "--tools", "claude", "--link")
        self.assertEqual(code, 0, err)
        dest = self.course / ".claude" / "skills" / "quiz-me"
        self.assertTrue((dest / "SKILL.md").is_file())
        self.assertTrue(install.owned(dest))
        self.assertFalse((install.SKILLS / "quiz-me" / install.MARKER).exists())  # never writes into the repo
        self.run_main("--uninstall", str(self.course))
        self.assertFalse(dest.exists() or dest.is_symlink())
        self.assertTrue((install.SKILLS / "quiz-me" / "SKILL.md").is_file())

    def test_refuses_repo_and_missing_folder(self):
        self.assertEqual(self.run_main(str(REPO), "--tools", "claude")[0], 1)
        self.assertEqual(self.run_main(str(self.tmp / "nope"), "--tools", "claude")[0], 1)


if __name__ == "__main__":
    unittest.main()
