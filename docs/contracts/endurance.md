# Contract: Endurance artifact

> **Status: Accepted 2026-04-22.**
>
> Endurance artifact shape, required fields, and aggregate statistic
> definitions.
>
> **Source:** derived from [archived cleanup plan §3](../archive/2026-03-operator-console-cleanup-plan.md)
> and reconciled against `core/events.py` (`RunSummary`, `EnduranceReport`,
> `build_endurance_report`) and the artifact writer in
> `service/src/npu_service/cli.py:1056..1077`.
>
> **Cross-refs:** [ADR-010 (storage)](../decisions/ADR-010-storage-localappdata-api-mediated.md)
> — physical artifact lives under `%LOCALAPPDATA%\AeyeOps\aeo-npui\artifacts\endurance\`,
> UI reads it only through the service.
> [ADR-008](../decisions/ADR-008-service-api-http-sse.md) — endurance
> runs are kicked off via `POST /endurance` per `service-api.md`.

## 1. Purpose

Cleanup plan §3 required that an endurance summary answer three
operator questions from one screen:

1. Did it pass?
2. How stable was it?
3. Where did it go wrong (if anywhere)?

The artifact defined here is the structured record that backs the
summary view. The Rich/console renderer and the future Layer-3 UI
both render from this artifact; neither computes aggregates from
scratch.

## 2. Storage

- **Path:** `%LOCALAPPDATA%\AeyeOps\aeo-npui\artifacts\endurance\latest.json`
  for the most recent run. Historical artifacts land at
  `<artifacts>\endurance\<run_id>.json` and are never overwritten.
  (Current code writes only `latest.json`; the per-run copy is a
  planned Iteration-4 addition — the contract is written so both the
  current and planned behaviour are conformant.)
- **Format:** single JSON object, UTF-8, trailing newline.
- **Mediation:** UI retrieves the artifact via `GET /state` (which
  includes the latest summary inline) or by subscribing to
  `/events?run_id=<endurance-run-id>`. UI does not open
  `latest.json` directly; ADR-002 and ADR-010.

## 3. Artifact top-level shape

The root object carries aggregates plus a nested array of per-run
summaries.

| Field | Type | Required | Notes |
|---|---|---|---|
| `command` | string | yes | Backend command that was repeated, e.g. `"watch"`. |
| `requested_runs` | integer | yes | How many runs the operator asked for. |
| `completed_runs` | integer | yes | How many actually completed before the run ended (may be lower than requested on early termination). |
| `passed_runs` | integer | yes | Count of runs where `exit_code == 0` AND `phase_pass` is true. |
| `failed_runs` | integer | yes | `completed_runs - passed_runs`. |
| `mean_duration_seconds` | float | yes | Rounded to 3 decimals. Mean of per-run `duration_seconds`. |
| `median_duration_seconds` | float | yes | Rounded to 3 decimals. Median of per-run `duration_seconds`. |
| `p95_duration_seconds` | float | yes | Rounded to 3 decimals. Simple 95th percentile using the `ceil(n*0.95) - 1` index rule (see §4). Emitted even on tiny samples; consumers displaying it SHOULD annotate low-sample-size cases. |
| `max_duration_seconds` | float | yes | Max of per-run `duration_seconds`. |
| `overall_cpu_mem_delta_mib` | float | yes | Rounded to 1 decimal. `last_run.end_cpu_mem_used_mib - first_run.start_cpu_mem_used_mib`. Detects monotonic CPU-memory growth across the session. |
| `peak_npu_util_percent` | float | yes | Max of per-run peaks (clamped; see `metrics.md`). |
| `peak_gpu_util_percent` | float | yes | Max of per-run peaks. |
| `runs` | array of `RunSummary` | yes | Per-run records in execution order. See §5. |

## 4. Aggregate statistic definitions

These are the exact formulas as implemented in
`core/events.py:build_endurance_report`. The contract pins them so
cross-language reimplementations (TypeScript client, future
consumers) are deterministic.

- **mean**: Python `statistics.mean` on the ordered list of
  `duration_seconds`, rounded to 3 decimals.
- **median**: Python `statistics.median` on the same list, rounded to
  3 decimals. For even-length samples this is the average of the two
  middle elements.
- **p95**: the `ceil(n * 0.95) - 1` index into the sorted list, where
  `n = len(values)`. For small `n` this degenerates to the max; the
  caller MUST NOT round up separately. Reference implementation:

  ```python
  from math import ceil
  def p95(values: list[float]) -> float:
      if not values: return 0.0
      ordered = sorted(values)
      index = max(0, ceil(len(ordered) * 0.95) - 1)
      return float(ordered[index])
  ```

- **max**: `max(values)` over `duration_seconds`.
- **peak_npu_util_percent** (aggregate): `max(r.peak_npu_util_percent for r in runs)`.
- **peak_gpu_util_percent** (aggregate): `max(r.peak_gpu_util_percent for r in runs)`.
- **overall_cpu_mem_delta_mib**: `runs[-1].end_cpu_mem_used_mib - runs[0].start_cpu_mem_used_mib`, rounded to 1 decimal. Zero if `runs` is empty.
- **passed_runs**: count of runs where `exit_code == 0 AND phase_pass == true`.
- **failed_runs**: `completed_runs - passed_runs`.

Empty-run handling: all aggregates are `0.0` or `0` when `completed_runs == 0`. The artifact is still written.

## 5. `RunSummary` (one element of `runs[]`)

Each entry in the `runs` array. Fields mirror the Pydantic-equivalent
`RunSummary` dataclass in `core/events.py`.

| Field | Type | Notes |
|---|---|---|
| `run_number` | integer | 1-indexed position within the endurance session. |
| `run_id` | string | The underlying per-run `run_id` (e.g. `"watch-20260320T220638Z"`). Joins to events in `npu-events.jsonl` via `run_id`. |
| `command` | string | Backend command, e.g. `"watch"`. |
| `exit_code` | integer | Process exit code for this run. |
| `duration_seconds` | float | Wall-clock duration of this run. |
| `phase_pass` | bool | `true` if the probe reported the expected phase. |
| `peak_npu_util_percent` | float | Clamped (see `metrics.md`). |
| `peak_npu_util_raw_percent` | float | Unclamped; preserved for drift investigation. |
| `peak_gpu_util_percent` | float | |
| `peak_cpu_percent` | float | |
| `peak_cpu_mem_used_mib` | float | |
| `start_cpu_mem_used_mib` | float | For per-run delta computation. |
| `end_cpu_mem_used_mib` | float | For per-run delta computation. |
| `cpu_mem_delta_mib` | float | `end - start` for this run. |
| `npu_signal_source` | string enum | Same vocabulary as `metrics.md` §4. |
| `watch_artifact` | string \| null | Absolute Windows path to the per-run `watch-<run_id>.json`, or `null` if not applicable. |
| `probe_artifact` | string \| null | Absolute Windows path to the per-run `llm-probe-<run_id>.json`, or `null` if not applicable. |
| `trace_metadata` | string \| null | Optional path to captured trace metadata. |
| `etl_path` | string \| null | Optional path to a WPR ETL file. |

## 6. Memory-drift reporting (cleanup-plan §4)

The artifact supports distinguishing a sawtooth reuse pattern from
monotonic growth by carrying:

- **Per-run start/end/delta**: `start_cpu_mem_used_mib`,
  `end_cpu_mem_used_mib`, `cpu_mem_delta_mib` in each `RunSummary`.
- **Overall delta**: `overall_cpu_mem_delta_mib` at the root.
- **Rolling peak**: `peak_cpu_mem_used_mib` per run lets a consumer
  draw min/max envelopes without re-reading the event log.

UIs rendering the artifact SHOULD plot the per-run deltas as a
time-series; the sign and stability of the sequence is the
operator-visible answer to "is this sawtooth or monotonic?"

## 7. Failure attribution (cleanup-plan §3 acceptance)

When `failed_runs > 0`, each failing run's `RunSummary` carries
`watch_artifact` and `probe_artifact` paths. Consumers produce a
"see artifacts" link from each failing row to the files on disk
(mediated by the service, ADR-010). This satisfies the cleanup-plan
acceptance criterion: "failures are attributable to a specific run
and artifact set."

## 8. Worked example

```json
{
  "command": "watch",
  "requested_runs": 3,
  "completed_runs": 3,
  "passed_runs": 2,
  "failed_runs": 1,
  "mean_duration_seconds": 20.167,
  "median_duration_seconds": 20.5,
  "p95_duration_seconds": 22.0,
  "max_duration_seconds": 22.0,
  "overall_cpu_mem_delta_mib": 12.4,
  "peak_npu_util_percent": 91.0,
  "peak_gpu_util_percent": 0.0,
  "runs": [
    {
      "run_number": 1,
      "run_id": "watch-20260320T220638Z",
      "command": "watch",
      "exit_code": 0,
      "duration_seconds": 20.5,
      "phase_pass": true,
      "peak_npu_util_percent": 91.0,
      "peak_npu_util_raw_percent": 104.0,
      "peak_gpu_util_percent": 0.0,
      "peak_cpu_percent": 43.0,
      "peak_cpu_mem_used_mib": 38642.0,
      "start_cpu_mem_used_mib": 36675.1,
      "end_cpu_mem_used_mib": 36801.3,
      "cpu_mem_delta_mib": 126.2,
      "npu_signal_source": "gpu_engine_luid_inference",
      "watch_artifact": "C:\\dev\\npu\\artifacts\\watch\\watch-20260320T220638Z.json",
      "probe_artifact": "C:\\dev\\npu\\artifacts\\llm-probe\\llm-probe-20260320T220638Z.json",
      "trace_metadata": null,
      "etl_path": null
    }
  ]
}
```

## 9. Validation

- Unit tests: `service/tests/test_events.py::test_build_endurance_report_aggregates_runs`.
- Synthetic fixtures covering "all pass" and "one injected failure"
  per cleanup-plan §3 acceptance live under
  `service/tests/fixtures/` (to be extended in Iteration 4).
- Memory-drift coverage uses synthetic fixtures with (a) increasing
  memory and (b) oscillating memory per cleanup-plan §4 acceptance.
