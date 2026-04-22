---
Title: Identical UX across launch origin
Status: Accepted
Date: 2026-04-22
---

## Context

The operator runs the app on a Windows machine with an Intel NPU. There
are two realistic launch paths:

1. From Windows itself — Start menu, Desktop shortcut, `pwsh.exe`.
2. From WSL — a bash shell on the same machine that invokes the
   installed Windows binary via `cmd.exe /c start`.

Historically, UX diverged between these two entry points. The Expo web
bundle was driven by CDP scripts that only ran from WSL; the Rich TUI
rendered differently depending on whether `Windows Terminal` was the
host. Operators on the WSL path saw a visibly different product, which
produced bug reports that were actually environment-divergence reports.

The operator does not care which shell launched the app. They care
that the product looks the same, responds the same, and fails the
same. If it does not, a "works on Windows launch" claim is not a
release claim — it is a conditional one.

## Decision

Cross-launch UX divergence is treated as a **P0 regression**. The test
matrix in `docs/testing.md` (authored in parallel with this ADR)
enumerates scenarios that run twice — once launched from Windows
`pwsh.exe`, once launched from WSL via `cmd.exe /c start` — and
pixel-compares the resulting app state.

Concretely, parity is measured against:

- **First paint** — the window's first painted frame must be
  pixel-identical between launch origins (subject to an allowed
  tolerance band for font-anti-aliasing noise, defined in
  `docs/testing.md`).
- **Window chrome** — title, size, position, menu, tray icon.
- **Service connectivity** — both origins reach the same local
  service on the same port and see the same `/health` response at the
  same time since launch.
- **Keyboard and input focus** — typing works identically; focus
  starts in the same control.
- **Update prompts, error dialogs, exit behavior** — all invariant to
  origin.

Any scenario that diverges is a bug filed before the iteration gate
closes. "The Windows path works; the WSL path is broken" is not an
acceptable iteration exit.

## Consequences

**Easier:**

- The UI contract is defensible to an operator in one sentence: "It
  does the same thing no matter how you launched it."
- Test automation stops having to reason about "which shell is live"
  — the harness just runs both launch paths and compares.
- Divergence regressions are caught mechanically, not via bug reports
  after ship.

**Harder:**

- Any UI feature that depends on "what OS launched me" is rejected.
  The window cannot branch on `process.env.WSL_INTEROP` or similar.
- Path handling requires discipline. WSL paths (`/mnt/c/...`) and
  Windows paths (`C:\...`) both appear in the environment of a
  WSL-origin launch; the UI must not display either directly — the
  service returns paths in a canonical shape (see ADR-010) and the UI
  renders them verbatim.
- The build pipeline has to produce one artifact (the Windows MSI/NSIS
  installer) that serves both launch paths. It does; Tauri does not
  know which shell spawned it.

**New work that follows:**

- `docs/testing.md` (Subagent H) authors the cross-launch matrix with
  explicit scenarios: launch-from-pwsh, launch-from-WSL, install,
  update, service autostart. Each scenario has "origin: pwsh" and
  "origin: wsl" rows.
- `desktop/e2e/` (Iteration 3.5) runs Playwright via `tauri-driver`
  against the installed binary from both origins, with artifact
  capture for visual diffing.
- CI runs the launch-parity subset on every PR that touches
  `desktop/`.

## Alternatives Considered

**Support only Windows-origin launch; tell WSL users to RDP or open a
Windows terminal first.** Rejected: the operator's daily workflow
includes WSL sessions (that's where their shell history, their
scripts, their cross-machine SSH live). Forcing them to leave WSL to
launch the app is a UX break. Invariant #4 exists because of this.

**Support two entry points but allow mild UX divergence (e.g. a banner
that says "launched from WSL").** Rejected: the slope is slippery.
"Mild divergence" becomes feature-gated behavior becomes
origin-dependent bug reports. The invariant has to be strict to be
useful.

**Make the UI a PWA hosted at `http://127.0.0.1:<port>/ui/` so both
origins open the same URL in a browser.** Rejected for separate
reasons in ADR-004 (no native menu/tray/updater; no offline desktop
feel). That said, the PWA alternative would satisfy THIS invariant
trivially — which is a useful sanity check that the constraint is
implementable, just not preferred.

## Status

Accepted. The test matrix in `docs/testing.md` is the enforcement
mechanism. See also: ADR-002 (UI must not call the shell — a
prerequisite for cross-launch parity), ADR-004 (Tauri 2 as the shell
that carries this contract), and `docs/intent.md` where invariant #4
is stated in product-level language.
