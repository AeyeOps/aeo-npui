# Testing

**Doctrine:** E2E-first. Unit tests and snapshot tests are developer
aids; they do not gate release. The release gate is the cross-launch
matrix below, run green against the installed Tauri binary via
`tauri-driver` on every iteration gate.

Learnings carried forward from the retired
[`archive/2026-03-operator-console-e2e-recovery-plan.md`](./archive/2026-03-operator-console-e2e-recovery-plan.md):

- Unit tests passed locally while interactive delivery regressed
  (startup crashes, dropped characters, prompt/response mismatches).
  Unit coverage is insufficient as a delivery gate for a live operator
  surface.
- PTY transcripts + scripted keystroke feeders + artifact collection
  (events log, watch artifact, endurance artifact) are required harness
  components — keep them as the reference pattern even after the TUI
  retires (ADR-001). The equivalent for the Tauri shell is
  `tauri-driver` + Playwright trace artifacts + SSE event captures.

## Driver choice — `tauri-driver` (plan §3.5)

Playwright cannot drive Tauri's WebView2 by URL. Vanilla
`@playwright/test` assumes a browser it launched itself and a loadable
HTTP URL; a Tauri window is a native `.exe` that embeds WebView2 with
no public URL. Options evaluated (plan §3.5):

- **Option A (chosen):** `tauri-driver` — official WebDriver bridge.
  Launches the Tauri binary, exposes a WebDriver endpoint, Playwright
  talks to it via remote connection. Decision recorded as **ADR-012**
  in Iteration 3.5.
- Option B: Attach to WebView2 CDP on a debug port. Brittle; the port
  changes between runs.
- Option C: WebdriverIO instead of Playwright. Churn for a project
  already using Playwright elsewhere.

## Cross-launch matrix

Every scenario runs against the **installed** `.exe` (not the build-tree
binary — WSL 9P access to the build tree is measurably slower and
distorts timing-sensitive assertions) and runs **twice** — once per
launch origin per ADR-003. Any pixel or timing divergence between origins
is a P0 defect.

| Scenario | Windows-origin command | WSL-origin command | Evidence captured |
|---|---|---|---|
| launch — cold start | Start menu → AEO NPUi **or** `& "$env:LOCALAPPDATA\Programs\aeo-npui\aeo-npui.exe"` | `cmd.exe /c start "" "$LOCALAPPDATA_WIN\\Programs\\aeo-npui\\aeo-npui.exe"` (see `orchestration.md`) | Playwright screenshot + trace, first-paint timing, window-chrome dimensions |
| launch — warm (service already running) | same command with `npu-service serve` already on 8765 | same | screenshot diff against cold-start baseline, `/health` response time |
| install-flow — NSIS | run `*_x64-setup.exe`, click through, launch | same, but NSIS invoked via `cmd.exe /c` | installer UI screenshots, `%LOCALAPPDATA%\Programs\aeo-npui\aeo-npui.exe` existence, first-launch screenshot |
| install-flow — MSI | `msiexec /i *_x64_en-US.msi /qb` from pwsh.exe | `cmd.exe /c msiexec /i ...` from WSL bash | same artifacts as NSIS row, plus `msiexec` log |
| update-flow | install v0.0.1, signal v0.0.2 in `latest.json`, wait for updater prompt, accept, restart | install v0.0.1 launched from WSL, same signaling | updater-prompt screenshot, post-restart version-bar screenshot, Tauri updater signature log |
| service-autostart — happy path | kill any existing npu-service, launch UI, wait for green dot | same, launched from WSL | `/health` poll timeline, PID of spawned service, time-to-green measurement |
| service-autostart — port collision | bind port 8765 with a dummy listener, launch UI | same, launched from WSL | UI error state screenshot, service-launcher error log, confirmation that UI does NOT silently rebind to another port |
| service-autostart — fail-to-ready deadline | patch service to never return ready, launch UI | same, launched from WSL | UI deadline-error screenshot, full autostart attempt log |

Each row is one row in the matrix but two test cases (Windows-origin
and WSL-origin must pass independently). Total: 8 scenarios × 2 origins
= **16 test cases** per iteration gate.

## Required harness components

Built/maintained to serve the matrix above:

- **`tauri-driver` + Playwright remote connection** —
  `desktop/e2e/` launches the installed binary, connects to the
  WebDriver endpoint, drives the window.
- **Scripted keystroke feeder** — a thin Playwright helper that issues
  `page.keyboard.type()` sequences to the Tauri window. Existence of
  this harness is a direct port of the PTY keystroke feeder from the
  retired TUI-era plan; the substrate changed, the harness role did not.
- **SSE event capture** — each test subscribes to the same `/events` and
  `/metrics` streams the UI uses, writes them to
  `output/playwright/<scenario>/events.jsonl`, asserts on them after
  the UI-observable effect is recorded. Keeps assertions on real server
  truth, not on rendered pixels alone.
- **Artifact collector** — Playwright's native trace + screenshot +
  video collection, augmented with copies of
  `%LOCALAPPDATA%\AeyeOps\aeo-npui\logs\service.log` and the
  run-specific event JSONL.
- **Visual-regression baselines** — captured from the retired Expo
  `output/playwright/` tree pre-port and checked in; N-UI-2 regressions
  are caught by diff against baseline. Baselines are re-captured when
  ADR-013 styling decision lands.
- **PTY/replay harness (legacy, retained for probe scripts only)** —
  the PTY transcript runner + keystroke feeder built for the TUI-era
  e2e-recovery plan is kept for exercising the remaining probe scripts
  (`run`, `watch`, `trace`, `phase-zero`, `endurance-headless`) which
  still run as non-TUI Typer commands. Not used for the Tauri window.

## Gate cadence

- **Iteration 2 gate:** launch cold-start scenario runs green on both
  origins against the scaffold (health-dot stub).
- **Iteration 3 gate:** every matrix row runs green on both origins via
  `tauri-driver`.
- **Iteration 4 gate:** same, plus `service-autostart` rows exercise the
  real Layer-2 launcher + port-reservation logic (not the echo stub).
- **Iteration 5 gate:** `update-flow` row exercises the signed
  installer + auto-updater end to end.

## What the matrix does NOT cover

- Mobile viewport fidelity — the Tauri window is desktop-only
  (ADR-004). Responsive CSS in the React DOM port (N-UI-2) is a
  correctness goal, not a gate.
- CLI probe commands — covered by the legacy PTY harness + service
  `pytest` suite, not by the cross-launch matrix.
- Performance regression thresholds — tracked but not gated at this
  stage; revisit after Iteration 5 ships.
