# Contract: Metrics (NPU state model + clamping)

> **Status: Accepted 2026-04-22.**
>
> NPU state model (`unknown` / `idle` / `active`), clamping rules,
> signal-source enumeration, and the split between the three
> observable fields.
>
> **Source:** derived from [archived cleanup plan §1 and §4](../archive/2026-03-operator-console-cleanup-plan.md)
> and reconciled against `core/events.py` and the fixture
> `tests/fixtures/events_sample.jsonl`.
>
> **Cross-refs:** [`events.md` §6.1](./events.md#61-metricsample-kind--metric)
> defines the wire shape; this document defines the semantics and
> clamping rules applied before the wire is hit.
> [ADR-008](../decisions/ADR-008-service-api-http-sse.md) surfaces metrics
> via `GET /metrics` SSE.

## 1. Why this document exists

The cleanup plan §1 observed three failure modes in the shipped
operator console:

1. NPU utilization displayed values above `100%` (fixture shows a raw
   reading of `104.0`).
2. `"n/a"` was overloaded and ambiguous — it meant both "no signal at
   all" and "the signal reads zero" and "the session hasn't started a
   turn yet." Operators could not tell the three apart.
3. The metric was inferred from the compute-only adapter LUID, but
   nothing in the log said so — operators assumed a native counter.

This contract pins the fix: three separate fields, clamping on the
display value, and an explicit state enumeration.

## 2. The three-field split

Every `metric.sample` row in `npu-events.jsonl` carries these three
fields together (never one without the others):

| Field | Type | Range | Role |
|---|---|---|---|
| `npu_util_percent` | float | **clamped to `[0.0, 100.0]`** | The percent the UI displays. |
| `npu_state` | string enum | see §3 | The semantic state the UI shows next to the percent. |
| `npu_signal_source` | string enum | see §4 | The provenance tag the UI shows in the "About this metric" detail panel. |

A fourth field, `npu_util_raw_percent`, carries the unclamped reading
for debugging only. The UI MUST NOT display it as a first-class
number; it is available via the full event envelope for operators
who want to see counter drift.

## 3. `npu_state` enumeration

| State | When | Operator meaning |
|---|---|---|
| `"unknown"` | No signal has been observed yet, OR the compute-only LUID has not appeared among observed LUIDs, OR the provenance source could not be determined. | "We cannot say whether the NPU is working." |
| `"idle"` | Signal is observed and `npu_util_percent` reads `0.0` (or below a producer-defined idle floor). | "The NPU is present and reachable but not running a workload right now." |
| `"active"` | Signal is observed and `npu_util_percent > 0.0`. | "The NPU is running a workload." |

Rules:

- `"unknown"` is the default at the start of a run before the first
  sample is evaluated.
- A sample with `npu_util_percent == 0.0` AND an observed LUID MUST
  be emitted as `"idle"`, never `"unknown"`. This directly addresses
  cleanup-plan §1's "stop presenting inference as if it were a
  first-class native Windows NPU counter, and stop using `n/a` when
  the signal is actually `idle`."
- A sample with `npu_util_percent > 0.0` MUST be emitted as
  `"active"`.
- Transitions are per-sample; the state is not sticky. A stream of
  samples alternating `idle`/`active`/`idle` is valid.

The live dashboard layer in `core/events.py:268` applies a cosmetic
gloss ("idle (last turn active, peak 91%)") when the current sample
is `idle` but the run's latest summary shows peak activity. That gloss
is a UI detail, not a contract field — consumers relying on the
structured state MUST read `npu_state` directly.

## 4. `npu_signal_source` enumeration

| Value | Meaning | Appears when |
|---|---|---|
| `"native_npu_counter"` | First-class Windows NPU counter reading. | Reserved for a future path. Not currently emitted by `watch_llm_probe.ps1`. |
| `"gpu_engine_luid_inference"` | Inferred from `GPU Engine` counter activity on the compute-only adapter LUID. | **Current production path.** Fixture always shows this value. |
| `"unspecified"` | Provenance could not be determined for this sample. | Defensive default; readers SHOULD treat the sample's NPU fields as low-confidence and SHOULD prefer `npu_state = "unknown"` unless a subsequent sample supplies a concrete source. |

The `metric_confidence` field on the same event classifies the source
orthogonally as `"native"` / `"inferred"` / `"absent"`. The two are
redundant by design: `metric_confidence` is cheap to key in a UI pill,
`npu_signal_source` is the precise lookup.

## 5. Clamping rules for `npu_util_percent`

Producers MUST compute clamping as follows:

```
npu_util_percent = max(0.0, min(100.0, npu_util_raw_percent))
```

Concretely: a raw reading of `104.0` becomes `100.0` on the wire. A
raw reading of `-0.3` becomes `0.0`. The fixture preserves the pair
`{npu_util_percent: 0.0, npu_util_raw_percent: 104.0}` for the first
metric sample — the raw is nonzero because the LUID is observed, but
no inference work is active yet.

**Peak aggregation** in summary events follows the same rule: the
`peak_npu_util_percent` field in a `watch.summary` payload is the
maximum of the clamped per-sample values. `peak_npu_util_raw_percent`
is the maximum of the raw values. Downstream consumers (endurance
aggregator, run summary) use the clamped field.

The clamp is applied **once, by the producer**. Readers MUST NOT
re-clamp or adjust the received value; doing so would double-adjust
if the producer is upgraded to a native counter that legitimately
reports `0..100` without a raw/clamped split.

## 6. Acceptance (from cleanup-plan §1)

- No displayed NPU percent exceeds `100`. ✓ via §5.
- Every sample has a clear NPU state. ✓ via §3.
- The UI never uses `"n/a"` when it actually means `"idle"`. ✓ via §3.

## 7. Validation fixtures

- `service/tests/fixtures/events_sample.jsonl` exercises all three
  states across two metric samples plus one summary.
- Unit tests covering the state transitions live in
  `service/tests/test_events.py`.
- Cross-reference: `metric.sample` wire shape in
  [`events.md` §6.1](./events.md#61-metricsample-kind--metric).
