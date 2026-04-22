---
Title: Rich + Typer TUI demoted; not the go-forward product
Status: Accepted
Date: 2026-04-22
---

## Context

The operator console began as a Python TUI built on Rich (`Live`, panels,
tables) and Typer (CLI entry points), with a raw-stdin input loop for
typing fidelity. Over the 2026-Q1 iteration window, four successive
recovery plans were written in response to defects that kept escaping
local tests:

- `archive/2026-03-dashboard-recovery-plan.md` catalogued four
  release-blocking bugs in the live path:
  1. **Width-wrap inflation** — renderables filled terminal width too
     aggressively; one or two characters overflowed the drawable width
     and each wrapped line consumed two rows, doubling effective height.
  2. **Live paint instability** — partial redraws, repeated fragments,
     stale panel content during transitions because the render tree
     used dimensions that drifted within a single frame.
  3. **Typing regressions** — "every second character" dropped;
     slash-command handling and normal typing interfered; raw-input
     fidelity was not reliably defensible.
  4. **Startup state drift** — first-frame messaging sometimes showed
     failure even when the worker started successfully; stale state
     poisoned new launches.
- `archive/2026-03-operator-console-e2e-recovery-plan.md` drew the
  broader conclusion: **unit and snapshot tests are insufficient as a
  release gate for interactive delivery.** Regressions kept shipping
  despite local greens because the TUI's correctness lived entirely in
  real-terminal execution (PTY transcripts, live repaint, keystroke
  feeding, Windows Terminal geometry). The plan rebuilt validation
  around an E2E matrix driven from Windows `pwsh.exe`.

The pattern across all four defects is not "we wrote the Rich code
wrong." It is that the TUI surface concentrates irreducible complexity
(terminal geometry, raw-input semantics, frame composition, startup
state rendering) into a code path that can only be verified by running
the real terminal — and even then, only on the real target environment
(Windows Terminal at the operator's 4K scale). For a product whose
invariant is "identical UX regardless of launch origin," a TUI cannot
carry that contract: Windows Terminal, Windows Console Host, WSL's
Windows-Terminal host, and remote SSH terminals each render Rich's live
primitives differently.

## Decision

Rich + Typer TUI is **demoted**. It is not the forward product. The
operator UI is a native desktop window (see ADR-004) whose contract is
to render a Layer-1 HTTP snapshot, not to drive a terminal.

Typer stays as the service's CLI framework — `uv run npu-service serve`,
`uv run npu-service status`, and the probe-command passthroughs all
remain Typer commands. What leaves is the Rich `Live` dashboard, the
raw-input loop, the width-budget infrastructure, and every module that
exists only to compose frames for a terminal.

The archived TUI code survives in git history. Specifically:
`service/src/npu_service/ui/{atomic_live.py, chat_console.py,
dashboard.py}`, `service/src/npu_service/core/dashboard_debug.py`, and
the dashboard-specific branches of `service/src/npu_service/cli.py`
will be deleted in Iteration 4.1; pre-deletion commit SHAs serve as
pointers for archaeological reference.

## Consequences

**Easier:**

- Cross-launch parity becomes testable. The desktop window renders the
  same pixel tree whether launched from Windows or WSL (ADR-003).
- Release gating via Playwright + `tauri-driver` replaces PTY transcripts
  and keystroke feeders. Test infrastructure is off-the-shelf.
- Input-layer defects (typing-drop regressions) disappear as a category
  — the browser's input handling is not our code.
- Width/layout concerns move to CSS, where they have a 30-year track
  record rather than Rich's 5-year one.

**Harder:**

- Any contributor expecting to run the product in a headless SSH session
  now has to either run a probe command (`uv run npu-service
  endurance-headless`) or accept that the UI requires a desktop.
- The TUI's information density (multi-pane dashboards in 80×24) has to
  be reproduced by the React UI; the migration plan for this lives in
  `docs/roadmap/native-ui.md`.

**New work that follows:**

- Iteration 4.1 removes the TUI module tree and its tests in one
  mechanical pass (plan §4.1 gives the precise file list and the
  `grep` purge guards).
- `service/src/npu_service/web_api.py` → `api.py` rename and
  replacement of `reduce_dashboard_state` (which serialized the TUI
  `DashboardState` dataclass to browser JSON) with
  `build_api_snapshot()` returning service-api-compliant JSON dicts
  (see ADR-002, ADR-008).
- `rich` is removed from `service/pyproject.toml` runtime dependencies;
  CI enforces this via the grep guards in plan §4.1.

## Alternatives Considered

**Keep the TUI and ship it alongside the desktop UI.** Rejected: the
reason regressions kept escaping local tests is that TUI correctness
depends on the real terminal. Shipping both doubles the surface area of
"works-on-my-machine" failure modes without adding user value, because
every user of this product has a desktop (the Windows machine with the
NPU). A headless-server deployment is not a real use case.

**Replace Rich with another TUI library (Textual, prompt_toolkit
standalone).** Rejected: the width-wrap, live-paint, and startup-state
defects are category-level TUI issues, not Rich-specific bugs. Textual
would shift the specific failure modes without changing the class. The
E2E gate problem — that only live-terminal execution catches
regressions — is invariant across TUI libraries.

**Keep the Rich+Typer TUI as the only UI, ship nothing native.**
Rejected: the cross-launch parity invariant (principle #4) cannot be
satisfied by a terminal. Two launch origins with two terminal hosts
produce two different visual contracts. See ADR-003.

## Status

Accepted. Rich+Typer TUI is retired as the forward product. Typer
remains for the service CLI surface. Code removal is scheduled for
Iteration 4.1 per the plan. Re-opening this decision would require new
evidence that the category defects above are actually fixable within a
TUI paradigm — the bar is not "we could work around them" but "they do
not recur."
