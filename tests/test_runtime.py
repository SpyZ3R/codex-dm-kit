from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from codex_dm_kit.generator import create_campaign


REPO_ROOT = Path(__file__).resolve().parents[1]
ANSWERS = REPO_ROOT / "examples" / "onboarding_answers.ru.json"


class RuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="codex-dm-runtime-")
        self.root = Path(self.temp.name) / "campaign"
        create_campaign(ANSWERS, self.root)
        runtime_path = self.root / "tools" / "codex_dm.py"
        spec = importlib.util.spec_from_file_location("generated_codex_dm", runtime_path)
        assert spec and spec.loader
        self.runtime = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.runtime)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_roll_expression(self) -> None:
        result = self.runtime.roll("2d6+3")
        self.assertEqual(len(result["rolls"]), 2)
        self.assertEqual(result["total"], sum(result["rolls"]) + 3)
        with self.assertRaises(ValueError):
            self.runtime.roll("drop table")

    def test_validator_rejects_duplicate_quest_and_broken_reference(self) -> None:
        quests_path = self.root / "quests.json"
        quests = json.loads(quests_path.read_text(encoding="utf-8"))
        duplicate = dict(quests["active"][0])
        duplicate["status"] = "completed"
        quests["completed"].append(duplicate)
        quests_path.write_text(json.dumps(quests, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        result = self.runtime.validate_campaign(self.root, check_dashboard=False)
        self.assertFalse(result["ok"])
        self.assertTrue(any("unique" in error for error in result["errors"]))

    def test_first_game_action_syncs_state_log_and_dashboard(self) -> None:
        player_path = self.root / "player_state.json"
        player = json.loads(player_path.read_text(encoding="utf-8"))
        player["gold"] += 1
        player_path.write_text(json.dumps(player, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        log_path = self.root / "session_log.md"
        log_marker = "First action: the character received one gold piece."
        log_path.write_text(log_path.read_text(encoding="utf-8") + f"\n- {log_marker}\n", encoding="utf-8")

        stale = self.runtime.validate_campaign(self.root, check_dashboard=True)
        self.assertFalse(stale["ok"])
        self.assertTrue(any("stale" in error for error in stale["errors"]))
        self.runtime.write_dashboard_data(self.root)
        fresh = self.runtime.validate_campaign(self.root, check_dashboard=True)
        self.assertTrue(fresh["ok"], fresh["errors"])
        dashboard = self.runtime.parse_dashboard_data(self.root / "dashboard" / "dashboard_data.js")
        self.assertEqual(dashboard["player"]["gold"], player["gold"])
        self.assertIn(log_marker, log_path.read_text(encoding="utf-8"))

    def test_dashboard_allowlist_excludes_secrets_and_hidden_quests(self) -> None:
        marker = "TOP-SECRET-MOON-KEY"
        (self.root / "secrets.md").write_text(marker, encoding="utf-8")
        quests_path = self.root / "quests.json"
        quests = json.loads(quests_path.read_text(encoding="utf-8"))
        quests["hidden"].append({
            "id": "hidden_marker",
            "title": marker,
            "goal": marker,
            "current_progress": marker,
            "known_facts": [],
            "hidden_facts": [marker],
            "possible_consequences": [],
            "status": "hidden",
        })
        quests_path.write_text(json.dumps(quests, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.runtime.write_dashboard_data(self.root)
        dashboard = (self.root / "dashboard" / "dashboard_data.js").read_text(encoding="utf-8")
        self.assertNotIn(marker, dashboard)

    def test_dashboard_is_file_url_compatible_and_renders_imports_as_text(self) -> None:
        html = (self.root / "dashboard" / "index.html").read_text(encoding="utf-8")
        data = (self.root / "dashboard" / "dashboard_data.js").read_text(encoding="utf-8")

        self.assertIn('<script src="./dashboard_data.js"></script>', html)
        self.assertNotIn("fetch(", html)
        self.assertNotIn("innerHTML", html)
        self.assertTrue(data.startswith("window.CODEX_DM_DATA = "))

    def test_validator_requires_the_stable_dashboard_shell(self) -> None:
        (self.root / "dashboard" / "index.html").unlink()

        result = self.runtime.validate_campaign(self.root, check_dashboard=True)

        self.assertFalse(result["ok"])
        self.assertIn("missing required file: dashboard/index.html", result["errors"])

    def test_cli_reports_invalid_resource(self) -> None:
        player_path = self.root / "player_state.json"
        player = json.loads(player_path.read_text(encoding="utf-8"))
        player["hp"]["current"] = player["hp"]["max"] + 1
        player_path.write_text(json.dumps(player, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        command = subprocess.run(
            [sys.executable, str(self.root / "tools" / "codex_dm.py"), "finalize", "--root", str(self.root)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(command.returncode, 1)
        self.assertIn("0 <= current <= max", command.stdout)


if __name__ == "__main__":
    unittest.main()
