# Native UI (Layer 3) — Tauri 2 + Bun + Vite

**Supersedes:** [`../archive/2026-03-console-native-prd.md`](../archive/2026-03-console-native-prd.md)
(the Expo/RN-web PRD). Expo is retired; React Native primitives are
replaced with React DOM (ADR-004, ADR-005). The UX contract from the
archived PRD (explicit `starting`/`ready`/`failed`, first-prompt
retention, transcript continuity, `/clear` semantics, live interaction
rail, log-follow stability, one-workspace-plus-context-rail layout) is
preserved — only the implementation substrate changes.

**Invariants reinforced here:**

- Layer 3 speaks **only** to `127.0.0.1:<service-port>` (ADR-002). No
  `pwsh.exe`, no filesystem, no `conda`, no direct NPU calls from the
  UI process.
- UX is identical regardless of whether the binary was launched from
  Windows Start menu, `pwsh.exe`, or WSL `bash` (ADR-003). Cross-launch
  diffs are P0 defects.

## Workstreams

### 1. Shell (Rust / Tauri) — ADR-004, ADR-006

- Tauri 2 host. Zero custom Rust commands:
  `tauri::generate_handler![]` stays empty. The shell's job is window
  lifecycle + default menu + tray + updater — nothing else.
- Default menu and tray (no bespoke commands).
- CSP in `tauri.conf.json` locked tight:
  `connect-src 'self' http://127.0.0.1:<port> ws://127.0.0.1:<port>`;
  no wildcard hosts. Dev-mode widening (`http://127.0.0.1:*`) via a
  separate `tauri.conf.dev.json` loaded explicitly with
  `bun run tauri dev -- --config src-tauri/tauri.conf.dev.json`.
- Capabilities file `capabilities/main.json` carries only:
  `core:default`, `updater:default`, `updater:allow-check`,
  `updater:allow-download-and-install`, `process:allow-restart`.
- Updater endpoint =
  `https://github.com/AeyeOps/aeo-npui/releases/latest/download/latest.json`
  (ADR-006). `plugins.updater.pubkey` carries the real pubkey generated
  in pre-flight 1.1.E — no placeholder ever landed.
- Bundle targets: `["nsis", "msi"]`, Windows-only (explicitly scoped to
  avoid Tauri's default "build all targets").

### 2. Frontend (React + Vite) — ADR-005

- React DOM only; no Expo, no React Native, no RN-web.
- React Router for navigation (replaces Expo Router).
- Vite for bundling and dev server. Bun is the package manager and
  script runner; Vite is the bundler — the two split is deliberate, see
  ADR-005.
- Screens migrated from the retired Expo tree. The inventory (each
  screen, its RN primitives, HTML/CSS plan, state-shape dependencies)
  is authored by subagent Q in Iteration 3.1 at
  [`./frontend-migration-inventory.md`](./frontend-migration-inventory.md)
  (document created in Iteration 3; forward reference is fine).
- Translation rules:
  - `View` → `div`
  - `Text` → `span` + CSS
  - `ScrollView` → `div` with overflow
  - `Pressable` → `button`
- Existing state shapes, hooks, and API clients re-used verbatim where
  they're Expo-independent.
- Styling decision (Tailwind vs CSS Modules vs styled-components)
  recorded as ADR-013 in Iteration 3.3.

### 3. Client (API layer) — ADR-008, ADR-002

- `desktop/src/api/` — TypeScript client for the contract in
  [`../contracts/service-api.md`](../contracts/service-api.md).
- Types generated from the service's Pydantic models via
  `scripts/gen-types.sh` (tool wiring lands in Iteration 4.3; see
  [`./service-layer.md`](./service-layer.md) §4.3). Emits to
  `desktop/src/api/types.ts`. CI gates drift with
  `scripts/gen-types.sh --check`.
- Streaming endpoints (`GET /events`, `GET /metrics`) use the browser's
  native `EventSource` — the server provides relative URLs
  (`events_url`, `metrics_url`) that clients pass through directly.
- No `invoke()` calls for NPU concerns. If an NPU-adjacent operation
  appears to require one, it belongs in Layer 1 — file an issue and
  extend the service API per ADR-008.

## Reference ADRs

- [ADR-002 — UI is Layer-1 client only](../decisions/ADR-002-ui-is-service-client-only.md)
- [ADR-003 — Identical UX across launch origin](../decisions/ADR-003-identical-ux-across-launch.md)
- [ADR-004 — Native shell = Tauri 2](../decisions/ADR-004-native-shell-is-tauri-2.md)
- [ADR-005 — Frontend toolchain = Bun + Vite](../decisions/ADR-005-frontend-toolchain-bun-plus-vite.md)
- [ADR-006 — Auto-updater via GitHub Releases](../decisions/ADR-006-auto-updater-via-github-releases.md)
- [ADR-008 — Service API = HTTP + SSE](../decisions/ADR-008-service-api-http-sse.md)

## Acceptance (native UI)

- `bun run tauri dev` opens a native Windows window that renders the
  React skeleton served by Vite.
- `bun run tauri build` produces signed NSIS + MSI installers (signing
  activated in Iteration 5).
- Cross-launch parity: launching the installed `.exe` from Windows Start
  menu and from WSL `cmd.exe /c start` produces pixel-identical first
  paint (ADR-003). Any diff is a P0 defect.
- No Expo / React Native references anywhere in `desktop/`:
  `grep -rI 'expo\|react-native' desktop/` returns empty.
- No Rust `invoke()` calls for NPU operations; CSP `connect-src`
  restricts to the specific service port.
- Screen migration inventory covers every screen in the retired
  `console-native/` tree; no screen is silently dropped.
