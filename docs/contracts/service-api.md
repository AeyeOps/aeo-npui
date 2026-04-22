# Contract: Service API (HTTP + SSE)

> **Status: Accepted 2026-04-22.**
>
> The keystone Layer-1 contract. Defines the HTTP routes, SSE streams,
> and request/response schemas that the desktop UI uses to drive the
> NPU service.
>
> **Cross-refs:**
> - [ADR-008 (HTTP + SSE via FastAPI)](../decisions/ADR-008-service-api-http-sse.md) — decision rationale.
> - [ADR-002 (UI is Layer-1 client only)](../decisions/ADR-002-ui-is-service-client-only.md) — the UI never bypasses this contract.
> - [ADR-010 (storage in `%LOCALAPPDATA%\AeyeOps\aeo-npui\`, API-mediated)](../decisions/ADR-010-storage-localappdata-api-mediated.md) — events and artifacts are file-backed but accessed through this API, never via direct filesystem reads.
> - [`events.md`](./events.md) — SSE event payloads.
> - [`metrics.md`](./metrics.md) — metric semantics and clamping.
> - [`endurance.md`](./endurance.md) — endurance artifact shape.

## 1. Transport

- **Base URL:** `http://127.0.0.1:<port>`. Default port is `8765`.
  The UI loads this from `tauri.conf.json` CSP (ADR-004 binds
  `connect-src` to the exact port at build time).
- **Binding:** loopback only. The service MUST NOT bind any other
  interface; there is no authentication in Layer 1.
- **CORS:** `*` during development; tightened to the Tauri origin in
  production builds. The current implementation (`web_api.py:321`)
  uses `allow_origins=["*"]` as a baseline.
- **Content-type:** `application/json` for request/response bodies
  (not matrix-varied). SSE endpoints emit `text/event-stream`.
- **Auth:** none. The loopback binding is the trust boundary.
- **Errors:** 4xx for client errors with JSON body
  `{"error": "<code>", "message": "<human-readable>"}`. 5xx for
  service errors with the same shape.

## 2. Pydantic models (canonical)

The following Pydantic model names are the canonical source of truth
for request/response shapes. TypeScript types are generated from them
(Iteration 4). Models live in `service/src/npu_service/models.py`
once Iteration 4 completes the restructure; **names marked "proposed
in Iteration 4"** are forward references — Subagent W introduces
them when `web_api.py` becomes `api.py`.

| Pydantic model | File | Role |
|---|---|---|
| `ServiceState` | `models.py` (proposed in Iteration 4) | Response of `GET /state`. |
| `InferenceRequest` | `models.py` (proposed in Iteration 4) | Body of `POST /inference`. |
| `InferenceResponse` | `models.py` (proposed in Iteration 4) | Response of `POST /inference`. |
| `EnduranceRequest` | `models.py` (proposed in Iteration 4) | Body of `POST /endurance`. |
| `EnduranceResponse` | `models.py` (proposed in Iteration 4) | Response of `POST /endurance`. |
| `ModelInfo` | `models.py` (proposed in Iteration 4) | Element of `GET /models`. |
| `HealthResponse` | `models.py` (proposed in Iteration 4) | Response of `GET /health`. |
| `EventEnvelope` | `models.py` (proposed in Iteration 4) | Shape of SSE `data:` on `/events`. Mirrors [`events.md` §2](./events.md). |
| `MetricSample` | `models.py` (proposed in Iteration 4) | Shape of SSE `data:` on `/metrics`. Mirrors [`events.md` §6.1](./events.md#61-metricsample-kind--metric). |
| `ChatInputRequest` | `web_api.py` (exists today) | Body of the legacy `POST /api/chat/send`. Retained in transition. |

## 3. Endpoint summary

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/state` | Service state, active model, current session id. |
| `POST` | `/inference` | Submit a prompt; returns SSE URLs for this run. |
| `GET` | `/events` | SSE stream of all event kinds for one run (or all runs). |
| `GET` | `/metrics` | SSE stream of metric samples. |
| `POST` | `/endurance` | Kick off an endurance run; returns SSE URL + artifact path. |
| `GET` | `/models` | List models available to the NPU runtime. |
| `GET` | `/health` | Liveness + readiness. |
| `POST` | `/session/clear` | Reset the conversation. |

## 4. `GET /state`

Return the current service state. Called on desktop app open and on
reconnect. Non-streaming.

**Response** (`ServiceState`):

```json
{
  "startup_state": "starting | ready | failed | idle | stopped",
  "session_run_id": "chat-20260421T093012Z | null",
  "active_model": "OpenVINO/TinyLlama-1.1B-Chat-v1.0-int4-ov | null",
  "last_status_line": "Ready",
  "last_help_line": "Type a message and press Enter",
  "system_message": "Loading TinyLlama on the local Intel NPU... | null"
}
```

Implementation: today's `/api/state` in `web_api.py:331` returns a
superset of these fields (dashboard snapshot, messages, log lines);
Iteration 4.1 trims the response to match this contract via
`build_api_snapshot` and retires the TUI-coupled fields.

## 5. `POST /inference`

Submit a prompt. The response is **discoverability metadata** — it
tells the UI where to open SSE streams for this run, not the
inference output itself.

**Request** (`InferenceRequest`):

```json
{
  "prompt": "Reply with the single word working.",
  "run_id": "chat-20260421T093012Z | null"
}
```

- `prompt` (string, required): the user prompt.
- `run_id` (string, optional): bind this inference to an existing
  chat session. If omitted, the service opens a new run and returns
  its id.

**Response** (`InferenceResponse`):

```json
{
  "run_id": "chat-20260421T093012Z",
  "events_url": "/events?run_id=chat-20260421T093012Z&since=0",
  "metrics_url": "/metrics?run_id=chat-20260421T093012Z&since=0"
}
```

- `events_url` and `metrics_url` are **server-constructed relative
  paths**. The UI opens them directly as an `EventSource`:

  ```ts
  const es = new EventSource(`http://127.0.0.1:8765${response.events_url}`);
  ```

- **Clients MUST NOT synthesize `events_url` or `metrics_url` from
  `run_id` themselves.** The contract owner reserves the right to
  change the query shape, add auth tokens, or route to a different
  host; the discoverability metadata is the escape hatch that lets
  the server evolve without breaking clients.

- Clients MAY parse the URLs to extract `run_id` for display.
  Clients MUST NOT rewrite them.

## 6. `GET /events`

SSE stream of every event in `npu-events.jsonl` for one run (or all
runs). Event payloads match [`events.md`](./events.md).

**Query parameters:**

| Parameter | Type | Notes |
|---|---|---|
| `run_id` | string, optional | When set, the stream is filtered to events with this `run_id`. When omitted, the stream is the full firehose (operator view). |
| `since` | integer, optional | Monotonic event `seq` (§4.6 of `events.md`). When set, the stream begins with the first event where `seq > since`. Default `0` (from the start). |

**SSE framing:**

- `id:` — set to the event's `seq`. Resuming a dropped connection
  uses the client's last received `id:` value — this is the standard
  SSE `Last-Event-ID` header semantic. Clients MUST honor it on
  reconnect.
- `event:` — set to the event's `event` field (e.g. `metric.sample`,
  `watch.summary`, `watch.start`).
- `data:` — a JSON-serialized `EventEnvelope` matching
  [`events.md` §2](./events.md#2-top-level-envelope).

**Connection lifecycle:**

- The server sends a comment line `: keepalive\n\n` at least every
  30 seconds to keep proxies and browsers from timing out.
- The server closes the connection when the run completes (signaled
  by a `*.summary` event with matching `run_id`) ONLY if
  `run_id` is set. When `run_id` is omitted, the stream is
  long-lived across runs.

## 7. `GET /metrics`

SSE stream of only metric samples for one run. Equivalent to
`/events?run_id=...` filtered to `event == "metric.sample"`, but the
framing is optimized for dashboard clients and the `since` parameter
is a **unix-ms timestamp** rather than a sequence number.

**Query parameters:**

| Parameter | Type | Notes |
|---|---|---|
| `run_id` | string, optional | Same semantics as `/events`. |
| `since` | integer, optional | Unix milliseconds. The stream begins with the first metric sample whose `ts` converts to a wall-clock instant strictly greater than `since`. Default `0`. |

**SSE framing:**

- `id:` — the sample's unix-ms timestamp. Used for reconnect.
- `event:` — the literal string `"metric.sample"`.
- `data:` — a JSON-serialized `MetricSample` matching
  [`events.md` §6.1](./events.md#61-metricsample-kind--metric).

## 8. `POST /endurance`

Kick off an endurance run. Returns discoverability metadata plus the
artifact path the UI can poll.

**Request** (`EnduranceRequest`):

```json
{
  "command": "watch",
  "runs": 3,
  "stop_on_failure": true
}
```

- `command` (string, required): backend command to repeat
  (`"watch"`, `"trace"`, etc.).
- `runs` (integer, required, `>= 1`): how many iterations.
- `stop_on_failure` (bool, optional, default `true`): short-circuit
  on the first failing run.

**Response** (`EnduranceResponse`):

```json
{
  "run_id": "endurance-20260421T093012Z",
  "artifact_path": "C:\\Users\\steve\\AppData\\Local\\AeyeOps\\aeo-npui\\artifacts\\endurance\\latest.json",
  "events_url": "/events?run_id=endurance-20260421T093012Z&since=0"
}
```

- Same discoverability rule as `/inference`: clients MUST NOT
  synthesize `events_url` from `run_id`.
- `artifact_path` is an **absolute path on the host filesystem**. UIs
  SHOULD display this path read-only and SHOULD NOT attempt to open
  it directly — they fetch the artifact contents via
  `GET /state` (which includes the latest summary inline) or via the
  SSE `*.summary` event.

## 9. `GET /models`

List models available to the NPU runtime. Non-streaming.

**Response:** array of `ModelInfo`.

```json
[
  {
    "id": "OpenVINO/TinyLlama-1.1B-Chat-v1.0-int4-ov",
    "display_name": "TinyLlama 1.1B Chat (int4)",
    "active": true,
    "size_mib": 712.4
  }
]
```

## 10. `GET /health`

Liveness and readiness. Distinguishes the two explicitly.

**Response** (`HealthResponse`):

```json
{
  "status": "ok | degraded | starting | failed",
  "liveness": true,
  "readiness": false,
  "detail": "Loading TinyLlama on the local Intel NPU..."
}
```

- `liveness` is `true` if the process is running and the HTTP stack
  is serving requests. It says nothing about the NPU.
- `readiness` is `true` only when `liveness` is `true` AND the NPU
  session has completed startup AND no fatal startup error is
  recorded.
- `status` is derived:
  - `"starting"` when `liveness && !readiness` and no error.
  - `"failed"` when `liveness` and the session has a startup error.
  - `"degraded"` when `liveness && readiness` but the most recent
    turn failed.
  - `"ok"` when `liveness && readiness` and the most recent turn (if
    any) passed.
- `detail` is a human-readable one-liner. May be empty when
  `status == "ok"`.

`/health` is a **cheap** check. Kubernetes-style probes, the Tauri
autostart check (ADR-008 §§2.3), and the UI's health dot all hit this
endpoint. It MUST NOT block on NPU warm-up.

## 11. `POST /session/clear`

Reset the conversation. Idempotent; safe to call when no session is
active. Returns the new `ServiceState` (§4).

**Request body:** empty object `{}`.

**Response:** `ServiceState`.

## 12. OpenAPI-compatible schema sketch

This YAML fragment is **authoritative for the route shape**; the
Pydantic models in `service/src/npu_service/models.py` (once
Iteration 4 lands) are the source of truth for field-level types.
Iteration 4 publishes this as `/openapi.json` via FastAPI's built-in
generator.

```yaml
openapi: 3.1.0
info:
  title: AEO NPUi Service API
  version: 0.1.0
  license:
    name: MIT
servers:
  - url: http://127.0.0.1:8765
paths:
  /state:
    get:
      summary: Get service state
      responses:
        '200':
          description: Current state
          content:
            application/json:
              schema: {$ref: '#/components/schemas/ServiceState'}
  /inference:
    post:
      summary: Submit a prompt
      requestBody:
        required: true
        content:
          application/json:
            schema: {$ref: '#/components/schemas/InferenceRequest'}
      responses:
        '200':
          description: Run discovery metadata
          content:
            application/json:
              schema: {$ref: '#/components/schemas/InferenceResponse'}
  /events:
    get:
      summary: SSE stream of events for one run (or all runs)
      parameters:
        - {in: query, name: run_id, required: false, schema: {type: string}}
        - {in: query, name: since, required: false, schema: {type: integer, default: 0}}
      responses:
        '200':
          description: SSE stream
          content:
            text/event-stream:
              schema: {$ref: '#/components/schemas/EventEnvelope'}
  /metrics:
    get:
      summary: SSE stream of metric samples
      parameters:
        - {in: query, name: run_id, required: false, schema: {type: string}}
        - {in: query, name: since, required: false, schema: {type: integer, default: 0, description: "unix-ms timestamp"}}
      responses:
        '200':
          description: SSE stream
          content:
            text/event-stream:
              schema: {$ref: '#/components/schemas/MetricSample'}
  /endurance:
    post:
      summary: Kick off an endurance run
      requestBody:
        required: true
        content:
          application/json:
            schema: {$ref: '#/components/schemas/EnduranceRequest'}
      responses:
        '200':
          description: Run discovery metadata + artifact path
          content:
            application/json:
              schema: {$ref: '#/components/schemas/EnduranceResponse'}
  /models:
    get:
      summary: List models available to the NPU
      responses:
        '200':
          description: Model list
          content:
            application/json:
              schema:
                type: array
                items: {$ref: '#/components/schemas/ModelInfo'}
  /health:
    get:
      summary: Liveness + readiness
      responses:
        '200':
          description: Health response
          content:
            application/json:
              schema: {$ref: '#/components/schemas/HealthResponse'}
  /session/clear:
    post:
      summary: Reset the conversation
      requestBody:
        required: false
        content:
          application/json:
            schema: {type: object}
      responses:
        '200':
          description: New service state
          content:
            application/json:
              schema: {$ref: '#/components/schemas/ServiceState'}
components:
  schemas:
    ServiceState:
      type: object
      required: [startup_state, last_status_line, last_help_line]
      properties:
        startup_state: {type: string, enum: [starting, ready, failed, idle, stopped]}
        session_run_id: {type: string, nullable: true}
        active_model: {type: string, nullable: true}
        last_status_line: {type: string}
        last_help_line: {type: string}
        system_message: {type: string, nullable: true}
    InferenceRequest:
      type: object
      required: [prompt]
      properties:
        prompt: {type: string, minLength: 1}
        run_id: {type: string, nullable: true}
    InferenceResponse:
      type: object
      required: [run_id, events_url, metrics_url]
      properties:
        run_id: {type: string}
        events_url: {type: string, description: "server-constructed; clients MUST NOT synthesize"}
        metrics_url: {type: string, description: "server-constructed; clients MUST NOT synthesize"}
    EnduranceRequest:
      type: object
      required: [command, runs]
      properties:
        command: {type: string}
        runs: {type: integer, minimum: 1}
        stop_on_failure: {type: boolean, default: true}
    EnduranceResponse:
      type: object
      required: [run_id, artifact_path, events_url]
      properties:
        run_id: {type: string}
        artifact_path: {type: string, description: "absolute host path, read-only to the UI"}
        events_url: {type: string, description: "server-constructed; clients MUST NOT synthesize"}
    ModelInfo:
      type: object
      required: [id, display_name, active]
      properties:
        id: {type: string}
        display_name: {type: string}
        active: {type: boolean}
        size_mib: {type: number}
    HealthResponse:
      type: object
      required: [status, liveness, readiness]
      properties:
        status: {type: string, enum: [ok, degraded, starting, failed]}
        liveness: {type: boolean}
        readiness: {type: boolean}
        detail: {type: string, nullable: true}
    EventEnvelope:
      type: object
      required: [schema, ts, run_id, seq, kind, level, module, event, message, host, proc, data]
      properties:
        schema: {type: string, enum: [npu.event.v1]}
        ts: {type: string, format: date-time}
        run_id: {type: string}
        seq: {type: integer}
        kind: {type: string, enum: [lifecycle, metric, summary, log, error]}
        level: {type: string, enum: [DEBUG, INFO, WARN, ERROR]}
        module: {type: string}
        event: {type: string}
        message: {type: string}
        host: {type: object}
        proc: {type: object}
        data: {type: object, description: "see events.md §6 for per-event shapes"}
    MetricSample:
      description: "An EventEnvelope where event == metric.sample; the data payload is specialized per metrics.md."
      allOf:
        - $ref: '#/components/schemas/EventEnvelope'
        - type: object
          properties:
            data:
              type: object
              required: [npu_util_percent, npu_state, npu_signal_source]
              properties:
                npu_util_percent: {type: number, minimum: 0, maximum: 100}
                npu_util_raw_percent: {type: number}
                npu_state: {type: string, enum: [unknown, idle, active]}
                npu_signal_source: {type: string, enum: [native_npu_counter, gpu_engine_luid_inference, unspecified]}
                metric_confidence: {type: string, enum: [native, inferred, absent]}
                cpu_percent: {type: number, minimum: 0, maximum: 100}
                cpu_mem_used_mib: {type: number}
                gpu_util_percent: {type: number, minimum: 0, maximum: 100}
                gpu_mem_mib: {type: number}
                npu_mem_mib: {type: number}
                npu_luid_candidates: {type: array, items: {type: string}}
                observed_npu_luids: {type: array, items: {type: string}}
                observed_luids: {type: array, items: {type: string}}
```

## 13. Legacy routes (transitional)

The current `web_api.py` exposes:

- `GET  /api/state`        — superseded by `GET /state` (§4).
- `POST /api/chat/send`    — subsumed by `POST /inference` (§5).
- `POST /api/chat/clear`   — superseded by `POST /session/clear` (§11).
- `POST /api/session/stop` — not part of this contract; reserved for removal in Iteration 4.

The `/api/*` prefix and the snapshot-shaped response bodies are
removed in Iteration 4.1 when `web_api.py → api.py` and the TUI-coupled
`reduce_dashboard_state` path is replaced by `build_api_snapshot`.

## 14. Codegen path (recommendation for `scripts/gen-types.sh`)

**Recommended: Path B (`/openapi.json` + `openapi-typescript` +
`openapi-fetch`).**

Rationale: (a) §12 of this document already defines the schema in
OpenAPI shape, so publishing `/openapi.json` via FastAPI's built-in
generator is zero additional work; (b) Path B keeps types anchored
to the served spec, giving a single source of truth for UI and
server; (c) `openapi-fetch` from the same author as `openapi-typescript`
pairs cleanly to produce a typed runtime client with route
constants, which beats hand-written fetch wrappers. Actual wiring
lands in Iteration 4 (Subagent Y) — this line is the recommendation
only.
