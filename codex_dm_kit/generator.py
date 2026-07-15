from __future__ import annotations

import json
import os
import re
import shutil
import stat
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
    value = re.sub(r"[^\w-]+", "-", value.strip().lower(), flags=re.UNICODE).strip("-_")
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
        if result.returncode == 0 and result.stdout.strip().lower() == "true":
            return True

    cursor = path.resolve()
    while True:
        metadata = cursor / ".git"
        if metadata.is_file():
            try:
                if metadata.read_text(encoding="utf-8", errors="replace").lstrip().startswith("gitdir:"):
                    return True
            except OSError:
                return True
        elif metadata.is_dir() and (metadata / "HEAD").is_file():
            return True
        if cursor.parent == cursor:
            return False
        cursor = cursor.parent


def _initialized_campaign(path: Path) -> bool:
    try:
        meta = json.loads((path / "campaign_meta.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return False
    return (
        isinstance(meta, dict)
        and meta.get("initialized") is True
        and meta.get("schema_version") == 1
        and isinstance(meta.get("kit_version"), str)
    )


def inspect_target(target: Path) -> dict[str, Any]:
    target = target.expanduser().resolve()
    inside_git_worktree = _git_worktree(target)
    contains_git_metadata = (target / ".git").exists() or (target / ".git").is_symlink()
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
        "already_initialized": _initialized_campaign(target),
    }


def _load_answers(source: Path | str) -> dict[str, Any]:
    try:
        if str(source) == "-":
            binary_stdin = getattr(sys.stdin, "buffer", None)
            raw_answers = binary_stdin.read().decode("utf-8-sig") if binary_stdin else sys.stdin.read()
            data = json.loads(raw_answers)
        else:
            path = Path(source).expanduser().resolve()
            data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CampaignCreationError(f"answers file does not exist: {source}") from exc
    except json.JSONDecodeError as exc:
        raise CampaignCreationError(f"answers JSON is invalid: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise CampaignCreationError("answers supplied over stdin must be UTF-8") from exc
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
    opening_hook = data["opening_hook"]
    if isinstance(opening_hook, dict):
        if not str(opening_hook.get("summary", "")).strip():
            raise CampaignCreationError("opening_hook.summary is required when opening_hook is an object")
    elif not str(opening_hook).strip():
        raise CampaignCreationError("opening_hook must be a non-empty string or object")
    if "preferences" in data and not isinstance(data["preferences"], dict):
        raise CampaignCreationError("preferences must be an object")
    return data


def _opening_hook_text(opening_hook: Any) -> str:
    if not isinstance(opening_hook, dict):
        return str(opening_hook).strip()
    title = str(opening_hook.get("title", "")).strip()
    summary = str(opening_hook.get("summary", "")).strip()
    return f"{title} — {summary}" if title else summary


def _inline_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value)).strip()


def _list_text(value: Any, fallback: str) -> str:
    if isinstance(value, list):
        rendered = ", ".join(_inline_text(item) for item in value if _inline_text(item))
        return rendered or fallback
    rendered = _inline_text(value) if value is not None else ""
    return rendered or fallback


def _play_mix_text(value: Any, fallback: str) -> str:
    if isinstance(value, dict):
        rendered = ", ".join(f"{_inline_text(key)}: {_inline_text(amount)}" for key, amount in value.items())
        return rendered or fallback
    return _list_text(value, fallback)


def _tokens(answers: dict[str, Any]) -> dict[str, str]:
    player = answers["player"]
    setting = answers["setting"]
    preferences = answers.get("preferences", {})
    language = answers["language"]
    unspecified = "не указано" if language == "ru" else "not specified"
    return {
        "CAMPAIGN_TITLE": _inline_text(answers["campaign_title"]),
        "CAMPAIGN_SLUG": _slug(str(answers.get("campaign_slug") or answers["campaign_title"])),
        "LANGUAGE": language,
        "LANGUAGE_NAME": "русский" if language == "ru" else "English",
        "PLAYER_NAME": _inline_text(player["name"]),
        "SETTING_NAME": _inline_text(setting.get("name", answers["campaign_title"])),
        "SETTING_PREMISE": _inline_text(setting.get("premise", "")),
        "TONE": _inline_text(preferences.get("tone", "adventure with real consequences")),
        "BOUNDARIES": _list_text(preferences.get("boundaries"), unspecified),
        "LETHALITY": _list_text(preferences.get("lethality"), unspecified),
        "PLAY_MIX": _play_mix_text(preferences.get("play_mix"), unspecified),
        "OPENING_HOOK": _inline_text(_opening_hook_text(answers["opening_hook"])),
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
    if not isinstance(stats, dict):
        raise CampaignCreationError("player.stats must be an object")
    try:
        stats = {str(key): int(value) for key, value in stats.items()}
    except (TypeError, ValueError) as exc:
        raise CampaignCreationError("player.stats values must be integers") from exc
    modifiers = source.get("modifiers") or {key: (value - 10) // 2 for key, value in stats.items()}
    if not isinstance(modifiers, dict):
        raise CampaignCreationError("player.modifiers must be an object")
    try:
        modifiers = {str(key): int(value) for key, value in modifiers.items()}
    except (TypeError, ValueError) as exc:
        raise CampaignCreationError("player.modifiers values must be integers") from exc
    level = int(source.get("level", 1))
    if not 1 <= level <= 20:
        raise CampaignCreationError("player.level must be between 1 and 20")
    constitution_modifier = int(modifiers.get("constitution", 0))
    default_hp = max(1, 8 + constitution_modifier) + (level - 1) * max(1, 5 + constitution_modifier)
    hp = source.get("hp") or {"current": default_hp, "max": default_hp, "temp": 0}
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
        "proficiency_bonus": int(source.get("proficiency_bonus", 2 + (level - 1) // 4)),
        "stats": stats,
        "modifiers": modifiers,
        "hp": hp,
        "hit_dice": source.get("hit_dice", {"die": "d8", "current": level, "max": level, "constitution_modifier": constitution_modifier}),
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
    starting_id = _location_id(setting)
    supplied = setting.get("locations")
    if isinstance(supplied, list) and supplied:
        normalized: list[dict[str, Any]] = []
        for index, raw_location in enumerate(supplied):
            if not isinstance(raw_location, dict):
                raise CampaignCreationError(f"setting.locations[{index}] must be an object")
            location = deepcopy(raw_location)
            name = _inline_text(location.get("name") or f"Location {index + 1}")
            location["id"] = _slug(str(location.get("id") or name))
            location["name"] = name
            location.setdefault("description", "")
            location.setdefault("atmosphere", "")
            location.setdefault("inhabitants", [])
            location.setdefault("dangers", [])
            location.setdefault("visible_clues", [])
            location.setdefault("secrets", [])
            location.setdefault("related_npcs", [])
            location.setdefault("related_quests", ["opening_hook"] if location["id"] == starting_id else [])
            location.setdefault("visual_description", "")
            for field in ("inhabitants", "dangers", "visible_clues", "secrets", "related_npcs", "related_quests"):
                if not isinstance(location[field], list):
                    raise CampaignCreationError(f"setting.locations[{index}].{field} must be an array")
            normalized.append(location)
        if starting_id not in {location["id"] for location in normalized}:
            raise CampaignCreationError("setting.starting_location must match an entry in setting.locations")
        return normalized
    if supplied is not None and not isinstance(supplied, list):
        raise CampaignCreationError("setting.locations must be an array")
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


def _npcs(answers: dict[str, Any]) -> list[dict[str, Any]]:
    supplied = answers.get("npcs", [])
    if not isinstance(supplied, list):
        raise CampaignCreationError("npcs must be an array")
    normalized: list[dict[str, Any]] = []
    for index, raw_npc in enumerate(supplied):
        if not isinstance(raw_npc, dict):
            raise CampaignCreationError(f"npcs[{index}] must be an object")
        npc = deepcopy(raw_npc)
        name = _inline_text(npc.get("name") or f"NPC {index + 1}")
        npc["id"] = _slug(str(npc.get("id") or name))
        npc["name"] = name
        npc.setdefault("role", "")
        npc.setdefault("status", "active")
        npc.setdefault("attitude", "neutral")
        npc.setdefault("location", None)
        npc.setdefault("knows", [])
        npc.setdefault("does_not_know", [])
        npc.setdefault("knowledge_sources", [])
        npc.setdefault("goals", [])
        npc.setdefault("related_quests", [])
        for field in ("knows", "does_not_know", "knowledge_sources", "goals", "related_quests"):
            if not isinstance(npc[field], list):
                raise CampaignCreationError(f"npcs[{index}].{field} must be an array")
        normalized.append(npc)
    return normalized


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
            "preferences": deepcopy(answers.get("preferences", {})),
        },
        "player_state.json": _player_state(answers),
        "npcs.json": _npcs(answers),
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


def _is_reparse_point(path: Path) -> bool:
    try:
        metadata = os.lstat(path)
    except FileNotFoundError:
        return False
    attributes = getattr(metadata, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return stat.S_ISLNK(metadata.st_mode) or bool(reparse_flag and attributes & reparse_flag)


def _mkdir_tracked(path: Path, created_dirs: list[Path]) -> None:
    missing: list[Path] = []
    cursor = path
    while not cursor.exists():
        if _is_reparse_point(cursor):
            raise CampaignCreationError(f"refusing to use a reparse point: {cursor}")
        missing.append(cursor)
        if cursor.parent == cursor:
            break
        cursor = cursor.parent
    if cursor.exists() and not cursor.is_dir():
        raise CampaignCreationError(f"expected a directory but found a file: {cursor}")
    for directory in reversed(missing):
        try:
            directory.mkdir()
            created_dirs.append(directory)
        except FileExistsError:
            if not directory.is_dir() or _is_reparse_point(directory):
                raise CampaignCreationError(f"unsafe directory appeared during creation: {directory}")


def _assert_safe_destination(root: Path, relative: str) -> Path:
    relative_path = Path(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise CampaignCreationError(f"unsafe generated path: {relative}")
    destination = root / relative_path
    cursor = root
    for part in relative_path.parts[:-1]:
        cursor /= part
        if _is_reparse_point(cursor):
            raise CampaignCreationError(f"refusing to write through a reparse point: {cursor}")
    try:
        destination.parent.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise CampaignCreationError(f"generated path escapes the campaign root: {relative}") from exc
    if destination.exists() or _is_reparse_point(destination):
        raise CampaignCreationError(f"refusing to overwrite a file created after inspection: {relative}")
    return destination


def create_campaign(answers_path: Path | str, target: Path, *, dry_run: bool = False) -> dict[str, Any]:
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

    created: list[Path] = []
    created_dirs: list[Path] = []
    try:
        _mkdir_tracked(target, created_dirs)
        for relative, content in rendered.items():
            destination = target / relative
            _mkdir_tracked(destination.parent, created_dirs)
            destination = _assert_safe_destination(target, relative)
            with destination.open("x", encoding="utf-8", newline="\n") as handle:
                created.append(destination)
                handle.write(content)

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
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        for directory in reversed(created_dirs):
            try:
                directory.rmdir()
            except OSError:
                pass
        raise

    result["dashboard"] = str(target / "dashboard" / "index.html")
    return result
