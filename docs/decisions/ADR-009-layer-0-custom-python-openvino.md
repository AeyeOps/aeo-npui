---
Title: Layer 0 runtime is custom Python + OpenVINO
Status: Accepted
Date: 2026-04-22
---

## Context

Layer 0 is the NPU execution runtime — the code that loads a model,
feeds tokens, and produces output on the Intel NPU. Two broad
approaches exist for driving OpenVINO on NPU:

1. **Custom Python process** — direct use of `openvino-genai` (or
   `openvino`) Python bindings inside a process managed by Layer 1.
   The service owns the model load, the inference loop, the streaming
   callback hookup to SSE.
2. **OpenVINO Model Server (OVMS)** — a separate process that hosts
   one or more models and exposes gRPC/HTTP endpoints for inference.
   Layer 1 becomes a client of OVMS rather than an embedder of
   OpenVINO.

OVMS is attractive in principle: separation of concerns, multi-model
hosting, enterprise operational features (hot model swap, versioning,
metrics exporters). In practice (as of 2026-Q2):

- OVMS's Windows NPU support is not at parity with the direct
  `openvino-genai` Python path. Some NPU-specific features land in
  the Python bindings first and propagate to OVMS months later.
- This product currently serves a single operator with a single model
  at a time. The multi-model hosting story is not a requirement for
  1.0.
- An additional process and an additional network contract
  (OVMS gRPC) add surface area the service does not otherwise need.
  Every failure-mode in the operator's NPU run is now either an
  OVMS issue or a Layer-1 issue; diagnosing which is harder than
  diagnosing a single Python process.

## Decision

**Layer 0 runtime is custom Python + OpenVINO.** The service
(`service/src/npu_service/worker.py`) directly imports
`openvino-genai` and drives the NPU inference loop in-process.
Streaming callbacks from OpenVINO become SSE events on the
`/events` route (ADR-008).

**OVMS is deferred, not rejected.** Revisit when any of the following
is true:

- **(a) Windows NPU support for OVMS reaches parity** with the direct
  Python path. The gap today is specific feature coverage (token-level
  streaming callbacks, NPU-specific precision modes, model-compilation
  caching behavior); track upstream.
- **(b) The product needs multi-model hot-swap** without service
  restart. OVMS has this built-in; the custom Python path would need
  to implement it (model-manager layer, unload semantics, memory
  budgeting).
- **(c) The model surface exceeds what a single Python process
  handles well** — e.g. multiple concurrent inference contexts,
  A/B model comparison, large model catalog with on-demand load.
  OVMS's process-isolation story gets stronger at that scale.

Until at least one of these is true, the simpler single-process path
is the right call.

## Consequences

**Easier:**

- One process to deploy. `uv run npu-service serve` starts FastAPI and
  the NPU worker in the same Python interpreter.
- One set of dependencies. `openvino-genai` lives in the service's
  `uv` environment; no parallel install of OVMS.
- Error paths are local. An OpenVINO exception is caught in the
  service's except block, not across a gRPC boundary.
- Debugging is a Python debugger away. OVMS debugging involves two
  process contexts and a network hop.

**Harder:**

- Multi-model hot-swap (if ever needed) has to be implemented in
  Python. First-cut plan: allow one active model per service; model
  change requires service restart. This is fine for 1.0.
- Memory budgeting is the service's responsibility. A model that
  doesn't fit NPU memory fails at load time with a Python exception;
  the service surfaces this as a structured error over the API.
- The service process IS the inference process. A bug in inference
  code can take down the API surface. Mitigation: heavy error
  handling in `worker.py` and a `/health` route that returns 503 (not
  200) when the worker is in a degraded state.

**New work that follows:**

- Iteration 4.1 keeps `worker.py` (currently `core/runners.py` plus
  backend-script callers) as the NPU execution module; it is not
  demolished as TUI code was.
- Iteration 4.4 adds structured logging from the worker so inference
  failures produce actionable events in `npu-events.jsonl`.
- A "watch OVMS" note lives in `docs/roadmap/service-layer.md`;
  revisit every iteration.

## Alternatives Considered

**OVMS from day 1.** Rejected: (a)–(c) above are not true at 1.0; the
simpler path is correct until they are.

**Rust NPU runtime (OpenVINO has a C API, Rust could wrap it).**
Rejected: adds a systems-language surface area for no visible gain. The
Python bindings are the canonical, most-tested surface; the NPU
runtime itself is already in C++ behind the bindings. Rust in Layer 0
would be a re-implementation, not an improvement.

**ONNX Runtime DirectML backend instead of OpenVINO.** Rejected:
Intel's NPU is best-supported via OpenVINO; DirectML is Microsoft's
GPU/NPU abstraction layer but does not currently give parity with
OpenVINO on Intel NPU specifically. If the product ever supports
non-Intel NPU, revisit.

**llama.cpp / other inference stacks.** Rejected: they target GPU /
CPU paths. Intel NPU is an OpenVINO story.

**Separate Python process for NPU work, Layer 1 calls it via
stdin/stdout or a Unix socket.** Rejected: this is "OVMS done badly"
— all the multi-process cost without OVMS's ecosystem benefits.

## Status

Accepted. `worker.py` uses `openvino-genai` directly. OVMS watchlist
items (a)–(c) are tracked in `docs/roadmap/service-layer.md`. See
ADR-008 for how the inference callbacks become SSE events, ADR-011 for
the Python version constraint that `openvino-genai` imposes.
