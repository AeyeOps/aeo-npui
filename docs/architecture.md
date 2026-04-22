# Architecture

This document defines the layer model and boundaries between layers.
For the *why* (north star, invariants, stop conditions), see
[`intent.md`](./intent.md). For individual decisions with rationale,
see [`decisions/`](./decisions/).

## Layer Model

The system has four layers. Layer 0 is the underlying NPU execution
primitive; Layers 1–3 are the ones we build and ship. The project
writes code in L1, L2, and L3 and treats L0 as a wrapped external.

```
Layer 3 — Desktop UI (Tauri 2 + WebView2 + React/Vite)
          speaks only to Layer 1 over 127.0.0.1:<port>

Layer 2 — Launch & cross-OS orchestration
          (WSL <-> Windows bridge, conda activation,
           port reservation, autostart)
          invisible to L3 and L1 once running

Layer 1 — NPU Service (Python + FastAPI + SSE)
          stable HTTP contract; see contracts/service-api.md

Layer 0 — NPU execution (OpenVINO on Windows)
          wrapped by L1; not addressable from higher layers
```

### Layer 0 — NPU execution

The raw NPU path: Intel NPU driver, OpenVINO runtime, OpenVINO GenAI
pipelines, and NPU-targeted models on the Windows host. Layer 0 is
*not* a module we author — it is a dependency. Layer 1 wraps it.

### Layer 1 — NPU Service

A Python process hosting FastAPI (HTTP + SSE) on a loopback port.
Owns all NPU calls, all model loading, all inference state, and all
persistent storage of artifacts and events. Exposes a stable HTTP
contract documented in [`contracts/service-api.md`](./contracts/service-api.md).

L1 is the only layer allowed to import OpenVINO or touch NPU APIs.
L1 does not know that a UI exists; a well-behaved HTTP client using
only the documented contract is indistinguishable from the desktop
shell. See ADR-002.

### Layer 2 — Launch & cross-OS orchestration

The glue that makes the app launchable identically from Windows and
from WSL. Owns: activating the `npu` conda environment on the Windows
side, starting the Layer-1 service, reserving a free loopback port,
writing/reading the port handshake, autostart registration, WSL-side
shortcuts that invoke the Windows-side launcher via `cmd.exe /c start`
or equivalent.

L2 runs at startup and then gets out of the way. Once L1 is up and
L3 has the port number, L2 is invisible. See ADR-003 for the
identical-UX invariant that L2 exists to satisfy.

### Layer 3 — Desktop UI

Tauri 2 shell (Rust host) rendering a React/Vite web app inside the
OS's WebView2. The Rust host handles window lifecycle and native OS
integration; the web app handles all UI state and rendering. The web
app reaches Layer 1 over HTTP + SSE on `127.0.0.1:<port>`.

L3 does not invoke `pwsh.exe`, does not shell out, does not touch the
filesystem outside Tauri's standard app directories, does not import
OpenVINO, does not know the conda env name. See ADR-002.

## Responsibility Matrix

| Concern | L0 | L1 | L2 | L3 |
|---|---|---|---|---|
| NPU device access | yes (via OpenVINO) | wraps L0 | no | no |
| Model loading & inference | no | yes | no | no |
| HTTP contract (request/response/SSE) | no | owns | no | consumes |
| Pydantic schemas / server-side validation | no | owns | no | no (reads generated TS types) |
| `%LOCALAPPDATA%\AeyeOps\aeo-npui\` reads/writes | no | owns | no | no (asks L1) |
| Event log (`npu-events.jsonl`) | no | owns | no | no (streams via SSE) |
| Port reservation & handshake | no | publishes port | reserves and starts L1 | reads port and connects |
| Conda environment activation | no | no | yes | no |
| `pwsh.exe` / `cmd.exe /c start` invocations | no | no | yes | no |
| WSL-side launcher shortcuts | no | no | yes | no |
| Autostart registration | no | no | yes | no |
| Window lifecycle, tray icon, native menus | no | no | no | yes (Tauri Rust host) |
| UI state, rendering, user interaction | no | no | no | yes (React/Vite) |
| Auto-updater plumbing | no | no | assists | yes (Tauri updater) |

## What Each Layer Must Not Know

These are not style preferences; they are boundary contracts. A
violation is a layering bug.

### L3 (Desktop UI) must not know

- That `pwsh.exe` exists, that conda exists, that Windows and WSL are
  two different OSes. The shell is handed a port number and speaks
  HTTP; origin of the port is L2's problem.
- The on-disk layout of `%LOCALAPPDATA%\AeyeOps\aeo-npui\`. Artifacts
  and events are retrieved through L1 endpoints (ADR-010).
- The shape of Pydantic models. L3 consumes generated TypeScript
  types derived from L1's schemas; it does not import server code.
- Which model is loaded, which OpenVINO version is installed, whether
  the NPU driver was updated this morning. That is L1's internal
  state and L0's dependency surface.

Violation example: calling `invoke()` in Tauri to run an NPU operation
directly. Correct: POST to the documented Layer-1 endpoint. See
ADR-002.

### L2 (Launch & orchestration) must not know

- The shape of any Pydantic model, the names of any L1 endpoints
  beyond health/ready, or what JSON the UI sends. L2 starts L1 and
  exits stage left; it does not participate in request flow.
- UI state, routing, or rendering. L2 does not ship UI assets or
  know what the user sees.
- NPU specifics. L2 activates a conda environment and starts a
  Python process; whether that process does NPU inference or
  computes primes is below its abstraction.

Violation example: L2 reading `npu-events.jsonl` to decide whether to
restart the service. Correct: L2 queries `/health` or `/ready` on L1.

### L1 (NPU Service) must not know

- That a desktop UI exists. L1 serves a documented HTTP contract;
  any caller that obeys it is valid. A Playwright test hitting L1
  directly is as legitimate as the real shell.
- UI-side state: selected conversation, scroll position, theme,
  panel layout. These are purely L3 concerns.
- How it was launched. L1 reads a port from config or env, binds
  loopback, and runs. Whether L2 double-clicked a `.lnk`, ran
  `cmd.exe /c start`, or a developer ran `uv run npu-service serve`
  directly is not L1's problem.

Violation example: L1 writing UI-state JSON files to assist L3.
Correct: L3 persists its own UI state; L1 persists only artifacts
and events.

### L0 (NPU execution) must not know anything

It's a dependency. If L0 needs to know something about our app, we've
built something wrong — we push the knowledge up into L1 and wrap it.

## Cross-Launch Parity

The identical-UX invariant from [`intent.md`](./intent.md) (ADR-003)
is enforced architecturally rather than by discipline. The mechanism:

- L2 is the only layer whose code path differs by launch origin
  (Windows-native vs. WSL-initiated). L2 converges on a single
  outcome: L1 running on a known loopback port.
- L3 receives only the port number. Its code path is identical
  regardless of how the app was launched.
- L1 is a pure HTTP server and has no awareness of origin.

If L3 behaves differently depending on launch origin, the difference
lives either in L2's handoff or in L3 reaching around L2 — both of
which are bugs. E2E test expectation: every scenario runs twice (once
Windows-launched, once WSL-launched) with byte-equivalent UI
transcripts.

## See Also

- [`intent.md`](./intent.md) — north star, invariants, stop conditions.
- [`contracts/service-api.md`](./contracts/service-api.md) — the
  stable L1 HTTP contract that L3 consumes.
- [`decisions/`](./decisions/) — ADR-001 through ADR-011.
- [`feasibility.md`](./feasibility.md) — evidence that L0 + L1 is a
  working path on target hardware.
