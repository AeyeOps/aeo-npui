#!/usr/bin/env bash
# Historical recipe for extracting AeyeOps/aeo-infra/npu/ into this repo.
# This extraction has already run; the script is kept as self-documenting
# reference. Do not re-execute against a populated repo.
set -euo pipefail

case "${1:-}" in
  -h|--help)
    cat <<'USAGE'
Usage: extract-from-aeo-infra.sh

Historical recipe for the one-time extraction that produced this repo.

Approach: physical relocation (not git filter-repo). The npu/ subtree
had a single commit of history; preserving it via filter-repo would have
added ceremony without value. git archive respects .gitignore (only
tracked files cross the boundary).

Recipe (already run — 2026-04-22):

  mkdir -p /opt/aeo/aeo-npui
  cd /opt/aeo/aeo-infra
  git archive HEAD npu/ | tar -xC /opt/aeo/aeo-npui --strip-components=1
  cd /opt/aeo/aeo-npui
  git init -b main
  git add -A
  git commit -m "Initial import from aeo-infra/npu/ (2026-04-22)"
  gh repo create AeyeOps/aeo-npui --public --source=. --remote=origin --push

The subsequent reconciliation (console/ -> service/, docs/ reorg, ADRs,
CI, etc.) lives in the commit history that follows the initial import.

Do NOT run this script. If a future extraction is needed (e.g. re-cutting
history for a different purpose), adapt the recipe manually.
USAGE
    exit 0
    ;;
esac

echo "This recipe has already run; AeyeOps/aeo-npui is live. See --help." >&2
exit 1
