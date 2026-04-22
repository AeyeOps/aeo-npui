#!/usr/bin/env bash
# Generate desktop/src/api/types.ts from Pydantic models in service/.
# Wired up in Iteration 4 (Subagent Y); stub for Iteration 1.
set -euo pipefail

case "${1:-}" in
  -h|--help)
    cat <<'USAGE'
Usage: gen-types.sh [--check]

Generate desktop/src/api/types.ts from the Pydantic models that back the
HTTP+SSE contract in docs/contracts/service-api.md.

Modes:
  (default)   Regenerate types.ts in place.
  --check     Exit non-zero if the emitted file differs from the
              committed types.ts. Used by CI to fail drift.

Iteration 4 (Subagent Y) selects the concrete toolchain:
  Path A: pydantic2ts (direct Pydantic -> TS). Simpler.
  Path B: openapi-typescript + openapi-fetch (via /openapi.json).
          Types anchored to the served OpenAPI doc.

The choice is recorded in docs/contracts/service-api.md at that time.
USAGE
    exit 0
    ;;
esac

echo "gen-types.sh is a stub; wired in Iteration 4. See --help." >&2
exit 1
