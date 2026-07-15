# codex-dm-kit

[Русский](README.ru.md)

`codex-dm-kit` is an unofficial toolkit for local solo campaigns in Codex: DnD 5e light, honest dice, file-backed memory, source-based NPC knowledge, and a character dashboard that opens directly from disk.

Git is used only to obtain the kit. The campaign stays in the local project folder selected by the user and receives no `.git` directory. The kit itself does not upload campaign files.

Requirements: Codex with a local project folder, Git, and Python 3.10 or newer.

## Quick start

1. Create or choose the local folder for the campaign.
2. Open that exact folder as a project in Codex.
3. Paste the block below as the first message.

```text
Create a local solo campaign in the currently open project folder using codex-dm-kit.

Source:
https://github.com/SpyZ3R/codex-dm-kit

Release ref:
v0.1.1

Work autonomously:

1. Resolve the absolute path of the current project root and show it to me.
2. Use that root as the campaign folder. Do not suggest another location unless necessary.
3. Confirm that the folder is not inside a Git worktree and does not contain .git. The campaign must not use Git.
4. Inspect existing files. Do not delete or overwrite them without my confirmation. Treat relevant character or setting documents as import material.
5. If an initialized codex-dm-kit campaign already exists, do not run Session Zero again; load and continue it.
6. Confirm that Git and Python 3.10+ are available.
7. Clone the exact release ref of codex-dm-kit with a shallow clone into the system temporary directory. Verify that HEAD resolves to the requested tag. Never clone it inside my project folder.
8. Read AGENTS.md and README.md completely from the temporary clone.
9. Conduct a conversational Session Zero with no more than three short questions per response.
10. Offer to create the character and setting together or import my existing material.
11. Establish language, tone, boundaries, danger, and preferences for exploration, dialogue, combat, and mystery.
12. Show the final concept and obtain my confirmation before creating files.
13. After confirmation, pass the normalized Session Zero JSON to the generator over stdin and create campaign files directly in the open project root. Do not save those answers in the clone or another temporary file.
14. Do not run git init, upload campaign files, or create external copies.
15. Validate the campaign and generate the dashboard.
16. Read the generated AGENTS.md and main_prompt.md, then begin the first game scene in this same conversation.
17. After successful initialization, delete only the temporary codex-dm-kit clone that you created.
```

## What Codex asks

Session Zero can create a character and setting from scratch or import existing material. Codex establishes language, tone, boundaries, danger, the desired mix of exploration, dialogue, combat, and mystery, then presents a final concept before writing files.

## Generated campaign

The selected folder receives persistent GM instructions, structured JSON state, an append-only session log, GM secrets, rules notes, visualization continuity, local runtime tools, and the dashboard. The complete anonymized input format is illustrated in [`examples/onboarding_answers.ru.json`](examples/onboarding_answers.ru.json).

After a significant event, Codex synchronizes affected files, appends the log, and runs `finalize`. An out-of-game question should not change campaign files.

## Manual commands

From a kit checkout:

```bash
python -m codex_dm_kit inspect-target --target /chosen/project
python -m codex_dm_kit create --answers answers.json --target /chosen/project
```

The automated bootstrap uses `--answers -` and supplies JSON over stdin so Session Zero data is not copied into the temporary kit checkout.

Inside a generated campaign:

```bash
python tools/codex_dm.py roll 1d20+5
python tools/codex_dm.py validate
python tools/codex_dm.py finalize
```

On Windows, `py` can be used instead of `python`.

## Continue later

Open the same campaign folder as the Codex project and ask Codex to continue. Its generated `AGENTS.md` loads the existing state and prevents Session Zero from running again. After `finalize`, refresh an already open dashboard tab to see the latest state.

## Privacy and safety

- Initialization is rejected inside a Git worktree.
- Generated filenames are never overwritten.
- Other existing user files are preserved.
- The dashboard uses a public-field allowlist and excludes GM secrets, hidden quests, and unknown information.
- No OpenAI API key is required; the kit uses the user's existing Codex session.
- Choose a genuinely local, non-synced folder if the campaign must stay on one device. OneDrive, Dropbox, network drives, backup software, and the host product may have their own data-handling behavior.
- `secrets.md` is plaintext spoiler separation for the GM, not encryption or access control. Never put API keys, passwords, private keys, or other real credentials in campaign files.

## Version 0.1 limits

- one player controlling one character;
- NPC companions remain GM-controlled;
- DnD 5e light mechanics;
- local storage only;
- no campaign Git history, synchronization, or dedicated rollback.

## Development

```bash
python -m unittest discover -s tests -v
```

Released under the [MIT License](LICENSE). `codex-dm-kit` is not affiliated with OpenAI or Wizards of the Coast. Codex is an OpenAI product; Dungeons & Dragons and DnD belong to their respective rights holders.
