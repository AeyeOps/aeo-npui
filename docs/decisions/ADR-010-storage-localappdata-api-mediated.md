---
Title: Artifact and event storage in %LOCALAPPDATA%, API-mediated
Status: Accepted
Date: 2026-04-22
---

## Context

The service writes several kinds of durable state:

- **Events** — structured JSONL of run lifecycle, token arrivals,
  metric samples (`npu-events.jsonl`).
- **Logs** — service process logs, separate from events.
- **Artifacts** — endurance run outputs, probe results,
  diagnostic captures.
- **Models** — on-disk cache of model weights (OpenVINO IR or
  equivalent), since re-downloading is expensive.

Two decisions need to be made:

1. **Where on the filesystem.** Windows convention is
   `%LOCALAPPDATA%` for per-user, non-roaming app data. The operator's
   path is typically `C:\Users\<name>\AppData\Local\`.
2. **Who reads/writes.** Either the UI reaches directly into the
   directory (fast, simple) or the service mediates via API
   (consistent with ADR-002).

The Expo-era console worked by having UI code read `npu-events.jsonl`
directly from disk. This produced cross-launch divergences (the path
differs when running under WSL vs Windows), security surprises (the UI
had filesystem-read capability), and race conditions (the UI's
tail-read and the service's append were not coordinated). ADR-002
established that the UI is a pure Layer-1 client; extending that rule
to storage is the consistent move.

## Decision

**Storage location:** `%LOCALAPPDATA%\AeyeOps\aeo-npui\`

Sub-structure:

```
%LOCALAPPDATA%\AeyeOps\aeo-npui\
├── events\
│   └── npu-events.jsonl        append-only event log
├── logs\
│   └── service.log             service process log (rotated)
├── artifacts\
│   └── <run-id>\               endurance run outputs
└── models\
    └── <model-id>\             OpenVINO model cache
```

**Dev override:** the `NPU_DATA_DIR` environment variable, when set,
replaces `%LOCALAPPDATA%\AeyeOps\aeo-npui\` as the root. Intended for
development and CI, not for production deployment.

**Access pattern:** the UI **never** reads or writes this directory
directly. Everything goes through Layer 1:

- `GET /events?run_id=<uuid>&since=<seq>` — SSE stream sourced from
  `events/npu-events.jsonl`.
- `POST /session/clear` — service performs whatever in-memory and
  on-disk reset is required; UI does not touch disk.
- `POST /endurance` — service writes the artifact and returns
  `artifact_path` for display only; UI does not open or tail it.
- Future `GET /artifacts/<run-id>` — if needed, service streams the
  file content. UI still does not open disk paths.

Tauri's capability file (`desktop/src-tauri/capabilities/main.json`)
does NOT include `fs:*` — the WebView has no filesystem API. This is
the defense-in-depth enforcement of the decision.

## Consequences

**Easier:**

- Cross-launch parity (ADR-003) holds for storage. Windows-origin and
  WSL-origin launches see the same path; the service resolves
  `%LOCALAPPDATA%` the same way regardless of who invoked it.
- No race conditions between UI tail-reads and service appends. The
  service is the single reader of its own append log.
- Schema stability. The on-disk JSONL format can change without
  breaking the UI because the UI speaks the API's JSON shape, not the
  disk shape (though in practice they mirror each other; see ADR-008's
  `build_api_snapshot()`).
- Uninstall is clean. `%LOCALAPPDATA%\AeyeOps\aeo-npui\` is a single
  tree an uninstaller can delete (or that an operator can remove via
  File Explorer) without hunting through the filesystem.

**Harder:**

- The service must run for the UI to see any storage. Plan §4.5
  autostart + port-reservation handles this — first UI launch spawns
  the service if it is not already listening.
- Developer ergonomics: `tail -f` on the JSONL during development
  requires either (a) knowing the `%LOCALAPPDATA%` path or (b) setting
  `NPU_DATA_DIR=./dev-data` and running from a project-local directory.
  Plan's `scripts/launch-dev.sh` sets the env var automatically for
  the dev loop.
- `%LOCALAPPDATA%` expansion requires the service to read the env var
  correctly across WSL-invoked launches. Covered in plan §2.5's
  verification sequence.

**New work that follows:**

- Iteration 4.1's `api.py` includes a settings-aware resolver for
  `NPU_DATA_DIR` (via `pydantic-settings`) that falls back to the
  platform-native user-data dir.
- `docs/contracts/events.md` documents the JSONL schema; the service
  is its canonical writer.
- `docs/contracts/endurance.md` documents the artifact shape; the
  service is its canonical writer.
- Tauri capabilities audit runs every iteration to confirm no
  `fs:allow-read`/`fs:allow-write` capability leaks into the UI.

## Alternatives Considered

**Put data in the installation directory
(`%LOCALAPPDATA%\Programs\aeo-npui\`).** Rejected: mixing code and
runtime data confuses the uninstall story (a clean uninstall would
lose user data) and violates Windows conventions. `%LOCALAPPDATA%`
without the `Programs\` prefix is the right spot for user-scoped
runtime data.

**Put data in `%APPDATA%` (the roaming dir).** Rejected: events
and model caches are machine-local — roaming to another machine
would either re-download models (wasted bandwidth) or hit a different
NPU (wrong cached compilations). `%LOCALAPPDATA%` explicitly disables
roaming.

**Let the UI read the JSONL directly.** Rejected: violates ADR-002.
Also creates the race conditions that plagued the Expo-era console.

**Expose the file path to the UI so it can use Tauri's `shell.open()`
to launch a system editor on the artifact.** Rejected: that's a
`shell:*` capability, which ADR-002 forbids. If an operator needs to
view an artifact, the service streams it over HTTP and the UI renders
it (or a `/artifacts/<id>/download` endpoint streams it with
`Content-Disposition: attachment` to the browser's download UI).

**Use a SQLite database instead of JSONL.** Deferred, not rejected.
JSONL is append-only, human-readable, and trivially greppable.
SQLite is the right choice if/when queries get complex (indexed
lookups, multi-run aggregates). Not a 1.0 concern.

## Status

Accepted. Directory structure defined; `NPU_DATA_DIR` override
documented. Implementation: Iteration 4. Tauri capability enforcement
from Iteration 2.2. See ADR-002 for the layer boundary this
implements, ADR-008 for the API routes that mediate access.
