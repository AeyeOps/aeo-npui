# Operator Console E2E Recovery Plan

## Decision

Switch operator-console validation to E2E-first.

Do not trust unit or snapshot tests as a release gate for interactive delivery.

Use E2E validation as the primary gate for:

- dashboard startup
- live repaint stability
- typing fidelity
- chat turn correctness
- log view behavior
- follow mode behavior
- endurance behavior
- direct Windows `pwsh.exe` usability

## Problem Statement

Recent regressions escaped despite passing local tests:

- startup crashed in the real dashboard path
- live dashboard repaint glitched
- typing dropped characters
- prompt/response mismatches reached the user
- interaction semantics drifted away from user expectations

This means the current validation strategy is insufficient as a delivery gate.

## Overarching Acceptance

The console is not considered fixed until all of the following pass through E2E execution:

1. Dashboard starts from Windows `pwsh.exe` with no crash.
2. Typing in the live dashboard does not drop characters.
3. Chat responses correspond to the actual user prompt.
4. `/clear` resets the conversation.
5. `/view log` works, scrolls, and respects follow semantics.
6. Endurance runs in a stable full-screen dashboard.
7. The user remains in the original working directory after the launcher returns.

## E2E Matrix

### E2E-1. Dashboard startup

Environment:

- Windows `pwsh.exe`
- current directory: `C:\dev\npu`

Command:

```powershell
.\scripts\npu-console.ps1 dashboard
```

Pass:

- first frame appears
- no traceback
- visible system startup message appears while loading
- dashboard reaches ready state

Artifacts:

- PTY transcript
- screenshot or text capture of first frame

### E2E-2. Typing fidelity

Scenario:

- user types a known string with alternating characters, e.g. `abcdefghij`

Pass:

- input buffer shows the exact typed string
- no dropped or doubled characters

Artifacts:

- PTY transcript
- explicit typed string assertion from capture

### E2E-3. Single-turn chat correctness

Scenario:

- type `hi`

Pass:

- event log shows the real user prompt
- response is generated from that turn’s run artifact
- no stale artifact is used

Artifacts:

- `npu-events.jsonl`
- watch artifact
- llm artifact
- PTY transcript

### E2E-4. Multi-turn continuity

Scenario:

- turn 1: `hello`
- turn 2: `what did I just say?`

Pass:

- second prompt includes conversation history
- response is based on prior turns
- same persistent session remains active across turns

Artifacts:

- event log
- worker/session state capture
- PTY transcript

### E2E-5. Clear semantics

Scenario:

- chat for at least two turns
- issue `/clear`
- send a new prompt

Pass:

- transcript resets to initial state
- prior turn does not leak into the new prompt
- any in-flight result after clear is ignored

Artifacts:

- event log
- PTY transcript

### E2E-6. Log view behavior

Scenario:

- switch to `/view log`
- scroll with up/down and page keys
- toggle follow with `f`
- scroll while following

Pass:

- log panel replaces chat panel
- scrolling works
- follow mode turns off when the user scrolls
- `f` toggles follow back on
- new incoming rows do not move the viewport while follow is off

Artifacts:

- PTY transcript
- event log

### E2E-7. Endurance operator flow

Scenario:

- run:

```powershell
.\scripts\npu-console.ps1 endurance --runs 3 --command watch
```

Pass:

- full-screen dashboard remains stable
- no spinner/backend interleaving
- final summary appears with aggregate stats
- structured endurance artifact is written

Artifacts:

- PTY transcript
- endurance artifact

### E2E-8. Launcher working directory

Scenario:

- run launcher from `C:\dev\npu`
- exit

Pass:

- user remains in original directory

Artifacts:

- transcript or explicit `Get-Location` capture before/after

## Required Harness

Build or keep only what supports E2E delivery:

- Windows-side PTY transcript runner
- scripted keystroke feeder for the dashboard
- artifact collector for:
  - `npu-events.jsonl`
  - watch artifact
  - llm artifact
  - endurance artifact
  - stderr/stdout logs

Keep unit tests only as developer aids. Do not treat them as sufficient for release.

## Iterative Recovery Order

1. Stabilize dashboard startup and typing fidelity.
2. Fix prompt/response correctness and continuity.
3. Fix `/clear` and `/view log` behavior.
4. Fix endurance dashboard flow.
5. Run the full E2E matrix from Windows `pwsh.exe`.

Do not advance to the next item until the current item passes its E2E scenario.

## Release Gate

Before claiming delivery:

- run the full E2E matrix
- review the transcripts and artifacts
- reject release if any interactive scenario fails, even if local tests pass
