# Contract: Events (npu-events.jsonl)

> **Status: Accepted 2026-04-22.**
>
> JSONL schema for `npu-events.jsonl`, all event kinds, and the
> `data.metric_provenance` fields.
>
> **Source:** derived from [archived cleanup plan §5](../archive/2026-03-operator-console-cleanup-plan.md)
> and reconciled against the shipped event writer in
> `service/src/npu_service/core/events.py` plus the canonical fixture at
> `service/tests/fixtures/events_sample.jsonl`.
>
> **Cross-refs:** [ADR-008 (HTTP + SSE)](../decisions/ADR-008-service-api-http-sse.md)
> — events are surfaced via `GET /events` (SSE) per `service-api.md`.
> [ADR-010 (storage)](../decisions/ADR-010-storage-localappdata-api-mediated.md)
> — physical file lives in `%LOCALAPPDATA%\AeyeOps\aeo-npui\events\npu-events.jsonl`
> on Windows; WSL-side access is via the service, not direct read.
> [ADR-002 (UI is Layer-1 client only)](../decisions/ADR-002-ui-is-service-client-only.md)
> — the UI never opens this file directly; it consumes SSE and typed REST responses.

## 1. Transport

- **File format:** newline-delimited JSON (JSONL). One event per line.
  Each line is a self-contained JSON object parseable with
  `json.loads`.
- **Encoding:** UTF-8.
- **Path:** `%LOCALAPPDATA%\AeyeOps\aeo-npui\events\npu-events.jsonl`
  (per ADR-010). The current code (`core/settings.py`) resolves this as
  `wsl_root / scripts / npu-events.jsonl` when reading from WSL; the
  path-resolution rule is an implementation detail of the launcher, not
  part of this contract.
- **Append-only:** events are never edited or deleted in place. Readers
  may safely tail the file; writers never rewind.
- **Ordering:** events are monotonically ordered by `seq`. The `ts`
  field is a best-effort UTC timestamp but `seq` is the authoritative
  sort key when two events share the same wall-clock instant.

## 2. Top-level envelope

Every event row is an object with these fields:

| Field | Type | Required | Notes |
|---|---|---|---|
| `schema` | string | yes | Version tag. Currently `"npu.event.v1"`. Readers MUST check this and MUST NOT silently consume a version they don't understand. |
| `ts` | string (RFC 3339, UTC, `Z` suffix) | yes | Producer wall-clock time. Example: `"2026-03-20T22:06:51.8555184Z"`. |
| `run_id` | string | yes | Stable identifier for one logical run. Format: `<command>-<YYYYMMDDTHHMMSSZ>`, e.g. `"watch-20260320T220638Z"` or `"chat-20260421T093012Z"`. |
| `seq` | integer | yes | Monotonic sequence within the file. Used as SSE `id:` value by `GET /events`. |
| `kind` | string enum | yes | See §3. |
| `level` | string enum | yes | One of `"DEBUG"`, `"INFO"`, `"WARN"`, `"ERROR"`. |
| `module` | string | yes | Emitter name, e.g. `"watch_llm_probe"`, `"monitor_npu_worker"`, `"npu_service"`. |
| `event` | string | yes | Dotted event name, e.g. `"metric.sample"`, `"watch.summary"`, `"watch.start"`. |
| `message` | string | yes | Human-readable one-liner. Not parsed. |
| `host` | object | yes | See §4. |
| `proc` | object | yes | See §5. |
| `data` | object | yes | Event-type-specific payload. See §6. |

## 3. Event `kind` enumeration

The `kind` field coarsely classifies events. The more specific `event`
field names the exact occurrence.

| `kind` | Meaning | Example `event` names |
|---|---|---|
| `"lifecycle"` | Run-boundary markers. | `watch.start`, `chat.start`, `endurance.start`, `endurance.run.start`, `endurance.run.complete`, `endurance.complete` |
| `"metric"` | Periodic resource sample. | `metric.sample` |
| `"summary"` | End-of-run structured summary. | `watch.summary`, `chat.summary`, `endurance.summary` |
| `"log"` | Free-form informational line. | `backend.stdout`, `backend.stderr`, `service.info` |
| `"error"` | Recoverable error inside a run. | `probe.error`, `chat.error` |

Readers MUST treat unknown `kind` values as `"log"`.

## 4. `host` sub-object

Describes the machine that produced the event. Captured once per
writer boot; repeated on every row for self-describing transport.

| Field | Type | Notes |
|---|---|---|
| `hostname` | string | e.g. `"DESKTOP-EXAMPLE1"` |
| `host_model` | string | e.g. `"Example Laptop 14"` |
| `host_manufacturer` | string | e.g. `"Dell Inc."` |
| `os_caption` | string | e.g. `"Microsoft Windows 11 Pro"` |
| `os_version` | string | e.g. `"10.0.26200"` |
| `os_build` | string | e.g. `"26200"` |

## 5. `proc` sub-object

| Field | Type | Notes |
|---|---|---|
| `pid` | integer | Producer process id. |
| `process` | string | Image name, e.g. `"pwsh"`, `"python"`. |
| `thread` | integer | Producer thread id. |

## 6. `data` payloads by event

### 6.1 `metric.sample` (`kind = "metric"`)

Periodic resource sample. This is the row the dashboard and SSE clients
render live. Fields:

**Core resource counters:**

| Field | Type | Clamped? | Notes |
|---|---|---|---|
| `cpu_percent` | float | 0..100 | System CPU utilization. |
| `cpu_mem_used_mib` | float | ≥0 | Working-set RSS in MiB. |
| `cpu_mem_avail_mib` | float | ≥0 | Available system memory in MiB. |
| `process_working_set_mib` | float | ≥0 | Probe-process RSS in MiB. |
| `gpu_util_percent` | float | 0..100 | Aggregate GPU utilization (discrete GPU, not NPU). |
| `gpu_mem_mib` | float | ≥0 | GPU memory in MiB. |
| `npu_mem_mib` | float | ≥0 | NPU memory in MiB. |

**NPU-specific, with provenance (per cleanup-plan §5):**

| Field | Type | Notes |
|---|---|---|
| `npu_util_percent` | float | **Clamped to `0..100`** per `metrics.md`. This is the value the UI shows. |
| `npu_util_raw_percent` | float | Unclamped raw counter value (fixture shows `104.0`). Preserved for debugging the clamp; UI MUST NOT display it as a first-class number. |
| `npu_state` | string enum | `"unknown"` \| `"idle"` \| `"active"`. See `metrics.md`. |
| `npu_signal_source` | string enum | Provenance tag. See §6.1.1. |
| `metric_confidence` | string enum | `"native"` \| `"inferred"` \| `"absent"`. `"inferred"` means the number came from the compute-only adapter LUID, not a native NPU counter. |
| `npu_luid_candidates` | array of string | Candidate adapter LUIDs hex-encoded, e.g. `["00017F20"]`. |
| `observed_npu_luids` | array of string | Subset of candidates actually observed this sample. |
| `observed_luids` | array of string | All adapter LUIDs this sample saw, e.g. `["000168BF","00016D74","00017F20"]`. |

#### 6.1.1 `npu_signal_source` enumeration

| Value | Meaning |
|---|---|
| `"native_npu_counter"` | Reserved for a future first-class Windows NPU counter. Not currently emitted. |
| `"gpu_engine_luid_inference"` | Inferred from `GPU Engine` counter activity on a compute-only adapter LUID. **This is the current production path** — the number is an inference, not a direct reading. |
| `"unspecified"` | Default when provenance could not be determined. Readers should treat the sample's NPU fields as low-confidence. |

Provenance tags reflect cleanup-plan §1's recommendation: "if the metric
is inferred from the compute-only adapter LUID, say that plainly in
the event/log payload."

### 6.2 `watch.summary` / `chat.summary` (`kind = "summary"`)

End-of-run aggregate emitted by a probe wrapper. Fields (from the
fixture; canonical list):

| Field | Type | Notes |
|---|---|---|
| `probe_phase_pass` | bool | `true` if the probe reported the expected phase. |
| `probe_exit_code` | integer | Underlying process exit code. |
| `probe_artifact` | string (Windows path) | Absolute path to the per-run `llm-probe-<run_id>.json`. |
| `watch_artifact` | string (Windows path) | Absolute path to the per-run `watch-<run_id>.json`. |
| `peak_cpu_percent` | float | |
| `peak_cpu_mem_used_mib` | float | |
| `peak_gpu_util_percent` | float | |
| `peak_gpu_mem_mib` | float | |
| `peak_npu_util_percent` | float | Clamped. |
| `peak_npu_util_raw_percent` | float | Raw. |
| `start_cpu_mem_used_mib` | float | For drift computation. |
| `end_cpu_mem_used_mib` | float | For drift computation. |
| `cpu_mem_delta_mib` | float | `end - start`. |
| `npu_signal_source` | string enum | Same vocabulary as §6.1.1. |
| `npu_luid_candidates` | array of string | LUIDs that contributed to NPU estimates in this run. |

Optional extras (present on some runs):

| Field | Type | Notes |
|---|---|---|
| `trace_metadata` | string | Path to a captured trace file. |
| `etl_path` | string | Path to an ETL file if the run wrapped a WPR capture. |

### 6.3 `watch.start` / `chat.start` / `endurance.start` (`kind = "lifecycle"`)

Run-boundary marker emitted as the first event of a run. Fields vary
by producer; at minimum:

| Field | Type | Notes |
|---|---|---|
| `sample_interval_s` | float | Planned metric sample period (for `watch.start`). |
| `prompt` | string | Prompt sent to the model (for chat/watch runs). |
| `root_dir` | string | Root directory of the producer. |

Endurance lifecycle events (`endurance.run.start` / `endurance.run.complete`)
carry `run_number` and `duration_seconds` in `data`; see `endurance.md` §3.

### 6.4 `backend.stdout` / `backend.stderr` (`kind = "log"`)

Free-form line capture. `data.line` holds the raw line.

### 6.5 `*.error` (`kind = "error"`)

`data` carries at least `exc_type`, `exc_message`, and (where
available) `traceback` as a single string. Consumers MUST be tolerant
of additional fields being added.

## 7. Backward compatibility

- The `schema` field is the version gate. Bumping from `v1` to `v2`
  requires either a dual-publish period or a coordinator migration
  step; the SSE stream advertises only the latest schema it's
  producing, so old clients fail fast.
- New fields may be added within `data` at any time. Clients MUST
  ignore unknown fields.
- Renaming or removing a field is a breaking change and requires a
  schema bump.
