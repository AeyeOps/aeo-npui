# Operator Console Cleanup Plan

## Trigger

This cleanup round is driven by real endurance output from the current NPU workflow.

Observed issues:

- the NPU metric can report values above `100%`
- the NPU metric alternates between `n/a`, `0.0%`, and active percentages without a clear semantic model
- endurance output is still shell-output-driven and interleaves spinner/progress text with backend logs
- endurance summary is too shallow for real triage and trend analysis

## Goal

Make the operator console trustworthy and readable during repeated runs.

That means:

- metric semantics are explicit and stable
- endurance mode is dashboard-native
- summaries answer the obvious operator questions without extra log digging

## Cleanup Scope

### 1. Fix NPU metric semantics

Current problem:

- values like `101%`, `102%`, `104%` appear
- `n/a` is overloaded and ambiguous

Required changes:

- clamp displayed NPU utilization to `0..100` if it remains a percent-like metric
- introduce an explicit NPU state model:
  - `unknown`
  - `idle`
  - `active`
- separate:
  - `npu_util_percent`
  - `npu_state`
  - `npu_signal_source`

Recommendation:

- if the metric is inferred from the compute-only adapter LUID, say that plainly in the event/log payload
- stop presenting inference as if it were a first-class native Windows NPU counter

Acceptance:

- no displayed NPU percent exceeds `100`
- every sample has a clear NPU state
- the UI never uses `n/a` when it actually means `idle`

Validation:

- synthetic fixture with inferred NPU values above `100`
- replay test covering `unknown`, `idle`, and `active`
- real watch run confirming clamped display and stable semantics

### 2. Make endurance dashboard-native

Current problem:

- spinner output and backend logs interleave
- the user sees a shell transcript more than a dashboard

Required changes:

- endurance should render through the same Rich dashboard path instead of printing backend logs directly
- child process output should flow into the interaction/log pane, not fight with the spinner
- one stable screen should own the run

Recommendation:

- treat endurance as a coordinator over repeated `watch`-like runs
- update dashboard state from event log plus run coordinator state
- do not print backend shell lines directly to the outer console while the dashboard is live

Acceptance:

- no interleaved spinner and backend text in endurance mode
- a user can watch the whole endurance session from one stable full-screen console
- the interaction pane still preserves useful procedural logs

Validation:

- PTY transcript of a 3-run endurance session
- human review of redraw noise and layout stability
- replay-based dashboard test for in-progress endurance state

### 3. Deepen the endurance summary

Current problem:

- summary only shows `run`, `exit`, and `seconds`

Required additions:

- run count
- pass/fail count
- mean duration
- median duration
- p95 duration if sample size supports it
- max duration
- peak NPU per run
- peak GPU per run
- CPU memory delta per run
- failure artifact path if any run fails

Recommendation:

- write a structured endurance artifact
- make the Rich summary render from that artifact/state
- keep per-run details and overall summary separate

Acceptance:

- the summary answers “did it pass, how stable was it, and where did it go wrong?” from one screen
- failures are attributable to a specific run and artifact set

Validation:

- unit tests for summary reduction
- one passing endurance run
- one injected failure case

### 4. Add explicit memory-drift reporting

Current problem:

- memory values fluctuate, but the system does not summarize drift clearly

Required additions:

- per-run start and end CPU memory
- per-run delta
- rolling min/max
- overall delta across endurance session

Acceptance:

- the operator can distinguish a sawtooth reuse pattern from monotonic growth

Validation:

- synthetic fixture with increasing memory
- synthetic fixture with oscillating memory
- real endurance output summary

### 5. Tighten event schema for metric provenance

Current problem:

- metric rows carry useful values, but provenance is not explicit enough

Required additions:

- metric provenance fields under `data`, such as:
  - `npu_signal_source`
  - `npu_luid_candidates`
  - `npu_state`
  - `metric_confidence`

Acceptance:

- a future reader can tell whether a number came from a native counter, inferred adapter activity, or absence of signal

Validation:

- schema update
- event row tests
- replay tests against old and new event shapes if backward compatibility is required

## Execution Order

1. NPU metric semantics and provenance
2. Endurance dashboard-native rendering
3. Endurance summary deepening
4. Memory-drift reporting
5. Final PTY transcript review and cleanup pass

## Definition Of Done

This cleanup round is complete only when:

1. NPU metric semantics are explicit and no displayed percent exceeds `100`
2. Endurance mode runs in one stable dashboard without noisy spinner/backend interleaving
3. Endurance summary includes reliability and drift metrics, not just duration rows
4. Validation passes for unit tests, replay tests, and real runs
5. The resulting UX is clearer than the current shell-transcript-heavy behavior
