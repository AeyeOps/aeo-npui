#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair Chrome profile exit_type in Preferences")
    parser.add_argument(
        "--profile-root",
        required=True,
        help="Windows profile root mounted in WSL, e.g. /mnt/c/dev/chrome-profile",
    )
    parser.add_argument("--profile-directory", default="Default", help="Profile directory inside the root")
    parser.add_argument("--exit-type", default="Normal", help="Replacement exit type")
    args = parser.parse_args()

    preferences = Path(args.profile_root) / args.profile_directory / "Preferences"
    if not preferences.exists():
        raise SystemExit(f"Missing Preferences file: {preferences}")

    original = preferences.read_text(encoding="utf-8")
    data = json.loads(original)
    profile = data.setdefault("profile", {})
    previous = profile.get("exit_type")

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup = preferences.with_name(f"Preferences.backup.{timestamp}.json")
    backup.write_text(original, encoding="utf-8")

    profile["exit_type"] = args.exit_type
    preferences.write_text(
        json.dumps(data, separators=(",", ":"), ensure_ascii=False),
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "preferences_path": str(preferences),
                "backup_path": str(backup),
                "previous_exit_type": previous,
                "new_exit_type": profile.get("exit_type"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
