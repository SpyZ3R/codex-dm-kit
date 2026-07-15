# codex-dm-kit bootstrap instructions

This repository is a public campaign generator, not a live campaign. Never treat `examples/` as the user's current game.

## When the user wants a new campaign

The user's currently opened workspace root is the campaign target. Do not suggest a default storage folder.

Use `python` for kit commands; on Windows, use `py` if `python` is unavailable.

Before asking Session Zero questions:

1. Resolve and show the absolute workspace root.
2. Run `python -m codex_dm_kit inspect-target --target <workspace-root>` from this kit checkout.
3. Stop if the target is inside a Git worktree. If it is already initialized, load that campaign and continue instead of running Session Zero.
4. Inspect existing user files without editing them. Offer relevant character or setting files as import sources.
5. If generated filenames collide, show the exact names and ask the user to preserve or rename them. The generator never overwrites a collision.
6. Never delete, relocate, or overwrite an existing user file without explicit confirmation.

Conduct Session Zero conversationally, with no more than three short questions per response. Establish:

- campaign language (`ru` or `en`);
- create or import the character;
- create or import the setting;
- tone, boundaries, lethality, and desired play mix;
- opening hook and starting location.

If the user has no character or setting, offer a small number of concrete choices instead of requiring a blank-page description. Normalize confirmed answers to the format in `examples/onboarding_answers.ru.json`.

Before writing campaign files, show a concise final concept and obtain explicit confirmation.

Keep the normalized Session Zero answers in memory and pass them over stdin. Never save campaign answers inside the kit checkout or another temporary file. Create the campaign with:

`python -m codex_dm_kit create --answers - --target <workspace-root>`

The JSON supplied over stdin may contain character details, boundaries, and setting material. Do not echo it into logs or retain a second copy.

After creation:

1. Run `<workspace-root>/tools/codex_dm.py validate` with Python.
2. Report the absolute campaign root and dashboard path.
3. Read the generated `AGENTS.md` and `main_prompt.md` explicitly because project instructions are discovered only when a Codex task starts.
4. Start the opening scene in the same conversation.

Do not run `git init` in the campaign, upload its files, create backup archives, or copy it elsewhere. The external bootstrap prompt owns cleanup of a temporary kit clone after successful initialization.

## Repository development

- Runtime code supports Python 3.10+ with no third-party dependencies.
- Run `python -m unittest discover -s tests -v` after changes.
- Run `python -m codex_dm_kit create --answers examples/onboarding_answers.ru.json --target <safe-non-Git-temp-dir> --dry-run` when changing templates.
- Do not copy content, names, or secrets from a user's live campaign into this repository.
