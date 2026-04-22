# Roadmap

Current track: extract `npu/` from `aeo-infra` into this repo, retire the
Rich+Typer TUI (ADR-001), and rebuild the operator surface as a Tauri 2 +
Bun + Vite desktop app (ADR-004) that speaks only to a stable
`127.0.0.1:<port>` HTTP+SSE contract (ADR-002, ADR-008). Iteration 1
lands the foundation (docs, ADRs, CI, MIT license, preserved history);
Iterations 2–5 bring up the Tauri shell, port the Expo screens to React
DOM, implement the service API end-to-end, and ship signed installers
with auto-update.

## Workstreams

| File | Scope |
|---|---|
| [`service-layer.md`](./service-layer.md) | Layer-1 extraction: `service/src/npu_service/*.py` → `docs/contracts/service-api.md` compliance; TUI removal; `web_api.py` → `api.py`. |
| [`native-ui.md`](./native-ui.md) | Layer-3 Tauri 2 + Bun + Vite shell, React DOM frontend, typed client; supersedes the archived RN/Expo PRD. |
| [`orchestration.md`](./orchestration.md) | Layer-2 cross-OS launcher: single Windows `.exe`, WSL invocation via `cmd.exe /c start`, service autostart, port reservation. |
| [`tasks.yaml`](./tasks.yaml) | Unified backlog: `N-UI-*`, `SVC-*`, `ORCH-*`, `CI-*`. Each task has `status: proposed`. |

## What lives elsewhere

- Load-bearing design choices: [`../decisions/`](../decisions/)
- HTTP/SSE + storage contracts: [`../contracts/`](../contracts/)
- Historical plans retired from this tree: [`../archive/`](../archive/)
- Testing doctrine and cross-launch matrix: [`../testing.md`](../testing.md)
