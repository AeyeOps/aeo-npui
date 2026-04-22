"""Browser-facing API for the NPU console."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from npu_service.core.chat import (
    ChatMessage,
    ChatSession,
    ChatTurnResult,
    build_prompt,
    send_chat_turn,
    start_chat_session,
    stop_chat_session,
)
from npu_service.core.events import load_events, reduce_dashboard_state
from npu_service.core.settings import Settings, load_settings


class ChatInputRequest(BaseModel):
    text: str


class WebConsoleService:
    """Stateful bridge between the NPU backend and the browser UI."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.lock = threading.Lock()
        self.session: ChatSession | None = None
        self.startup_thread: threading.Thread | None = None
        self.startup_error: str | None = None
        self.startup_started = time.monotonic()
        self.pending_thread: threading.Thread | None = None
        self.pending_result: ChatTurnResult | None = None
        self.pending_error: str | None = None
        self.pending_generation = 0
        self.conversation_generation = 0
        self.messages: list[ChatMessage] = []
        self.last_status_line = "Starting local NPU session..."
        self.last_help_line = "Please wait while the model loads"
        self.auto_start = True

    def _seed_messages(self, active_session: ChatSession | None) -> list[ChatMessage]:
        if active_session is None:
            return []
        return [
            ChatMessage(
                "assistant",
                "You are chatting with the local TinyLlama model running on the Intel NPU. "
                f"Model load took {active_session.load_seconds:.2f}s. "
                "Type a message in English and press Enter.",
            )
        ]

    def ensure_startup(self) -> None:
        with self.lock:
            if not self.auto_start:
                return
            if self.session is not None:
                return
            if self.startup_thread is not None and self.startup_thread.is_alive():
                return
            self.startup_error = None
            self.startup_started = time.monotonic()

        def worker() -> None:
            try:
                started_session = start_chat_session(self.settings)
                with self.lock:
                    self.session = started_session
                    self.startup_error = None
                    self.messages = self._seed_messages(started_session)
                    self.last_status_line = "Ready"
                    self.last_help_line = "Type a message and press Enter"
            except Exception as exc:  # noqa: BLE001
                with self.lock:
                    self.session = None
                    self.startup_error = str(exc)
                    self.last_status_line = "Startup failed"
                    self.last_help_line = "Check the event log or restart the service"

        thread = threading.Thread(target=worker, daemon=True)
        with self.lock:
            self.startup_thread = thread
        thread.start()

    def _handle_completed_turn_locked(self) -> None:
        if self.pending_thread is None or self.pending_thread.is_alive():
            return
        result = self.pending_result
        pending_error = self.pending_error
        self.pending_thread = None
        self.pending_result = None
        self.pending_error = None
        if self.pending_generation != self.conversation_generation:
            self.last_status_line = "Conversation cleared"
            self.last_help_line = "Type a new message to start fresh"
            return
        if pending_error:
            self.messages.append(ChatMessage("assistant", f"NPU chat failed: {pending_error}"))
            self.last_status_line = "Last turn failed"
            self.last_help_line = "Check the event log and retry"
            return
        if result is None:
            return
        if result.exit_code != 0:
            self.messages.append(
                ChatMessage(
                    "assistant",
                    "The NPU run failed. Check the latest watch and llm artifacts for details.",
                )
            )
            self.last_status_line = "Last turn failed"
            self.last_help_line = "Check the latest watch and llm artifacts"
            return
        self.messages.append(ChatMessage("assistant", result.response_text.strip()))
        self.last_status_line = (
            f"Last turn completed in {result.generate_seconds:.2f}s "
            f"(peak NPU {result.peak_npu_util_percent:.1f}%)"
        )
        self.last_help_line = "Type another message or switch views"

    def _build_log_lines(self, run_id: str | None) -> list[str]:
        events = load_events(self.settings.event_log)
        log_lines: list[str] = []
        session_events = [event for event in events if run_id is not None and event.run_id == run_id]
        for event in session_events[-160:]:
            payload = event.data
            if event.event == "metric.sample":
                npu_state = payload.get("npu_state", "unknown")
                npu_percent = payload.get("npu_util_percent")
                npu_label = "unknown" if npu_percent is None else f"{float(npu_percent):.1f}%"
                log_lines.append(
                    f"{event.ts[11:19]} metric "
                    f"cpu={float(payload.get('cpu_percent', 0.0)):.1f}% "
                    f"npu={npu_state}:{npu_label} "
                    f"gpu={float(payload.get('gpu_util_percent', 0.0)):.1f}%"
                )
            elif event.kind == "summary":
                log_lines.append(
                    f"{event.ts[11:19]} summary "
                    f"exit={payload.get('probe_exit_code', '?')} "
                    f"peak_npu={float(payload.get('peak_npu_util_percent', 0.0)):.1f}% "
                    f"mem_delta={float(payload.get('cpu_mem_delta_mib', 0.0)):.1f}MiB"
                )
            else:
                log_lines.append(
                    f"{event.ts[11:19]} {event.level.lower()} "
                    f"{event.module}:{event.event} {event.message}"
                )
        return log_lines

    def snapshot(self, autostart: bool = True) -> dict[str, object]:
        if autostart:
            self.ensure_startup()
        with self.lock:
            self._handle_completed_turn_locked()
            session = self.session
            startup_thread = self.startup_thread
            startup_error = self.startup_error
            pending_thread = self.pending_thread
            messages = list(self.messages[-40:])
            status_line = self.last_status_line
            help_line = self.last_help_line

        events = load_events(self.settings.event_log)
        dashboard = reduce_dashboard_state(
            self.settings,
            events,
            selected_run_id=session.run_id if session is not None else None,
            backend_lines=tuple(),
            forced_command="watch",
        )
        system_message = (
            "Loading TinyLlama on the local Intel NPU..."
            if startup_thread is not None and startup_thread.is_alive()
            else "Startup failed. Check the error and retry."
            if startup_error is not None and session is None
            else "NPU is processing your reply..."
            if pending_thread is not None and pending_thread.is_alive()
            else None
        )
        return {
            "statusLine": status_line,
            "helpLine": help_line,
            "systemMessage": system_message,
            "startupState": (
                "starting"
                if startup_thread is not None and startup_thread.is_alive()
                else "failed"
                if startup_error is not None and session is None
                else "ready"
                if session is not None
                else "idle"
            ),
            "sessionRunId": session.run_id if session is not None else None,
            "messages": [asdict(message) for message in messages],
            "controls": [
                "/view split",
                "/view chat",
                "/view metrics",
                "/view log",
                "/clear",
                "/quit",
            ],
            "dashboard": {
                "title": dashboard.title,
                "mode": dashboard.mode,
                "status": dashboard.status,
                "activeModel": dashboard.active_model,
                "activeRunId": dashboard.active_run_id,
                "selectedCommand": dashboard.selected_command,
                "notes": list(dashboard.notes),
                "interactionLines": list(dashboard.interaction_lines),
                "trends": [asdict(trend) for trend in dashboard.trends],
                "artifactRows": [
                    {"label": label, "value": value} for label, value in dashboard.artifact_rows
                ],
            },
            "logLines": self._build_log_lines(session.run_id if session is not None else None),
            "endurance": self._load_endurance_summary(),
        }

    def _load_endurance_summary(self) -> dict[str, object] | None:
        latest = self.settings.artifacts_dir / "endurance" / "latest.json"
        if not latest.exists():
            return None
        return json.loads(latest.read_text(encoding="utf-8"))

    def clear(self) -> dict[str, object]:
        with self.lock:
            self.messages = self._seed_messages(self.session)
            self.conversation_generation += 1
            self.last_status_line = "Conversation cleared"
            self.last_help_line = "Type a new message to start fresh"
        return self.snapshot()

    def stop(self) -> dict[str, object]:
        with self.lock:
            session = self.session
            self.auto_start = False
            self.session = None
            self.startup_thread = None
            self.pending_thread = None
            self.pending_result = None
            self.pending_error = None
            self.messages = []
            self.last_status_line = "Stopped"
            self.last_help_line = "Refresh to start a new session"
        if session is not None:
            stop_chat_session(session)
        return self.snapshot(autostart=False)

    def send(self, text: str) -> dict[str, object]:
        normalized = text.strip()
        if not normalized:
            return self.snapshot()
        if normalized == "/clear":
            return self.clear()
        if normalized == "/quit":
            return self.stop()

        with self.lock:
            self.auto_start = True
        self.ensure_startup()
        should_return_snapshot = False
        with self.lock:
            self._handle_completed_turn_locked()
            if self.startup_thread is not None and self.startup_thread.is_alive():
                self.last_status_line = "Starting local NPU session..."
                self.last_help_line = "Please wait for the model to load"
                should_return_snapshot = True
            elif self.startup_error is not None or self.session is None:
                self.messages.append(
                    ChatMessage(
                        "assistant",
                        f"NPU session is not ready: {self.startup_error or 'unknown startup failure'}",
                    )
                )
                self.last_status_line = "Startup failed"
                self.last_help_line = "Check the event log and retry"
                should_return_snapshot = True
            else:
                prompt = build_prompt(self.messages, normalized)
                self.messages.append(ChatMessage("user", normalized))
                self.last_status_line = "Generating on local NPU..."
                self.last_help_line = "Wait for the response, or inspect the live log"
                self.pending_generation = self.conversation_generation
                session = self.session

                def worker() -> None:
                    try:
                        result = send_chat_turn(session, self.settings, prompt)
                        with self.lock:
                            self.pending_result = result
                            self.pending_error = None
                    except Exception as exc:  # noqa: BLE001
                        with self.lock:
                            self.pending_result = None
                            self.pending_error = str(exc)

                self.pending_result = None
                self.pending_error = None
                self.pending_thread = threading.Thread(target=worker, daemon=True)
                self.pending_thread.start()
        if should_return_snapshot:
            return self.snapshot()
        return self.snapshot()


app = FastAPI(title="NPU Console API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
service = WebConsoleService(load_settings())


@app.get("/health")
def get_health() -> dict[str, str]:
    """Lightweight liveness probe.

    Deliberately does NOT touch ``service`` — it must answer even when
    the NPU worker is mid-startup or has failed. The desktop shell polls
    this every 5 s to drive the connection indicator.
    """

    return {"status": "ok"}


@app.get("/api/state")
def get_state() -> dict[str, object]:
    return service.snapshot()


@app.post("/api/chat/send")
def post_chat(request: ChatInputRequest) -> dict[str, object]:
    return service.send(request.text)


@app.post("/api/chat/clear")
def post_clear() -> dict[str, object]:
    return service.clear()


@app.post("/api/session/stop")
def post_stop() -> dict[str, object]:
    return service.stop()


@app.on_event("shutdown")
def on_shutdown() -> None:
    with service.lock:
        session = service.session
    if session is not None:
        stop_chat_session(session)
