# Operator Console Plan

## Decision

Build the operator experience as a Rich + Typer console, not Textual.

Why:

- the current NPU path is already script-first and event-log-first
- Rich is sufficient for panels, tables, progress, logs, and a full-screen live layout
- Typer is sufficient for command shape, help, prompts, and completion
- the main project risk is NPU reliability, not advanced widget behavior
- this avoids spending disproportionate time debugging UI framework issues

## Goal

Create one operator console for the NPU workflow that:

- runs the current NPU-only probes and traces
- shows interaction and system state in one screen
- remains scriptable and testable
- is self-testable at the UX level, not just the business-logic level

## Execution Policy

Execute the remaining iterations continuously:

- when one iteration reaches its acceptance criteria, start the next without pausing for user confirmation
- rework immediately when gaps are found during validation
- do not treat an iteration as complete until its scoped UX and behavioral checks pass

## Overarching Acceptance

There is one final acceptance criterion for the remaining work:

- all remaining iterations are implemented and validated with no errors
- the user can run the TUI/CLI directly from a Windows `pwsh.exe` shell

## Product Shape

The console should stay thin over the existing execution path:

```text
Typer commands
    |
    v
Rich render layer
    |
    v
existing scripts + JSON artifacts + npu-events.jsonl
```

That means:

- the scripts remain the authoritative producers
- `npu-events.jsonl` remains the event bus
- the console is a renderer and orchestrator, not a second source of truth

## UX Target

Default layout:

- left: interaction log, prompt/result transcript, latest run events
- right top: KPIs
- right middle: rolling trends for NPU, CPU, CPU memory, GPU, GPU memory
- right bottom: run state, latest artifacts, mode, errors
- footer: key commands and current mode

Primary modes:

- `run`
- `watch`
- `trace`
- `endurance`
- `dashboard`

## Core Constraint

Every iteration must be self-testable.

That means each iteration must include:

- behavioral validation
- render validation
- transcript validation for what a user would actually see
- gap review and refinement before that iteration is considered complete

## UX Validation Strategy

### 1. Pure render snapshots

Make the Rich UI render from plain state objects.

Example shape:

- `build_dashboard(state) -> Renderable`
- `build_summary(state) -> Renderable`

Test by using `Console(record=True, width=<fixed>)` and exporting:

- plain text snapshots
- optional SVG snapshots for human review

Required viewport set:

- `100x30`
- `140x40`
- one narrow fallback such as `80x24`

This validates:

- wrapping
- clipping
- panel balance
- table readability
- KPI density

### 2. PTY transcript capture

Run the real CLI in a pseudo-terminal and capture the exact stream a user would see.

Store:

- raw ANSI transcript
- stripped text transcript
- terminal size metadata

This validates:

- startup messaging
- progress behavior
- redraw noise
- final screen clarity
- help output quality

### 3. Replay fixtures

Use saved `npu-events.jsonl` slices and known artifacts as replay fixtures for the dashboard.

This validates:

- deterministic rendering from real event shapes
- stability under idle, load, error, and trace-producing flows

### 4. Gap review gate

For every iteration, explicitly review:

- what looked confusing
- what wrapped badly
- what flickered too much
- what was visually redundant
- what key status was missing

Then rework within iteration scope until those issues are addressed.

## Iterative Plan

### Iteration 1. CLI foundation

Scope:

- create the packaged Rich + Typer CLI skeleton
- define command map and shared app state
- centralize config and paths
- integrate existing script runners without changing the core NPU path

Deliverables:

- packaged Python CLI under the repo
- `dashboard`, `run`, `watch`, `trace`, `endurance` command stubs
- shared settings module
- runner wrappers for the current Windows-side scripts

Acceptance:

- `--help` is coherent at top level and per command
- one obvious “golden path” command exists
- the CLI can invoke the current probes successfully

Self-tests:

- command help snapshots
- command smoke tests
- artifact path assertions

Gap review focus:

- command naming
- help text clarity
- startup latency and failure messaging

### Iteration 2. Static dashboard

Scope:

- build the full-screen Rich layout
- render fixed sample state with panels, tables, and placeholders for trends
- no live tailing yet

Deliverables:

- reusable render functions
- static full-screen dashboard command
- sample-state fixtures

Acceptance:

- dashboard is readable at the required viewport set
- no critical clipping in default views
- key KPIs are visible without scrolling

Self-tests:

- text snapshot tests at `80x24`, `100x30`, `140x40`
- optional SVG exports for manual review

Gap review focus:

- density
- panel sizing
- whether the left/right split feels natural

### Iteration 3. Live event dashboard

Scope:

- tail `npu-events.jsonl`
- show live logs and current KPIs
- add simple rolling trend renderers from in-memory samples

Deliverables:

- live dashboard mode
- event parsing and state reduction layer
- bounded in-memory trend window

Acceptance:

- new events appear predictably
- trend panels update smoothly without overwhelming redraw churn
- idle mode remains readable

Self-tests:

- replay fixtures
- PTY transcript capture of a live run
- snapshot tests for representative frames

Gap review focus:

- redraw noise
- stale data visibility
- whether logs drown out the KPIs

### Iteration 4. Orchestration controls

Scope:

- let the console launch `run`, `watch`, and `trace`
- reflect active state and produced artifacts in the same screen
- improve failure surfacing

Deliverables:

- command-driven orchestration from the CLI
- run state machine
- artifact summary region

Acceptance:

- a user can launch a real run and immediately see status, metrics, and output paths
- failures are visible without digging through raw logs

Self-tests:

- smoke tests for each command path
- PTY transcripts for success and failure cases
- replay tests with real event logs from those runs

Gap review focus:

- failure comprehension
- whether artifact paths are visible enough
- whether the UI makes run mode obvious

### Iteration 5. Endurance mode

Scope:

- add continuous repeated-run mode
- track pass/fail, latency drift, NPU utilization peaks, and memory behavior
- support stop policies

Deliverables:

- endurance runner
- endurance summary panel
- failure artifact index

Acceptance:

- repeated runs can proceed unattended
- results make reliability trends obvious
- failures are attributable to a specific run id and artifact set

Self-tests:

- simulated replay with injected failures
- shortened real endurance run
- summary snapshot tests

Gap review focus:

- whether the summary explains enough
- whether trends are visible without post-processing
- whether stop conditions are understandable

### Iteration 6. Polish and packaging

Scope:

- finalize shell completion
- refine help text
- reduce startup noise
- improve defaults and docs

Deliverables:

- polished operator command path
- minimal install/run documentation
- stable output conventions

Acceptance:

- a user can discover the main path from `--help`
- the default dashboard/run mode feels intentional
- no obvious UI friction remains in the reviewed viewport set

Self-tests:

- install/build validation
- help snapshots
- final PTY transcript review

Gap review focus:

- last-mile usability
- naming consistency
- command discoverability

## Test Harness Requirements

Build the test harness in parallel with the product.

Required harness pieces:

- render snapshot utility
- PTY transcript capture utility
- replay fixture loader for `npu-events.jsonl`
- smoke-run helpers for `run`, `watch`, and `trace`

This is non-optional. Without it, UI regressions become subjective and expensive.

## Definition Of Done Per Iteration

An iteration is done only when:

1. The scoped feature works behaviorally.
2. Snapshot outputs for the scoped UI are captured.
3. A PTY transcript of the real command path is captured.
4. Gaps found in review are either fixed or explicitly deferred.
5. The default user path is clearer than it was before the iteration.

## Initial Execution Recommendation

Start with:

1. Iteration 1: CLI foundation
2. Iteration 2: Static dashboard
3. Iteration 3: Live event dashboard

That gets the UX scaffolding in place quickly while staying close to the already-working NPU path.
