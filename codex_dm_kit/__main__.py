from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .generator import CampaignCreationError, create_campaign, inspect_target


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codex-dm-kit",
        description="Create a local, non-Git Codex DM campaign in a chosen folder.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="create a campaign from normalized answers")
    create.add_argument("--answers", required=True, type=Path, help="UTF-8 JSON answers file")
    create.add_argument("--target", required=True, type=Path, help="chosen campaign project root")
    create.add_argument("--dry-run", action="store_true", help="validate and list files without writing")

    inspect = subparsers.add_parser("inspect-target", help="check whether a folder is safe to initialize")
    inspect.add_argument("--target", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "inspect-target":
            result = inspect_target(args.target)
        else:
            result = create_campaign(args.answers, args.target, dry_run=args.dry_run)
    except CampaignCreationError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
