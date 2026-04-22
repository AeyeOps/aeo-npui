# Service Layer (Layer 1) — Extraction Roadmap

**Scope:** Bring the Python service under `service/src/npu_service/` into
compliance with [`../contracts/service-api.md`](../contracts/service-api.md),
remove the Rich+Typer TUI (ADR-001), and isolate Windows-side process
invocation into a dedicated Layer-2 subpackage (ADR-002).

**Authoritative detail:** the step-by-step is already written in the
extraction plan. This doc is a pointer + delta summary — do not re-derive
the detail here.

- Full TUI-removal inventory and rewrite scope: plan **§4.1**.
- HTTP+SSE implementation, codegen, observability, launcher: plan
  **§4.2–4.5**.

## Current shape (pre-Iteration-4)

```
service/src/npu_service/
├── __init__.py
├── __main__.py
├── cli.py              ~1132 lines; Typer + Rich Live TUI entangled
├── web_api.py          ~356 lines; serializes TUI dataclasses to JSON
├── core/
│   ├── chat.py         session management (keep)
│   ├── events.py       event parsing + reduce_dashboard_state (partial keep)
│   ├── runners.py      backend-script runner (keep; pwsh/conda calls move)
│   ├── settings.py     pydantic-settings (keep)
│   ├── version.py      version lookup (keep)
│   └── dashboard_debug.py   TUI-only frame telemetry (delete)
└── ui/                 dashboard.py, chat_console.py, atomic_live.py (delete entire dir)
```

## Iteration 4 deltas

### 4.1 — Rename + TUI removal (authoritative: plan §4.1)

- `git mv web_api.py api.py` — preserves history; update the single
  reference in `cli.py`'s `serve` command (`npu_service.api:app`).
- **Delete outright (~750 lines pure TUI):** entire `ui/` directory
  (`dashboard.py`, `chat_console.py`, `atomic_live.py`, `__init__.py`)
  plus `core/dashboard_debug.py`.
- **Rewrite `cli.py` to ≤150 lines** — thin Typer surface exposing only:
  - `status` (prints paths),
  - `serve` (starts FastAPI),
  - probe command passthroughs (`run`, `watch`, `trace`, `phase-zero`,
    `endurance-headless`) that wrap `run_backend()`.
  Remove: `interactive_dashboard`, `run_dashboard`, `dashboard`,
  endurance-TUI loop, `ESCAPE_SEQUENCES`, `AtomicLive` usage,
  `render_chat_console` imports, `read_input_events`, `handle_log_key`,
  all termios/tty manipulation.
- **Refactor `core/events.py`:** keep lines 1–203 (pure event parsing:
  `EventRecord`, `RunSummary`, `EnduranceReport`, `load_events`,
  `latest_run_id`, `latest_summary_event`, `p95`,
  `build_endurance_report`, `build_run_summary`). Delete
  `reduce_dashboard_state` (lines 205–307) — it depends on the TUI
  `DashboardState`/`TrendMetric` dataclasses being removed.
- **Replace with `build_api_snapshot(settings, events, ...) -> dict`**
  in `api.py` — returns plain JSON-shaped dicts matching
  [`../contracts/service-api.md`](../contracts/service-api.md), not TUI
  dataclasses. This closes ADR-002 (UI speaks only service-defined
  schemas, never TUI types) and ADR-008's response-shape decision.
- **Pre-delete test inventory:** run
  `grep -rln 'DashboardState\|TrendMetric\|reduce_dashboard_state\|AtomicLive\|dashboard_debug\|render_chat_console' tests/`
  first. For each hit: delete (TUI-only), rewrite (concept survives in
  `build_api_snapshot`), or migrate (reusable fixture).
- **Dependency hygiene:** remove `rich` from `service/pyproject.toml`
  (runtime and dev-group). Keep `typer` — it remains the CLI framework.

### 4.2 — HTTP + SSE implementation (plan §4.2)

Implement the eight endpoints in
[`../contracts/service-api.md`](../contracts/service-api.md):

| Method + Path | Purpose |
|---|---|
| `GET /state` | service state, active model, session |
| `POST /inference` | submit prompt; returns `{run_id, events_url, metrics_url}` |
| `GET /events?run_id=<uuid>&since=<seq>` | SSE stream of events for one run (omit `run_id` for operator view) |
| `GET /metrics?run_id=<uuid>&since=<ts>` | SSE stream of metric samples |
| `POST /endurance` | kick off endurance run |
| `GET /models` | list NPU-available models |
| `GET /health` | liveness + readiness |
| `POST /session/clear` | reset conversation |

FastAPI + `sse-starlette` for the streams. Pydantic input validation;
malformed bodies rejected with structured errors. Clients MUST NOT
synthesize `events_url` / `metrics_url` from `run_id` — server owns
those URLs.

### 4.3 — Pydantic → TypeScript codegen (plan §4.3)

Emit `desktop/src/api/types.ts` from the service's Pydantic models via
`scripts/gen-types.sh` (scaffolded in Iteration 1.3). CI runs
`scripts/gen-types.sh --check` and fails on drift. Tool choice (Path A
`pydantic2ts` vs Path B OpenAPI → `openapi-typescript` + `openapi-fetch`)
is decided at write time by the subagent and recorded in
`../contracts/service-api.md`.

### 4.4 — Observability (plan §4.4)

Structured logs per [`../contracts/events.md`](../contracts/events.md).
Log sink: `%LOCALAPPDATA%\AeyeOps\aeo-npui\logs\service.log` (ADR-010).
Service metrics endpoint per ADR-008.

### 4.5 — Move Windows invocation to Layer 2 (plan §4.5)

Create `service/src/npu_service/launcher/`:

- `launcher/windows.py` — `pwsh.exe` invocation, `conda activate npu`
  wrapping, probe-script dispatch. Any `runners.py` code that shells out
  to Windows moves here.
- `launcher/wsl_bridge.py` — WSL-originated operator command routing.
- Port reservation + autostart: UI pings `GET /health`; on
  `ConnectionRefusedError`, Layer 2 spawns `uv run npu-service serve`.
  Full cross-OS design: [`./orchestration.md`](./orchestration.md).

## Acceptance (service layer — plan §4.1 acceptance verbatim)

- `grep -rIE '\b(rich|AtomicLive|DashboardState|TrendMetric|reduce_dashboard_state|dashboard_debug|render_chat_console)\b' service/src/` returns empty. Typer deliberately omitted — it stays as the CLI framework.
- `grep -E '^\s*"rich\b' service/pyproject.toml` returns empty (no runtime or dev-group entry).
- `grep -E '^\s*"typer\b' service/pyproject.toml` returns exactly one hit.
- `uv run pytest service/tests/` passes with updated tests.
- `uv run npu-service serve --port 8765` starts FastAPI; `curl http://127.0.0.1:8765/health` returns 200.
- `grep -rI 'web_api' service/` returns empty; `grep -rI 'api:app' service/src/npu_service/cli.py` returns ≥1 hit.
- Every endpoint in `service-api.md` has a passing test (plan §4 gate).
