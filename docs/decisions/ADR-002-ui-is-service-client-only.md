---
Title: UI is Layer-1 service client only
Status: Accepted
Date: 2026-04-22
---

## Context

The three-layer architecture (`docs/architecture.md`) places the
desktop UI at Layer 3, the Python service at Layer 1, and OS-level
orchestration (process spawn, `pwsh.exe`, `conda activate npu`, WSL↔Windows
bridging) at Layer 2. Layer 0 is the NPU runtime wrapped by Layer 1.

The earlier Expo/RN console (`console-native/`) blurred these layers.
UI code reached into `pwsh.exe` via `shell.open()`/`exec()`-equivalents
to probe the NPU, to read event logs, to invoke endurance scripts.
Windows-only CDP driver scripts lived inside the UI tree. This made the
UI dependent on host-OS details: it could not run on Windows Start
origin vs WSL origin with identical semantics, because the shell it
invoked was different.

Several invariants the product has to hold:

- UX is identical regardless of which OS launched the app (principle
  #4, see ADR-003). A UI that speaks `pwsh.exe` cannot satisfy this.
- Tauri's capability system is a defense-in-depth opportunity: minimal
  capabilities = minimal blast radius if the WebView is compromised.
- The service's HTTP contract is the testable artifact (`curl` from any
  client, Playwright from the real binary). Adding a second contract
  (UI→shell→service) would require a second test surface.

## Decision

The UI (Layer 3) is a **pure Layer-1 client**. It:

- makes HTTP and SSE calls to `http://127.0.0.1:<service-port>`
- renders the JSON responses
- does not invoke `pwsh.exe`, `cmd.exe`, `powershell.exe`, `conda`, or
  any shell
- does not read or write any filesystem path outside its own
  WebView-local state (cache, session storage)
- does not use Tauri `invoke()` for NPU concerns — the only Rust
  commands the UI may call are window-lifecycle hooks (menu, tray,
  updater prompts)

Everything the UI needs from the OS goes through Layer 1. If Layer 1
does not expose it yet, the API contract grows to cover it — the UI
does not reach past the boundary.

## Consequences

**Easier:**

- Cross-launch parity (ADR-003) becomes achievable. The UI's behavior
  does not depend on which shell invoked Tauri.
- Tauri capability config stays minimal: `core:default`, `updater:*`,
  `process:allow-restart`. No `shell`, no `fs`, no `dialog` beyond
  updater prompts (see `desktop/src-tauri/capabilities/main.json` in
  Iteration 2.2).
- CSP in `tauri.conf.json` can lock `connect-src` to the specific
  service port (e.g. `http://127.0.0.1:8765 ws://127.0.0.1:8765`),
  refusing any other network origin.
- The test matrix shrinks: one contract (HTTP+SSE) vs. two (HTTP+SSE
  plus arbitrary shell invocations).
- Replacing the UI (e.g. swapping Tauri for a web-hosted client for
  remote operator use) is a drop-in: the API contract does not change.

**Harder:**

- Any feature that was "the UI runs a PS1" now needs a service route.
  This is planned — `POST /inference`, `GET /events`, `POST
  /endurance`, `POST /session/clear` are the first cut (see ADR-008,
  `docs/contracts/service-api.md`).
- The service has to take on launcher responsibilities (Layer 2) that
  previously sat in the UI. `service/src/npu_service/launcher/` is the
  home for that code.

**New work that follows:**

- `desktop/src/api/` is the only module that makes network calls. All
  other UI modules import from it; none construct `fetch()` themselves
  against ad-hoc URLs.
- CI enforces the rule via inspection: any `fetch(` or `EventSource(`
  call outside `desktop/src/api/` is a review block.
- The Tauri capabilities file is reviewed every iteration to confirm no
  `shell:*` or `fs:*` capability has crept in.

## Alternatives Considered

**Let the UI call Tauri `invoke()` handlers that wrap shell
operations.** Rejected: this hides the violation behind a Rust layer
but does not fix it. The Rust handler would still need `pwsh.exe`
knowledge; the UI would still have two contracts (Layer 1 HTTP + Rust
invoke). Worse, `invoke()` calls are not cross-platform in the same
way HTTP is — a future browser-hosted client cannot call them.

**Minimal Rust `invoke()` for "local-only" operations (read config
file, list models from disk).** Rejected: "local-only" turns into
"small-shell" quickly. The rule is crisp: UI talks to Layer 1 only.
Exceptions compound.

**Keep the Expo-era pwsh/CDP scripts behind a feature flag.**
Rejected: the scripts assume a specific shell and a specific launch
origin. They fail principle #4 structurally. They are deleted in
Iteration 3.6 (see plan §3.1).

## Status

Accepted. The Tauri capability file in `desktop/src-tauri/capabilities/`
and the CSP in `tauri.conf.json` enforce this at the shell layer from
Iteration 2 onward. Layer-1 API coverage is completed in Iteration 4.
See ADR-008 for the HTTP+SSE contract, ADR-003 for the parity
invariant, and ADR-010 for why storage is API-mediated too.
