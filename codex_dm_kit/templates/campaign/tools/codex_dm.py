#!/usr/bin/env python3
"""Dependency-free runtime utilities for a generated codex-dm-kit campaign."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
STATE_FILES = (
    "campaign_meta.json",
    "player_state.json",
    "npcs.json",
    "quests.json",
    "world_state.json",
    "locations.json",
    "battle_state.json",
)
REQUIRED_TEXT_FILES = (
    "AGENTS.md",
    "main_prompt.md",
    "new_chat_prompt.md",
    "campaign_summary.md",
    "session_log.md",
    "rules_notes.md",
    "secrets.md",
    "image_prompts.md",
    "dashboard/index.html",
)
DASHBOARD_PREFIX = "window.CODEX_DM_DATA = "


def load_json(path: Path, errors: list[str]) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors.append(f"missing required file: {path.name}")
    except json.JSONDecodeError as exc:
        errors.append(f"invalid JSON in {path.name}: {exc}")
    return None


def require_mapping(value: Any, name: str, errors: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append(f"{name} must be an object")
        return {}
    return value


def require_list(value: Any, name: str, errors: list[str]) -> list[Any]:
    if not isinstance(value, list):
        errors.append(f"{name} must be an array")
        return []
    return value


def validate_resource(resource: Any, name: str, errors: list[str]) -> None:
    data = require_mapping(resource, name, errors)
    current = data.get("current")
    maximum = data.get("max")
    if not isinstance(current, int) or not isinstance(maximum, int):
        errors.append(f"{name}.current and {name}.max must be integers")
    elif current < 0 or maximum < 0 or current > maximum:
        errors.append(f"{name} must satisfy 0 <= current <= max")


def all_quests(quests: dict[str, Any], errors: list[str]) -> tuple[list[dict[str, Any]], set[str]]:
    combined: list[dict[str, Any]] = []
    ids: list[str] = []
    expected_status = {
        "active": "active",
        "completed": "completed",
        "failed": "failed",
        "hidden": "hidden",
    }
    for bucket, status in expected_status.items():
        entries = require_list(quests.get(bucket), f"quests.{bucket}", errors)
        for index, raw in enumerate(entries):
            quest = require_mapping(raw, f"quests.{bucket}[{index}]", errors)
            quest_id = quest.get("id")
            if not isinstance(quest_id, str) or not quest_id:
                errors.append(f"quests.{bucket}[{index}].id must be a non-empty string")
            else:
                ids.append(quest_id)
            if quest.get("status") != status:
                errors.append(f"quest {quest_id or index} in {bucket} must have status '{status}'")
            combined.append(quest)
    duplicates = sorted({item for item in ids if ids.count(item) > 1})
    if duplicates:
        errors.append("quest IDs must be unique across all buckets: " + ", ".join(duplicates))
    return combined, set(ids)


def validate_campaign(root: Path, *, check_dashboard: bool = True) -> dict[str, Any]:
    root = root.resolve()
    errors: list[str] = []
    warnings: list[str] = []
    for name in REQUIRED_TEXT_FILES:
        if not (root / name).is_file():
            errors.append(f"missing required file: {name}")

    loaded = {name: load_json(root / name, errors) for name in STATE_FILES}
    meta = require_mapping(loaded["campaign_meta.json"], "campaign_meta.json", errors)
    player = require_mapping(loaded["player_state.json"], "player_state.json", errors)
    npcs = require_list(loaded["npcs.json"], "npcs.json", errors)
    quests = require_mapping(loaded["quests.json"], "quests.json", errors)
    world = require_mapping(loaded["world_state.json"], "world_state.json", errors)
    locations = require_list(loaded["locations.json"], "locations.json", errors)
    battle = require_mapping(loaded["battle_state.json"], "battle_state.json", errors)

    if meta.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"campaign_meta.schema_version must be {SCHEMA_VERSION}")
    if meta.get("initialized") is not True:
        errors.append("campaign_meta.initialized must be true")
    for key in ("campaign_id", "title", "language", "ruleset"):
        if not isinstance(meta.get(key), str) or not meta.get(key):
            errors.append(f"campaign_meta.{key} must be a non-empty string")

    for key in ("name", "race", "class"):
        if not isinstance(player.get(key), str) or not player.get(key):
            errors.append(f"player_state.{key} must be a non-empty string")
    if not isinstance(player.get("level"), int) or player.get("level", 0) < 1:
        errors.append("player_state.level must be a positive integer")
    validate_resource(player.get("hp"), "player_state.hp", errors)
    validate_resource(player.get("hit_dice"), "player_state.hit_dice", errors)
    if not isinstance(player.get("gold"), int) or player.get("gold", -1) < 0:
        errors.append("player_state.gold must be a non-negative integer")
    spells = require_mapping(player.get("spells"), "player_state.spells", errors)
    slots = require_mapping(spells.get("slots", {}), "player_state.spells.slots", errors)
    for level, slot in slots.items():
        validate_resource(slot, f"player_state.spells.slots.{level}", errors)

    _, quest_ids = all_quests(quests, errors)

    npc_ids: list[str] = []
    for index, raw in enumerate(npcs):
        npc = require_mapping(raw, f"npcs[{index}]", errors)
        npc_id = npc.get("id")
        if not isinstance(npc_id, str) or not npc_id:
            errors.append(f"npcs[{index}].id must be a non-empty string")
            continue
        npc_ids.append(npc_id)
        for field in ("knows", "does_not_know", "related_quests"):
            require_list(npc.get(field), f"npc {npc_id}.{field}", errors)
        for quest_id in npc.get("related_quests", []):
            if quest_id not in quest_ids:
                errors.append(f"npc {npc_id} references unknown quest: {quest_id}")
    duplicate_npcs = sorted({item for item in npc_ids if npc_ids.count(item) > 1})
    if duplicate_npcs:
        errors.append("NPC IDs must be unique: " + ", ".join(duplicate_npcs))

    location_ids: list[str] = []
    npc_id_set = set(npc_ids)
    for index, raw in enumerate(locations):
        location = require_mapping(raw, f"locations[{index}]", errors)
        location_id = location.get("id")
        if not isinstance(location_id, str) or not location_id:
            errors.append(f"locations[{index}].id must be a non-empty string")
            continue
        location_ids.append(location_id)
        for npc_id in require_list(location.get("related_npcs"), f"location {location_id}.related_npcs", errors):
            if npc_id not in npc_id_set:
                errors.append(f"location {location_id} references unknown NPC: {npc_id}")
        for quest_id in require_list(location.get("related_quests"), f"location {location_id}.related_quests", errors):
            if quest_id not in quest_ids:
                errors.append(f"location {location_id} references unknown quest: {quest_id}")
    duplicate_locations = sorted({item for item in location_ids if location_ids.count(item) > 1})
    if duplicate_locations:
        errors.append("location IDs must be unique: " + ", ".join(duplicate_locations))
    location_id_set = set(location_ids)
    for raw in npcs:
        if isinstance(raw, dict) and raw.get("location") is not None and raw.get("location") not in location_id_set:
            errors.append(f"npc {raw.get('id', '?')} references unknown location: {raw.get('location')}")
    if world.get("current_location") not in set(location_ids):
        errors.append("world_state.current_location must reference an existing location")

    if not isinstance(battle.get("active"), bool):
        errors.append("battle_state.active must be boolean")
    if battle.get("active"):
        if not battle.get("current_turn"):
            errors.append("active battle requires battle_state.current_turn")
        if not require_list(battle.get("initiative"), "battle_state.initiative", errors):
            errors.append("active battle requires a non-empty initiative list")
        if battle.get("location") not in set(location_ids):
            errors.append("active battle location must reference an existing location")

    dashboard = root / "dashboard" / "dashboard_data.js"
    if check_dashboard:
        if not dashboard.is_file():
            errors.append("missing dashboard/dashboard_data.js")
        else:
            try:
                data = parse_dashboard_data(dashboard)
                expected_hash = public_state_hash(root)
                if data.get("state_hash") != expected_hash:
                    errors.append("dashboard_data.js is stale; run finalize")
            except (ValueError, json.JSONDecodeError) as exc:
                errors.append(f"invalid dashboard_data.js: {exc}")

    return {
        "ok": not errors,
        "root": str(root),
        "errors": errors,
        "warnings": warnings,
    }


def public_projection(root: Path) -> dict[str, Any]:
    meta = json.loads((root / "campaign_meta.json").read_text(encoding="utf-8"))
    player = json.loads((root / "player_state.json").read_text(encoding="utf-8"))
    quests = json.loads((root / "quests.json").read_text(encoding="utf-8"))
    world = json.loads((root / "world_state.json").read_text(encoding="utf-8"))
    locations = json.loads((root / "locations.json").read_text(encoding="utf-8"))
    location_names = {item.get("id"): item.get("name") for item in locations if isinstance(item, dict)}

    player_fields = (
        "name", "pronouns", "race", "class", "level", "background", "rest_state",
        "proficiency_bonus", "stats", "modifiers", "hp", "hit_dice", "ac", "speed",
        "saving_throws", "skills", "features", "spells", "equipment", "gold",
        "conditions", "active_effects", "inspiration", "reputation",
    )
    public_player = {key: player.get(key) for key in player_fields if key in player}
    active_quests = [
        {
            "id": quest.get("id"),
            "title": quest.get("title"),
            "goal": quest.get("goal"),
            "current_progress": quest.get("current_progress"),
        }
        for quest in quests.get("active", [])
        if isinstance(quest, dict)
    ]
    return {
        "campaign": {
            "title": meta.get("title"),
            "language": meta.get("language"),
            "ruleset": meta.get("ruleset"),
        },
        "player": public_player,
        "quests": active_quests,
        "world": {
            "date": world.get("date"),
            "time_of_day": world.get("time_of_day"),
            "weather": world.get("weather"),
            "current_location": world.get("current_location"),
            "current_location_name": location_names.get(world.get("current_location")),
            "player_reputation": world.get("player_reputation", {}),
        },
    }


def public_state_hash(root: Path) -> str:
    payload = json.dumps(
        public_projection(root),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def public_dashboard_data(root: Path) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "state_hash": public_state_hash(root),
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        **public_projection(root),
    }


def write_dashboard_data(root: Path) -> None:
    destination = root / "dashboard" / "dashboard_data.js"
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(public_dashboard_data(root), ensure_ascii=False, indent=2)
    destination.write_text(f"{DASHBOARD_PREFIX}{payload};\n", encoding="utf-8", newline="\n")


def parse_dashboard_data(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8").strip()
    if not text.startswith(DASHBOARD_PREFIX) or not text.endswith(";"):
        raise ValueError("unexpected data wrapper")
    value = json.loads(text[len(DASHBOARD_PREFIX):-1])
    if not isinstance(value, dict):
        raise ValueError("dashboard payload must be an object")
    return value


def roll(expression: str) -> dict[str, Any]:
    match = re.fullmatch(r"(\d*)d(\d+)([+-]\d+)?", expression.replace(" ", ""), re.IGNORECASE)
    if not match:
        raise ValueError("dice expression must look like d20, 2d6, 1d8+3 or 4d6-2")
    count = int(match.group(1) or 1)
    sides = int(match.group(2))
    modifier = int(match.group(3) or 0)
    if not 1 <= count <= 100:
        raise ValueError("dice count must be between 1 and 100")
    if not 2 <= sides <= 10000:
        raise ValueError("die sides must be between 2 and 10000")
    rng = random.SystemRandom()
    rolls = [rng.randint(1, sides) for _ in range(count)]
    return {
        "expression": expression,
        "rolls": rolls,
        "modifier": modifier,
        "total": sum(rolls) + modifier,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local runtime for a codex-dm-kit campaign")
    parser.add_argument("command", choices=("roll", "validate", "finalize"))
    parser.add_argument("value", nargs="?", help="dice expression for the roll command")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root.expanduser().resolve()
    if args.command == "roll":
        if not args.value:
            print(json.dumps({"ok": False, "errors": ["roll requires a dice expression"]}, ensure_ascii=False, indent=2))
            return 2
        try:
            result = {"ok": True, **roll(args.value)}
        except ValueError as exc:
            result = {"ok": False, "errors": [str(exc)]}
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 2
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "finalize":
        result = validate_campaign(root, check_dashboard=False)
        if result["ok"]:
            write_dashboard_data(root)
            result = validate_campaign(root, check_dashboard=True)
    else:
        result = validate_campaign(root, check_dashboard=True)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
