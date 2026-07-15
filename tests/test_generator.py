from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from codex_dm_kit.generator import CampaignCreationError, create_campaign, inspect_target


REPO_ROOT = Path(__file__).resolve().parents[1]
ANSWERS = REPO_ROOT / "examples" / "onboarding_answers.ru.json"


class GeneratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="codex-dm-kit-test-")
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_creates_campaign_in_selected_folder_and_preserves_user_file(self) -> None:
        target = self.root / "chosen-project"
        target.mkdir()
        note = target / "my-character-notes.txt"
        note.write_text("keep me", encoding="utf-8")

        result = create_campaign(ANSWERS, target)

        self.assertTrue(result["ok"])
        self.assertEqual(note.read_text(encoding="utf-8"), "keep me")
        self.assertFalse((target / ".git").exists())
        self.assertTrue((target / "campaign_meta.json").is_file())
        self.assertTrue((target / "dashboard" / "index.html").is_file())
        validate = subprocess.run(
            [sys.executable, str(target / "tools" / "codex_dm.py"), "validate", "--root", str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(validate.returncode, 0, validate.stdout + validate.stderr)

    def test_refuses_collision_without_overwrite(self) -> None:
        target = self.root / "chosen-project"
        target.mkdir()
        agents = target / "AGENTS.md"
        agents.write_text("user-owned", encoding="utf-8")

        with self.assertRaises(CampaignCreationError):
            create_campaign(ANSWERS, target)

        self.assertEqual(agents.read_text(encoding="utf-8"), "user-owned")
        self.assertFalse((target / "campaign_meta.json").exists())

    def test_refuses_second_initialization(self) -> None:
        target = self.root / "chosen-project"
        create_campaign(ANSWERS, target)
        with self.assertRaises(CampaignCreationError):
            create_campaign(ANSWERS, target)

    @unittest.skipUnless(shutil.which("git"), "Git is required for worktree safety test")
    def test_refuses_target_inside_git_worktree(self) -> None:
        worktree = self.root / "repo"
        worktree.mkdir()
        subprocess.run(["git", "init", "-q", str(worktree)], check=True)
        target = worktree / "campaign"

        inspection = inspect_target(target)
        self.assertTrue(inspection["inside_git_worktree"])
        with self.assertRaises(CampaignCreationError):
            create_campaign(ANSWERS, target)

    def test_refuses_own_git_metadata_even_when_it_is_not_a_valid_repository(self) -> None:
        target = self.root / "chosen-project"
        (target / ".git").mkdir(parents=True)

        inspection = inspect_target(target)
        self.assertTrue(inspection["contains_git_metadata"])
        self.assertFalse(inspection["ok"])
        with self.assertRaises(CampaignCreationError):
            create_campaign(ANSWERS, target)

    def test_ignores_invalid_git_metadata_in_an_ancestor(self) -> None:
        (self.root / ".git").mkdir()
        target = self.root / "chosen-project"

        inspection = inspect_target(target)
        self.assertFalse(inspection["inside_git_worktree"])
        self.assertFalse(inspection["contains_git_metadata"])
        self.assertTrue(inspection["ok"])

    def test_dry_run_does_not_create_target(self) -> None:
        target = self.root / "chosen-project"
        result = create_campaign(ANSWERS, target, dry_run=True)
        self.assertTrue(result["dry_run"])
        self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
