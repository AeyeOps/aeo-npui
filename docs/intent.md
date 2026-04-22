# Intent

## North Star

An operator runs local LLM inference on Intel NPU from a single native
desktop app, launchable identically from Windows or from WSL. NPU-only —
no GPU fallback, no cloud fallback. If NPU stops working, the project
stops.

## Invariants

These are the four project-level invariants. Violating any of them is a
P0 defect, not a tradeoff.

1. **TUI retired.** The Rich + Typer terminal console is not the
   go-forward product. The operator-facing surface is the desktop app.
   See ADR-001.

2. **UI is a pure Layer-1 client.** The desktop app may not call
   `pwsh.exe`, shell out, touch the filesystem directly, or reach
   around Layer 1. Every effect goes through the Layer-1 HTTP contract.
   See ADR-002.

3. **Identical UX across launch origin.** A user launching the app from
   Windows (Start menu, Explorer, `pwsh.exe`) sees the same experience
   as a user launching it from WSL (`cmd.exe /c start`, Windows
   Terminal profile, WSL shortcut). Cross-launch behavioral diffs are
   P0 defects. See ADR-003.

4. **UI talks only to `127.0.0.1:<port>`.** The desktop shell reaches
   Layer 1 over loopback HTTP on a reserved local port. No remote
   endpoints, no alternate transports from the UI side. See ADR-002.

## Stop Conditions

The project stops — does not pivot — under either of:

- **The NPU path fails on the target profile** (Intel Core Ultra on
  Windows 11, driven from WSL). Failure means NPU cannot be brought
  back to working within a reasonable fix window; it does not mean
  "we'll try CPU" or "we'll try GPU."

- **Upstream OpenVINO drops NPU support** for the target class of
  Intel NPU hardware. Same rule: stop, do not pivot.

Notably absent from this list: cloud fallback, GPU fallback, CPU
fallback. None of those are acceptable outcomes. They would weaken the
project goal and hide NPU regressions.

## Where To Go Next

- Layer model and boundaries between layers: [`architecture.md`](./architecture.md).
- Proof that the NPU path is real on the target hardware: [`feasibility.md`](./feasibility.md).
- The eleven individual decisions (ADR-001 through ADR-011) that
  implement the invariants above: [`decisions/`](./decisions/).
