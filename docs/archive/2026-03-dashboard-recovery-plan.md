# Dashboard Recovery Plan

## Purpose

Fix the live dashboard until it is actually usable for a human operator.

This plan is intentionally narrower than feature development. The focus is:

- rendering correctness
- typing correctness
- startup correctness
- stable live interaction

## Current Unusability Bugs

### 1. Width wrap inflation

Observed behavior:

- lines appear to render on every second row
- the screen looks double-height
- only the lower part of the screen remains practically usable

Likely cause:

- live renderables are filling the terminal width too aggressively
- one or two characters overflow the real drawable width
- each wrapped line consumes two terminal rows
- the full dashboard height then effectively doubles

Required fix:

- introduce a global width safety margin for the live dashboard
- do not render to the exact reported width
- make all custom renderables respect the same slack
- verify at the actual Windows Terminal environment, not just replay snapshots

### 2. Live paint instability

Observed behavior:

- partial redraw artifacts
- repeated screen fragments
- stale panel content during transitions

Likely cause:

- the live dashboard is redrawing while state is changing in multiple places
- the render tree may be using dimensions or content that drift during one frame

Required fix:

- make one full render tree from a single state snapshot per frame
- avoid ad hoc partial console writes in the interactive path
- keep a single `Live(screen=True)` owner for the live TTY session

### 3. Typing regressions

Observed behavior:

- dropped characters
- previously “every second character”
- slash commands and normal typing have interfered with each other

Required fix:

- treat typing fidelity as a release-blocking bug
- stop hand-tuning unless behavior is validated through the live path
- either:
  - fully stabilize the current raw-input approach, or
  - replace it with a dedicated input layer such as `prompt_toolkit`

### 4. Startup state drift

Observed behavior:

- startup may show failure messaging even when the worker can start successfully
- state transitions are not always trustworthy

Required fix:

- define explicit startup states:
  - `starting`
  - `ready`
  - `failed`
- render them directly and deterministically
- ensure stale worker/session state cannot poison a new launch

## Recovery Strategy

### Phase 1. Freeze features

Do not add new dashboard features until the live console is stable.

No new:

- views
- controls
- summaries
- visual flourishes

until the core path is sound.

### Phase 2. Fix render width globally

Implement one dashboard-wide width budget:

- subtract a fixed safety margin from the terminal width
- apply it to:
  - left pane content
  - right pane content
  - custom metric rows
  - prompt row
  - command list
  - transcript/log content

Acceptance:

- no systematic 1-2 character wrap across the live dashboard
- no “every second line” inflation

Validation:

- actual Windows `pwsh.exe` run at the user’s 4K environment
- fresh full-screen screenshot
- PTY transcript from the live path

### Phase 3. Stabilize frame composition

Make frame generation deterministic:

- gather all state first
- build one render tree
- update `Live` once per tick

Acceptance:

- no mixed partial redraws
- no visible stale fragments during idle refresh

Validation:

- live PTY transcript
- repeated dashboard idle run
- screenshot while idle

### Phase 4. Fix typing path

Choose one of two outcomes:

1. the raw-input loop is proven stable through E2E
2. replace the input layer with `prompt_toolkit`

Decision rule:

- if the current raw-input path continues to show dropped/misread characters after the width/render fixes, stop trying to salvage it and replace it

Acceptance:

- user can type a known string with no dropped characters
- slash commands work
- normal text entry works

Validation:

- E2E typing scenario
- real interactive Windows run

### Phase 5. Revalidate startup state

Acceptance:

- the first screen shows `starting`
- it transitions to `ready` when the model is loaded
- it only shows `failed` on a real startup failure

Validation:

- repeated startup runs
- artifact check for startup state
- PTY transcript

## E2E Gates

Each phase must pass through real interactive validation.

Minimum release gates:

1. `dashboard` starts from Windows `pwsh.exe` with no crash.
2. A 4K Windows Terminal run does not exhibit line-wrap inflation.
3. Typing a known test string does not lose characters.
4. `/quit` exits cleanly.
5. `/view log` remains usable.
6. A fresh screenshot shows the full dashboard fitting on screen as intended.

## Definition Of Done

The dashboard is considered recovered only when:

1. the live dashboard is visually stable
2. width overflow no longer causes double-height rendering
3. typing works reliably
4. startup state is trustworthy
5. the direct Windows `pwsh.exe` path is usable by a human without workarounds
