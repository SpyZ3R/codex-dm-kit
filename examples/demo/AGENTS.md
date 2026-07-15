# Codex DM campaign instructions

This folder is an initialized local campaign created by codex-dm-kit.

## Start of every task

1. Read `campaign_meta.json` and confirm that `initialized` is `true`.
2. Read `main_prompt.md` completely and follow it as the campaign contract.
3. Load only the current state files required by the scene, using the priority defined in `main_prompt.md`.
4. Never run Session Zero again unless the user explicitly asks to rebuild the campaign.

## Durable commands

- Roll dice: `python tools/codex_dm.py roll <expression>` (on Windows, `py` is an acceptable fallback).
- Validate current state: `python tools/codex_dm.py validate`.
- After a significant in-game change: update affected files, append `session_log.md`, then run `python tools/codex_dm.py finalize`.

## Safety and ownership

- The player controls only Лисса Тихая. Never invent the player's decisions, thoughts, dialogue, spell use, or resource spending.
- Keep NPC knowledge source-based. Private communication is not known to observers unless it is relayed.
- Do not initialize Git, create backup archives, upload campaign files, or copy them outside this project.
- Never overwrite unrelated user files.
- Do not edit `dashboard/index.html` during play. `finalize` updates only `dashboard/dashboard_data.js`.
- Continue in русский unless the user changes language.
