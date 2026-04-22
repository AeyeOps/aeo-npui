#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# ///
"""Single-source version management for aeo-npui.

The canonical version lives in `/VERSION` at the repo root. Every
manifest that ships a version field is synchronised from that file —
hand-edit VERSION, run `make version-sync`, commit the lot. CI runs
`make version-check` to fail fast if a manifest drifts.

Commands:
  version.py             — print the canonical version
  version.py check       — exit 1 if any manifest drifts from VERSION
  version.py sync        — rewrite every manifest to match VERSION
  version.py bump X.Y.Z  — write X.Y.Z to VERSION, then sync

console-native/package.json is frozen at its retired version (ADR-004
superseded the Expo/RN shell) and deliberately NOT synced.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
VERSION_FILE = REPO / "VERSION"

# (label, path, kind) — kind selects the rewrite strategy below.
TARGETS: list[tuple[str, pathlib.Path, str]] = [
    ("root package.json",     REPO / "package.json",                    "json"),
    ("desktop/package.json",  REPO / "desktop/package.json",            "json"),
    ("tauri.conf.json",       REPO / "desktop/src-tauri/tauri.conf.json", "json"),
    ("Cargo.toml",            REPO / "desktop/src-tauri/Cargo.toml",    "toml-package"),
    ("service/pyproject.toml", REPO / "service/pyproject.toml",         "toml-project"),
]

VERSION_RE = re.compile(r"^\d+\.\d+\.\d+([.-][0-9A-Za-z.-]+)?$")


def canonical() -> str:
    return VERSION_FILE.read_text().strip()


def read_manifest(path: pathlib.Path, kind: str) -> str:
    """Extract the version field from a manifest without touching anything else."""
    text = path.read_text()
    if kind == "json":
        # Minimal field read — keep the file byte-identical if we don't need to rewrite.
        return json.loads(text)["version"]
    if kind == "toml-package":
        # [package]\n...version = "X.Y.Z" — first one, under the top [package] table.
        match = re.search(r'^\s*\[package\](?:.*\n)*?\s*version\s*=\s*"([^"]+)"', text, re.MULTILINE)
        if not match:
            raise ValueError(f"no [package].version in {path}")
        return match.group(1)
    if kind == "toml-project":
        match = re.search(r'^\s*\[project\](?:.*\n)*?\s*version\s*=\s*"([^"]+)"', text, re.MULTILINE)
        if not match:
            raise ValueError(f"no [project].version in {path}")
        return match.group(1)
    raise ValueError(f"unknown manifest kind: {kind}")


def write_manifest(path: pathlib.Path, kind: str, new: str) -> bool:
    """Rewrite the version field. Returns True if the file changed."""
    text = path.read_text()
    if kind == "json":
        # Preserve indentation and key order; only touch the "version" value.
        pattern = re.compile(r'("version"\s*:\s*)"[^"]+"')
        if not pattern.search(text):
            raise ValueError(f'no "version" key in {path}')
        new_text = pattern.sub(lambda m: f'{m.group(1)}"{new}"', text, count=1)
    elif kind == "toml-package":
        pattern = re.compile(r'(^\s*\[package\](?:.*\n)*?\s*version\s*=\s*)"[^"]+"', re.MULTILINE)
        if not pattern.search(text):
            raise ValueError(f"no [package].version in {path}")
        new_text = pattern.sub(lambda m: f'{m.group(1)}"{new}"', text, count=1)
    elif kind == "toml-project":
        pattern = re.compile(r'(^\s*\[project\](?:.*\n)*?\s*version\s*=\s*)"[^"]+"', re.MULTILINE)
        if not pattern.search(text):
            raise ValueError(f"no [project].version in {path}")
        new_text = pattern.sub(lambda m: f'{m.group(1)}"{new}"', text, count=1)
    else:
        raise ValueError(f"unknown manifest kind: {kind}")
    if new_text == text:
        return False
    path.write_text(new_text)
    return True


def cmd_check() -> int:
    want = canonical()
    drift: list[str] = []
    for label, path, kind in TARGETS:
        have = read_manifest(path, kind)
        mark = "ok" if have == want else "DRIFT"
        print(f"  {mark:5s} {label:24s} {have}")
        if have != want:
            drift.append(f"{label}: has {have!r}, VERSION has {want!r}")
    if drift:
        print()
        print(f"VERSION = {want}")
        print("Drift detected — run `make version-sync`:")
        for line in drift:
            print(f"  - {line}")
        return 1
    print(f"\nVERSION = {want} — all manifests in sync.")
    return 0


def cmd_sync() -> int:
    want = canonical()
    changed: list[str] = []
    for label, path, kind in TARGETS:
        if write_manifest(path, kind, want):
            changed.append(label)
            print(f"  updated {label} -> {want}")
        else:
            print(f"  already {label} = {want}")
    print()
    if changed:
        print(f"VERSION = {want} — {len(changed)} manifest(s) updated.")
    else:
        print(f"VERSION = {want} — no changes needed.")
    return 0


def cmd_bump(new: str) -> int:
    if not VERSION_RE.match(new):
        print(f"not a valid version: {new!r} (want X.Y.Z or X.Y.Z-prerelease)", file=sys.stderr)
        return 2
    VERSION_FILE.write_text(new + "\n")
    print(f"VERSION {canonical()} — bumped; syncing manifests:")
    return cmd_sync()


def main(argv: list[str]) -> int:
    if len(argv) == 1:
        print(canonical())
        return 0
    cmd = argv[1]
    if cmd == "check":
        return cmd_check()
    if cmd == "sync":
        return cmd_sync()
    if cmd == "bump":
        if len(argv) != 3:
            print("usage: version.py bump X.Y.Z", file=sys.stderr)
            return 2
        return cmd_bump(argv[2])
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
