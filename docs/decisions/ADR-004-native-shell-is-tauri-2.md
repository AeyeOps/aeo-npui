---
Title: Native shell is Tauri 2
Status: Accepted
Date: 2026-04-22
---

## Context

Per invariant #2 (native on Windows desktop, launchable from Windows or
WSL) and ADR-002 (UI is Layer-1 client only), the desktop shell needs
to provide:

- a native window (not a browser tab) with Windows-native menu, tray,
  and notification integration
- an auto-updater (ADR-006) with signature verification
- a strict CSP that locks network egress to `127.0.0.1:<service-port>`
  only
- a minimal capability surface (no shell, no fs, no dialog beyond
  updater prompts)
- a runtime that embeds an OS WebView, not a bundled browser runtime
  (binary size, memory footprint, update cadence)
- a build pipeline that produces signed MSI + NSIS installers and a
  `latest.json` updater manifest consumable from GitHub Releases
  (ADR-006)

The shell must not leak the TUI failure modes (ADR-001) — typing must
be the browser's, rendering must be CSS, geometry must be handled by
WebView2, not by hand.

Cross-launch parity (ADR-003) requires that whatever shell the project
picks behaves identically regardless of launch origin. That rules out
any shell that embeds OS-dependent UI chrome.

Tauri 2 was released in late 2024 with a substantially reworked plugin
and capability system, `plugin-updater` with ed25519 signing, stable
support for WebView2 on Windows, and the `tauri-driver` WebDriver
bridge that the E2E story (Iteration 3.5) depends on. At the time of
this decision (2026-Q2), Tauri 2 is mature for Windows desktop; the
ecosystem (tauri-action, signpath GitHub Action, plugin-updater) is
production-ready.

## Decision

The native shell is **Tauri 2** — Rust host, OS WebView (WebView2 on
Windows), Bun + Vite for the frontend build (ADR-005). Binary output:
MSI and NSIS installers via `tauri-action` with Authenticode signing
via SignPath Foundation (ADR-007).

Concretely:

- `desktop/src-tauri/tauri.conf.json` is the configuration surface;
  `productName: "aeo-npui"`, `mainBinaryName: "aeo-npui"` (or Cargo
  `package.name` if the Tauri schema field has moved — see plan §2.2).
- `desktop/src-tauri/capabilities/main.json` lists the minimum
  capability set: `core:default`, `updater:default`,
  `updater:allow-check`, `updater:allow-download-and-install`,
  `process:allow-restart`.
- `desktop/src-tauri/src/main.rs` is thin: default menu, tray, zero
  custom `invoke_handler` commands.
- CSP in `tauri.conf.json` restricts `connect-src` to
  `http://127.0.0.1:8765 ws://127.0.0.1:8765` (per ADR-002).

## Consequences

**Easier:**

- Binary size is modest. Tauri on Windows produces ~10–15 MB installers
  because the WebView2 runtime is a shared OS component, not bundled.
- Security posture is defensible: minimal Rust surface, minimal
  capability surface, CSP-locked network egress, OS-provided WebView
  that gets security updates via Windows Update.
- The signing path is one commercial tool away from zero cost:
  SignPath Foundation for OSS is free (ADR-007).
- Rust appears in the codebase only for shell lifecycle hooks. The
  product is still a TypeScript + Python product.

**Harder:**

- `tauri-driver` is the only practical way to drive E2E tests against
  the binary (ADR-012 in Iteration 3.5). Adds a dev-dependency.
- Rust toolchain appears in CI and in the developer setup. Cargo is
  invisible during iteration but not during bootstrap.
- Some tutorials on the internet target Tauri 1; the config schema
  moved. Plan §2.2 verifies field paths at scaffold time.

**New work that follows:**

- Iteration 2 scaffolds the Tauri project, writes the config, wires
  the updater.
- Iteration 5 integrates SignPath signing into the release workflow.
- `tauri-driver` is introduced in Iteration 3.5 with its own ADR-012.

## Alternatives Considered

**Electron.** Rejected: binary size (120–180 MB typical because
Chromium is bundled), a larger and more active attack surface
(historical CVEs in Electron's IPC layer), heavier memory footprint
per window, and a default security posture that requires opt-in
hardening. Electron is right when the team has to target Linux + macOS
+ Windows with identical Chromium; this product is Windows-only.

**Electrobun.** Rejected: at the time of this decision the project is
young, the ecosystem (code signing integrations, updater plugins,
E2E drivers) is not established, and Windows-WebView2 support is not
at parity with Tauri 2. Revisit in 12–18 months if the ecosystem
develops.

**Bunv.** Rejected: still-wet-paint at time of decision. No production
references, no signing pipeline integrations, no documented updater
flow. Not a bet the product can place.

**PWA (service-hosted web UI, no desktop shell).** Rejected: no native
menu, no tray, no updater prompts (the browser is the updater), no
offline install affordance. An operator launching "the product" opens
a browser tab — which is not what the product is. Also fails the
invariant that Windows Start can launch the app.

**Webview2 via direct Rust without Tauri.** Rejected: re-implements
the capability system, the updater signature flow, the config schema,
and the build pipeline that Tauri already provides. Reinventing is
only worth it if Tauri is blocking something specific; it is not.

**Webview2 via .NET (WPF/WinUI hosting WebView2).** Rejected: adds
.NET as a third ecosystem alongside Python and Node/Bun. The Rust
footprint in Tauri is smaller than a .NET dependency graph would be,
and the cross-repo Action ecosystem (tauri-action, signpath-action)
is purpose-built for Tauri projects.

## Status

Accepted. Tauri 2 is scaffolded in Iteration 2 (plan §2.1). Config,
capabilities, and CSP land in 2.2. Updater and signing in Iteration 5.
See ADR-005 for the frontend toolchain inside the Tauri shell, ADR-006
for the updater pipeline, ADR-007 for signing.
