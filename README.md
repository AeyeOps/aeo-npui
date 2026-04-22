# aeo-npui

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

NPU-first local LLM operator app. Python FastAPI + SSE service (Layer 1)
wrapped by a Tauri 2 desktop shell (Layer 3). Launchable identically
from Windows and from WSL. NPU-only — no GPU fallback, no cloud
fallback.

Status: Iteration 1 foundation (2026-04-22). Service layer extracted
from `AeyeOps/aeo-infra/npu/`; desktop scaffold lands in Iteration 2.

See [`docs/intent.md`](./docs/intent.md) for the north star and the four
invariants that drive every design decision.

## Layout

| Path | What | Status |
|---|---|---|
| [`service/`](./service/) | Layer 1 — Python + FastAPI + SSE, OpenVINO NPU worker, cross-OS launcher | live (Iteration 1) |
| [`desktop/`](./desktop/) | Layer 3 — Tauri 2 + React + Vite shell | Iteration 2 |
| [`docs/`](./docs/) | Intent, architecture, ADRs, contracts, roadmap, archive | live |
| [`scripts/`](./scripts/) | Repo-level dev helpers (extract, codegen, dev launcher) | live |

## Quick start

First-time setup — install OS-native prerequisites (webkit2gtk on Linux,
MSVC Build Tools + WebView2 on Windows):

```bash
make bootstrap                   # Linux / WSL (apt, requires sudo)
# or: .\bootstrap\bootstrap.ps1  # Windows (winget)
```

See [`bootstrap/README.md`](./bootstrap/README.md) for the pattern.

Then:

```bash
uv sync                          # install Python workspace deps
bun install                      # install desktop JS deps
make ci                          # full gate: service + Linux cargo + (on WSL) Windows NSIS/MSI + locks + guards
```

Or run layers individually:

```bash
cd service && uv run pytest      # service tests
uv run ruff check
uv run ty check                  # the only Python type checker (see CLAUDE.md)

cd desktop && bun run tauri dev  # desktop dev loop

make build-windows               # just the Windows NSIS/MSI bundles (syncs repo to %TEMP%\aeo-npui-build)
```

## Conventions

- **Package managers**, one per layer: `uv` (service), `bun` (desktop),
  `cargo` (Tauri shell). See [`AGENTS.md`](./AGENTS.md).
- **Versioning**: manifests declare `>=` minimums; lock files pin; CI
  installs frozen. See [`CLAUDE.md`](./CLAUDE.md) for the rule.
- **Python version**: `>=3.13,<3.14` — rationale in
  [ADR-011](./docs/decisions/ADR-011-python-3-13-workspace-pin.md).
- **Type checking**: `ty` for Python, `tsc` for TypeScript — no
  alternates anywhere. Enforced by a CI checker-purity guard.

## License

MIT. See [`LICENSE`](./LICENSE). This repo is **public from day 1** to
keep the SignPath Foundation OSS signing path open — rationale in
[ADR-007](./docs/decisions/ADR-007-signing-signpath-foundation.md).
