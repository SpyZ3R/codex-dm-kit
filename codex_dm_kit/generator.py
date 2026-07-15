from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__


class CampaignCreationError(RuntimeError):
    """Raised when campaign creation would be unsafe or incomplete."""


TEMPLATE_ROOT = Path(__file__).resolve().parent / "templates" / "campaign"
STATIC_TEMPLATE_FILES = {
    "AGENTS.md.tmpl": "AGENTS.md",
    "main_prompt.md.tmpl": "main_prompt.md",
    "new_chat_prompt.md.tmpl": "new_chat_prompt.md",
    "rules_notes.md.tmpl": "rules_notes.md",
    "campaign_summary.md.tmpl": "campaign_summary.md",
    "session_log.md.tmpl": "session_log.md",
    "secrets.md.tmpl": "secrets.md",
    "image_prompts.md.tmpl": "image_prompts.md",
    "tools/codex_dm.py": "tools/codex_dm.py",
    "dashboard/index.html": "dashboard/index.html",
}
GENERATED_FILES = {
    "campaign_meta.json",
    "player_state.json",
    "npcs.json",
    "quests.json",
    "world_state.json",
    "locations.json",
    "battle_state.json",
    "dashboard/dashboard_data.js",
    *STATIC_TEMPLATE_FILES.values(),
}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip().lower()).strip("-")
    return value or "campaign"


def _git_worktree(path: Path) -> bool:
    git = shutil.which("git")
    probe = path if path.exists() else path.parent
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    if git:
        result = subprocess.run(
            [git, "-C", str(probe), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0 and result.stdout.strip().lower() == "true"

    cursor = path.resolve()
    while True:
        if (cursor / ".git").exists():
            return True
        if cursor.parent == cursor:
            return False
        cursor = cursor.parent


def inspect_target(target: Path) -> dict[str, Any]:
    target = target.expanduser().resolve()
    inside_git_worktree = _git_worktree(target)
    contains_git_metadata = (target / ".git").exists()
    existing = sorted(
        str(item.relative_to(target))
        for item in target.rglob("*")
        if target.exists()
        and item.is_file()
        and ".git" not in item.relative_to(target).parts
    ) if target.exists() else []
    collisions = sorted(name for name in GENERATED_FILES if (target / name).exists())
    return {
        "ok": not inside_git_worktree and not contains_git_metadata and not collisions,
        "target": str(target),
        "inside_git_worktree": inside_git_worktree,
        "contains_git_metadata": contains_git_metadata,
        "existing_files": existing,
        "collisions": collisions,
        "already_initialized": (target / "campaign_meta.json").exists(),
    }


def _load_answers(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CampaignCreationError(f"answers file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CampaignCreationError(f"answers JSON is invalid: {exc}") from exc
    if not isinstance(data, dict):
        raise CampaignCreationError("answers must be a JSON object")
    for key in ("campaign_title", "language", "player", "setting", "opening_hook"):
        if key not in data:
            raise CampaignCreationError(f"answers are missing required field: {key}")
    if data["language"] not in {"ru", "en"}:
        raise CampaignCreationError("language must be 'ru' or 'en'")
    if not isinstance(data["player"], dict) or not data["player"].get("name"):
        raise CampaignCreationError("player.name is required")
    if not isinstance(data["setting"], dict) or not data["setting"].get("starting_location"):
        raise CampaignCreationError("setting.starting_location is required")
    return data


def _tokens(answers: dict[str, Any]) -> dict[str, str]:
    player = answers["player"]
    setting = answers["setting"]
    preferences = answers.get("preferences", {})
    language = answers["language"]
    return {
        "CAMPAIGN_TITLE": str(answers["campaign_title"]),
        "CAMPAIGN_SLUG": _slug(str(answers.get("campaign_slug") or answers["campaign_title"])),
        "LANGUAGE": language,
        "LANGUAGE_NAME": "русский" if language == "ru" else "English",
        "PLAYER_NAME": str(player["name"]),
        "SETTING_NAME": str(setting.get("name", answers["campaign_title"])),
        "SETTING_PREMISE": str(setting.get("premise", "")),
        "TONE": str(preferences.get("tone", "adventure with real consequences")),
        "BOUNDARIES": ", ".join(map(str, preferences.get("boundaries", []))) or "not specified",
        "OPENING_HOOK": str(answers["opening_hook"]),
        "CREATED_AT": _now(),
        "KIT_VERSION": __version__,
    }


def _render(text: str, tokens: dict[str, str]) -> str:
    for key, value in tokens.items():
        text = text.replace("{{" + key + "}}", value)
    unresolved = sorted(set(re.findall(r"\{\{([A-Z0-9_]+)\}\}", text)))
    if unresolved:
        raise CampaignCreationError(f"unresolved template tokens: {', '.join(unresolved)}")
    return text


def _player_state(answers: dict[str, Any]) -> dict[str, Any]:
    source = deepcopy(answers["player"])
    stats = source.get("stats") or {
        "strength": 10,
        "dexterity": 10,
        "constitution": 10,
        "intelligence": 10,
        "wisdom": 10,
        "charisma": 10,
    }
    modifiers = source.get("modifiers") or {key: (int(value) - 10) // 2 for key, value in stats.items()}
    level = int(source.get("level", 1))
    hp = source.get("hp") or {"current": 8, "max": 8, "temp": 0}
    return {
        "name": source["name"],
        "pronouns": source.get("pronouns", "not specified"),
        "race": source.get("race", "not specified"),
        "class": source.get("class", "adventurer"),
        "level": level,
        "background": source.get("background", "not specified"),
        "backstory": source.get("backstory", {}),
        "alignment": source.get("alignment", "not specified"),
        "rest_state": source.get("rest_state", "ready to begin"),
        "advancement": source.get("advancement", {"method": "milestone", "xp_tracking": False}),
        "proficiency_bonus": int(source.get("proficiency_bonus", 2)),
        "stats": stats,
        "modifiers": modifiers,
        "hp": hp,
        "hit_dice": source.get("hit_dice", {"die": "d8", "current": level, "max": level, "constitution_modifier": modifiers.get("constitution", 0)}),
        "ac": int(source.get("ac", 10 + modifiers.get("dexterity", 0))),
        "speed": int(source.get("speed", 30)),
        "saving_throws": source.get("saving_throws", {}),
        "skills": source.get("skills", {}),
        "features": source.get("features", []),
        "spells": source.get("spells", {"slots": {}, "cantrips": [], "known_spells": []}),
        "equipment": source.get("equipment", []),
        "gold": int(source.get("gold", 0)),
        "conditions": source.get("conditions", []),
        "active_effects": source.get("active_effects", []),
        "inspiration": int(source.get("inspiration", 0)),
        "known_clues": source.get("known_clues", []),
        "reputation": source.get("reputation", {}),
    }


def _location_id(setting: dict[str, Any]) -> str:
    location = setting["starting_location"]
    if isinstance(location, dict):
        return _slug(str(location.get("id") or location.get("name") or "starting-location"))
    return _slug(str(location))


def _locations(answers: dict[str, Any]) -> list[dict[str, Any]]:
    setting = answers["setting"]
    supplied = setting.get("locations")
    if isinstance(supplied, list) and supplied:
        return supplied
    raw = setting["starting_location"]
    if isinstance(raw, dict):
        name = str(raw.get("name") or "Starting location")
        description = str(raw.get("description") or setting.get("premise", ""))
        atmosphere = str(raw.get("atmosphere") or "The first scene is ready to begin.")
    else:
        name = str(raw)
        description = str(setting.get("premise", ""))
        atmosphere = "The first scene is ready to begin."
    return [{
        "id": _location_id(setting),
        "name": name,
        "description": description,
        "atmosphere": atmosphere,
        "inhabitants": [],
        "dangers": [],
        "visible_clues": [],
        "secrets": [],
        "related_npcs": [],
        "related_quests": ["opening_hook"],
        "visual_description": "",
    }]


def _state_files(answers: dict[str, Any], tokens: dict[str, str]) -> dict[str, str]:
    setting = answers["setting"]
    opening = answers["opening_hook"]
    opening_text = opening.get("summary") if isinstance(opening, dict) else str(opening)
    opening_title = opening.get("title", "Opening hook") if isinstance(opening, dict) else "Opening hook"
    locations = _locations(answers)
    current_location = _location_id(setting)
    files: dict[str, Any] = {
        "campaign_meta.json": {
            "schema_version": 1,
            "initialized": True,
            "kit_version": __version__,
            "campaign_id": tokens["CAMPAIGN_SLUG"],
            "title": answers["campaign_title"],
            "language": answers["language"],
            "ruleset": "dnd_5e_light",
            "created_at": tokens["CREATED_AT"],
        },
        "player_state.json": _player_state(answers),
        "npcs.json": answers.get("npcs", []),
        "quests.json": {
            "active": [{
                "id": "opening_hook",
                "title": opening_title,
                "goal": opening_text,
                "current_progress": "The campaign has not started yet." if answers["language"] == "en" else "Кампания еще не началась.",
                "known_facts": [],
                "hidden_facts": [],
                "possible_consequences": [],
                "status": "active",
            }],
            "completed": [],
            "failed": [],
            "hidden": [],
        },
        "world_state.json": {
            "date": setting.get("date", "Campaign day 1" if answers["language"] == "en" else "1-й день кампании"),
            "time_of_day": setting.get("time_of_day", "morning" if answers["language"] == "en" else "утро"),
            "weather": setting.get("weather", "clear" if answers["language"] == "en" else "ясно"),
            "current_location": current_location,
            "factions": setting.get("factions", []),
            "player_reputation": {},
            "global_events": [],
            "timers": [],
            "past_consequences": [],
        },
        "locations.json": locations,
        "battle_state.json": {
            "active": False,
            "location": current_location,
            "round": 0,
            "current_turn": None,
            "initiative": [],
            "combatants": {},
            "environment": [],
            "last_action": None,
            "resources_spent": [],
        },
        "dashboard/dashboard_data.js": "window.CODEX_DM_DATA = null;\n",
    }
    return {
        path: (json.dumps(value, ensure_ascii=False, indent=2) + "\n") if not isinstance(value, str) else value
        for path, value in files.items()
    }


def create_campaign(answers_path: Path, target: Path, *, dry_run: bool = False) -> dict[str, Any]:
    answers_path = answers_path.expanduser().resolve()
    target = target.expanduser().resolve()
    answers = _load_answers(answers_path)
    inspection = inspect_target(target)
    if inspection["inside_git_worktree"]:
        raise CampaignCreationError(f"target is inside a Git worktree: {target}")
    if inspection["contains_git_metadata"]:
        raise CampaignCreationError(f"target contains .git metadata: {target}")
    if inspection["already_initialized"]:
        raise CampaignCreationError(f"campaign is already initialized: {target}")
    if inspection["collisions"]:
        raise CampaignCreationError("refusing to overwrite existing files: " + ", ".join(inspection["collisions"]))
    if not TEMPLATE_ROOT.is_dir():
        raise CampaignCreationError(f"template directory is missing: {TEMPLATE_ROOT}")

    tokens = _tokens(answers)
    rendered: dict[str, str] = {}
    for source_name, destination in STATIC_TEMPLATE_FILES.items():
        source = TEMPLATE_ROOT / source_name
        if not source.is_file():
            raise CampaignCreationError(f"template file is missing: {source}")
        text = source.read_text(encoding="utf-8")
        rendered[destination] = _render(text, tokens) if source.suffix == ".tmpl" else text
    rendered.update(_state_files(answers, tokens))

    result = {
        "ok": True,
        "target": str(target),
        "dry_run": dry_run,
        "preserved_existing_files": inspection["existing_files"],
        "created_files": sorted(rendered),
    }
    if dry_run:
        return result

    target.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    try:
        for relative, content in rendered.items():
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8", newline="\n")
            created.append(destination)

        runtime = target / "tools" / "codex_dm.py"
        validation = subprocess.run(
            [sys.executable, str(runtime), "finalize", "--root", str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        if validation.returncode != 0:
            raise CampaignCreationError(
                "generated campaign failed validation: " + (validation.stdout or validation.stderr).strip()
            )
    except Exception:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        for directory in (target / "dashboard", target / "tools"):
            try:
                directory.rmdir()
            except OSError:
                pass
        try:
            target.rmdir()
        except OSError:
            pass
        raise

    result["dashboard"] = str(target / "dashboard" / "index.html")
    return result
