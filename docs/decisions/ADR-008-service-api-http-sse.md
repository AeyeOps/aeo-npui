---
Title: Service API is HTTP + SSE via FastAPI
Status: Accepted
Date: 2026-04-22
---

## Context

Layer 1 (the Python service) is the only contract the UI speaks to
(ADR-002). That contract has to carry:

- **Request/response** — UI submits a prompt, gets back a run handle.
  Simple RPC-shaped.
- **Long-lived streams** — NPU events (token arrival, metric samples,
  run lifecycle) are emitted continuously; the UI subscribes and
  renders as they arrive. Orders of magnitude more events than
  requests.
- **Introspection** — UI queries available models, service health,
  endurance run status. GET-style reads.

The UI lives in a WebView (Tauri's WebView2), so browser-native
primitives (`fetch`, `EventSource`, `WebSocket`) are zero-cost. Non-
browser primitives (gRPC-web, protobuf over HTTP/2) carry dependency
weight the UI does not otherwise need.

FastAPI is the Python web framework already in the codebase
(`service/src/npu_service/web_api.py` → `api.py` after Iteration 4.1).
It provides Pydantic-validated request/response models, auto-generated
OpenAPI, and first-class SSE via the `sse-starlette` add-on.

## Decision

**The service API is HTTP (request/response) + Server-Sent Events
(streaming) via FastAPI.**

Concretely (full spec in `docs/contracts/service-api.md`):

| Method | Path | Kind | Purpose |
|---|---|---|---|
| `GET` | `/health` | JSON | Liveness + readiness |
| `GET` | `/state` | JSON | Service state, active model, session |
| `GET` | `/models` | JSON | List models available to NPU |
| `POST` | `/inference` | JSON | Submit prompt; returns `{run_id, events_url, metrics_url}` |
| `POST` | `/endurance` | JSON | Kick off endurance run |
| `POST` | `/session/clear` | JSON | Reset conversation |
| `GET` | `/events` | SSE | Event stream (per run or global) |
| `GET` | `/metrics` | SSE | Metric-sample stream |

**Response schemas emit plain JSON dicts, not TUI dataclasses.** This
is the structural closing of ADR-001 and ADR-002. The legacy path
(`reduce_dashboard_state` serializing a TUI `DashboardState` to
browser JSON) is replaced in Iteration 4.1 by
`build_api_snapshot(settings, events, ...) -> dict` living in
`api.py`. The UI never imports or reconstructs a TUI type — it
renders the JSON shape defined in `service-api.md`.

**Resumable SSE.** `/events?run_id=<uuid>&since=<seq>` uses a monotonic
sequence number; reconnecting after a dropped TCP connection resumes
via the standard SSE `Last-Event-Id` header mirroring the last received
`id:` line. `/metrics?run_id=<uuid>&since=<ts>` uses a unix-ms
timestamp for the same purpose.

**WebSocket is an escape hatch.** Reserved for a future need
(bidirectional control, backpressure negotiation, binary framing). If
the need arises, it lands as a separate route — it does not replace
SSE for the one-way streaming use case.

## Consequences

**Easier:**

- Browser-native consumption. The UI's `src/api/` module is plain
  `fetch()` + `EventSource`; no protobuf codegen, no gRPC-web proxy.
- Proxy compatibility. HTTP + SSE traverses corporate proxies and
  localhost loopback the same way `curl` does. gRPC over HTTP/2 has
  well-known issues with some corporate middleboxes.
- Testability. `curl http://127.0.0.1:8765/health` is a valid
  liveness check. `curl -N http://127.0.0.1:8765/events?run_id=<uuid>`
  streams events in the terminal. No special client needed for
  ad-hoc probes.
- OpenAPI docs are free. FastAPI generates them from the Pydantic
  schemas; `/openapi.json` is the mechanically-verifiable shape of
  the contract.
- Mobile-web friendliness. A future mobile or web client reuses the
  same API without a second contract.

**Harder:**

- SSE is one-way (server → client). Client-initiated control lives in
  POST routes; that's a shape discipline, not a blocker.
- SSE connections can idle-timeout behind some proxies; the implementation
  sends periodic comments (`: keepalive\n\n`) to keep the connection
  warm. `sse-starlette` handles this by default.
- Pydantic → TypeScript codegen is required so the UI's types stay in
  sync with the server's (Iteration 4.3). See ADR-005 for toolchain
  specifics; the CI check for type drift is in plan §1.11.

**New work that follows:**

- Iteration 4.1: `web_api.py` → `api.py`; `reduce_dashboard_state`
  replaced by `build_api_snapshot()`.
- Iteration 4.2: SSE routes implemented via `sse-starlette`.
- Iteration 4.3: Pydantic-to-TS codegen via `pydantic2ts` (Path A) or
  OpenAPI → `openapi-typescript`/`openapi-fetch` (Path B); tool choice
  made at subagent time, recorded in `service-api.md`.
- Iteration 4.4: structured logs emit in the same schema the SSE
  `/events` stream emits, so the `.jsonl` log is a replayable event
  source.

## Alternatives Considered

**gRPC (or gRPC-web with a proxy).** Rejected: (a) the UI is a
WebView, so the browser-native `fetch` + `EventSource` path is strictly
cheaper than gRPC-web's proxy + codegen pipeline; (b) gRPC's
streaming primitive is subtly different from SSE in error-recovery
semantics, and SSE's "Last-Event-Id + auto-reconnect" model fits the
"operator stayed connected through a brief network blip" scenario
better than gRPC's RST_STREAM; (c) gRPC's dependency footprint is
larger for no visible benefit.

**Pure WebSocket (no HTTP routes, WS for everything).** Rejected: WS
is bidirectional, which is more than this contract needs for the
1.0 surface. Debugging ad-hoc ("can you curl it?") is harder.
WebSockets for control-plane operations do not fit the
request/response model cleanly. WS remains the escape hatch for a
future genuinely-bidirectional use case.

**REST with long-polling instead of SSE.** Rejected: long-polling's
reconnect semantics are worse than SSE's (no built-in `Last-Event-Id`,
each reconnect is a fresh request with full auth), and server-side
resource usage is higher (more concurrent requests, more TCP setup).
SSE is the cheaper, better-supported choice.

**GraphQL.** Rejected: solves a different problem (over-fetching and
client-specified queries for heterogeneous clients). This service has
one consumer today; GraphQL's typing and subscription stories add
tooling weight without matching benefit.

**Keep `reduce_dashboard_state` and serialize the TUI
`DashboardState` dataclass to JSON.** Explicitly rejected: this is the
status quo being demolished. It couples the service API to TUI
internals, violating ADR-002. The replacement is `build_api_snapshot()`.

## Status

Accepted. Route list is the baseline for `docs/contracts/service-api.md`.
Implementation lands in Iteration 4.2. Codegen in 4.3. See ADR-002 for
why this boundary exists, ADR-001 for why
`reduce_dashboard_state` is demolished, and ADR-010 for why storage
access is also API-mediated.
