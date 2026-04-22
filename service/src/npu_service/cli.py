"""Typer command surface for the NPU operator console."""

from __future__ import annotations

import json
import os
import select
import sys
import termios
import threading
import time
import tty
from dataclasses import replace
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console, RenderableType
from rich.table import Table

from npu_service.core.chat import (
    ChatMessage,
    ChatSession,
    ChatTurnResult,
    build_prompt,
    send_chat_turn,
    start_chat_session,
    stop_chat_session,
)
from npu_service.core.dashboard_debug import (
    append_dashboard_debug,
    measure_renderable,
    reset_dashboard_debug_log,
)
from npu_service.core.events import (
    RunSummary,
    build_endurance_report,
    build_run_summary,
    load_events,
    reduce_dashboard_state,
)
from npu_service.core.runners import SCRIPT_TARGETS, RunnerError, run_script, start_script
from npu_service.core.settings import Settings, load_settings
from npu_service.core.version import get_version
from npu_service.ui.atomic_live import AtomicLive
from npu_service.ui.chat_console import (
    ChatConsoleState,
    compute_chat_layout_metrics,
    render_chat_console,
)
from npu_service.ui.dashboard import build_iteration_two_state, render_dashboard

app = typer.Typer(
    name="npu-service",
    no_args_is_help=True,
    rich_markup_mode="rich",
    help="Rich + Typer operator console for the NPU workflow.",
)
console = Console()

ESCAPE_SEQUENCES = (
    b"\x1b[A",
    b"\x1b[B",
    b"\x1b[5~",
    b"\x1b[6~",
)
CONTROL_BYTES = {0x1B, 0x0D, 0x0A, 0x08, 0x7F}


def live_render_width(settings: Settings, raw_width: int) -> int:
    """Return a wrap-safe width budget for live full-screen rendering."""

    guard = max(0, settings.dashboard_width_guard)
    return max(40, raw_width - guard)


def version_callback(value: bool) -> None:
    """Print version and exit."""

    if value:
        console.print(f"npu-service {get_version()}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=version_callback,
            is_eager=True,
            help="Show version and exit.",
        ),
    ] = False,
) -> None:
    """Operate the NPU workflow from a packaged CLI."""


def get_settings() -> Settings:
    """Load settings lazily for commands."""

    return load_settings()


def run_backend(command_name: str) -> None:
    """Run one backend script and forward its exit code."""

    settings = get_settings()
    try:
        exit_code = run_script(settings, command_name)
    except RunnerError as exc:
        console.print(f"[red]ERROR:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    raise typer.Exit(code=exit_code)


def pump_process_output(backend_process: object, backend_lines: list[str]) -> None:
    """Read any currently available child output without blocking."""

    stdout = getattr(backend_process, "stdout", None)
    stderr = getattr(backend_process, "stderr", None)
    streams = [stream for stream in (stdout, stderr) if stream is not None]
    if not streams:
        return

    ready, _, _ = select.select(streams, [], [], 0)
    for stream in ready:
        line = stream.readline()
        if not line:
            continue
        if stream is stdout:
            backend_lines.append(line.rstrip())
        else:
            backend_lines.append(f"stderr: {line.rstrip()}")


def drain_process_output(backend_process: object, backend_lines: list[str]) -> None:
    """Drain any remaining child output after process completion."""

    stdout = getattr(backend_process, "stdout", None)
    stderr = getattr(backend_process, "stderr", None)
    if stdout is not None:
        for line in stdout.read().splitlines():
            backend_lines.append(line.rstrip())
    if stderr is not None:
        for line in stderr.read().splitlines():
            backend_lines.append(f"stderr: {line.rstrip()}")


@app.command("phase-zero")
def phase_zero() -> None:
    """Run the raw NPU access proof."""

    run_backend("phase-zero")


@app.command("run")
def run() -> None:
    """Run the current NPU LLM probe."""

    run_backend("run")


@app.command("watch")
def watch() -> None:
    """Run the LLM probe with live metrics."""

    run_backend("watch")


@app.command("trace")
def trace() -> None:
    """Run the LLM probe with WPR NeuralProcessing trace."""

    run_backend("trace")


def interactive_dashboard() -> None:
    """Run the human-first interactive dashboard."""

    settings = get_settings()
    startup_artifact = settings.chat_startup_artifact
    startup_artifact.parent.mkdir(parents=True, exist_ok=True)
    reset_dashboard_debug_log(settings)
    append_dashboard_debug(
        settings,
        "session.start",
        dashboard_width_guard=settings.dashboard_width_guard,
        dashboard_capture_metrics=settings.dashboard_capture_metrics,
    )
    view = "split"
    last_status_line = "Starting local NPU session..."
    last_help_line = "Please wait while the model loads"
    input_buffer = ""
    log_follow = True
    log_top_line = 0
    session: ChatSession | None = None
    startup_thread: threading.Thread | None = None
    startup_error: str | None = None
    startup_started = time.monotonic()
    startup_announced = False
    pending_thread: threading.Thread | None = None
    pending_result: ChatTurnResult | None = None
    pending_error: str | None = None
    conversation_generation = 0
    pending_generation = 0
    messages: list[ChatMessage] = []
    state_lock = threading.Lock()
    frame_counter = 0

    startup_artifact.write_text("starting\n", encoding="utf-8")

    def seed_messages(active_session: ChatSession | None = None) -> list[ChatMessage]:
        current_session = active_session or session
        if current_session is None:
            return []
        return [
            ChatMessage(
                "assistant",
                "You are chatting with the local TinyLlama model running on the Intel NPU. "
                f"Model load took {current_session.load_seconds:.2f}s. "
                "Type a message in English and press Enter.",
            )
        ]

    def start_session_worker() -> None:
        nonlocal session, startup_error
        try:
            started_session = start_chat_session(settings)
            with state_lock:
                session = started_session
                startup_error = None
            startup_artifact.write_text("ok\n", encoding="utf-8")
            append_dashboard_debug(
                settings,
                "startup.ready",
                run_id=started_session.run_id,
                load_seconds=started_session.load_seconds,
                worker_pid=started_session.worker_pid,
            )
        except Exception as exc:  # noqa: BLE001
            with state_lock:
                startup_error = str(exc)
                session = None
            startup_artifact.write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
            append_dashboard_debug(
                settings,
                "startup.failed",
                error_type=type(exc).__name__,
                error=str(exc),
            )

    startup_thread = threading.Thread(target=start_session_worker, daemon=True)
    startup_thread.start()

    def render_state(status_line: str, help_line: str) -> RenderableType:
        nonlocal frame_counter
        with state_lock:
            session_snapshot = session
            startup_thread_snapshot = startup_thread
            startup_error_snapshot = startup_error
            pending_thread_snapshot = pending_thread
        view_snapshot = view
        input_snapshot = input_buffer
        log_follow_snapshot = log_follow
        log_top_line_snapshot = log_top_line
        messages_snapshot = tuple(messages[-12:])
        raw_width = console.size.width
        raw_height = console.size.height
        render_width = live_render_width(settings, raw_width)
        layout_metrics = compute_chat_layout_metrics(
            width=render_width,
            height=raw_height,
            view_mode=view_snapshot,
        )
        events = load_events(settings.event_log)
        dashboard_state = reduce_dashboard_state(
            settings,
            events,
            selected_run_id=session_snapshot.run_id if session_snapshot is not None else None,
            backend_lines=tuple(),
            forced_command="watch",
        )
        log_lines = []
        session_events = [
            event
            for event in events
            if session_snapshot is not None and event.run_id == session_snapshot.run_id
        ]
        for event in session_events[-120:]:
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
        spinner_frames = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧")
        spinner = spinner_frames[
            int((time.monotonic() - startup_started) * 8) % len(spinner_frames)
        ]
        state = ChatConsoleState(
            view_mode=view_snapshot,
            title="Chat With Local NPU",
            subtitle="Type plain English below",
            status_line=status_line,
            help_line=help_line,
            system_message=(
                f"{spinner} Loading TinyLlama on the local Intel NPU..."
                if startup_thread_snapshot is not None and startup_thread_snapshot.is_alive()
                else "Startup failed. Check the error and /view log."
                if startup_error_snapshot is not None and session_snapshot is None
                else "NPU is processing your reply..."
                if pending_thread_snapshot is not None and pending_thread_snapshot.is_alive()
                else None
            ),
            dashboard=dashboard_state,
            messages=messages_snapshot,
            input_buffer=input_snapshot,
            log_lines=tuple(log_lines),
            log_follow=log_follow_snapshot,
            log_top_line=log_top_line_snapshot,
            controls=(
                "/view split",
                "/view chat",
                "/view metrics",
                "/view log",
                "/clear",
                "/help",
                "/quit",
                "f toggle follow in log view",
            ),
        )
        renderable = render_chat_console(
            state,
            width=layout_metrics.render_width,
            height=layout_metrics.render_height,
        )
        frame_counter += 1
        if settings.dashboard_capture_metrics:
            measurements = measure_renderable(
                renderable,
                width=layout_metrics.render_width,
                height=layout_metrics.render_height,
            )
            append_dashboard_debug(
                settings,
                "frame.rendered",
                frame=frame_counter,
                raw_width=raw_width,
                raw_height=raw_height,
                render_width=layout_metrics.render_width,
                render_height=layout_metrics.render_height,
                view_mode=view_snapshot,
                log_follow=log_follow_snapshot,
                log_top_line=log_top_line_snapshot,
                **measurements,
            )
        return renderable

    def do_turn(user_text: str) -> None:
        nonlocal last_status_line, last_help_line, pending_thread, pending_result, pending_error
        nonlocal pending_generation
        nonlocal startup_thread, startup_error, startup_announced, messages
        if startup_thread is not None and startup_thread.is_alive():
            startup_thread.join()
        with state_lock:
            session_snapshot = session
            startup_error_snapshot = startup_error
        if startup_error_snapshot is not None or session_snapshot is None:
            messages.append(
                ChatMessage(
                    "assistant",
                    f"NPU session is not ready: {startup_error_snapshot or 'unknown startup failure'}",
                )
            )
            last_status_line = "Startup failed"
            last_help_line = "Check the event log or restart the dashboard"
            return
        prompt = build_prompt(messages, user_text)
        messages.append(ChatMessage("user", user_text))
        last_status_line = "Generating on local NPU..."
        last_help_line = "Wait for the response, or switch to /view log to inspect activity"
        pending_generation = conversation_generation
        append_dashboard_debug(
            settings,
            "turn.started",
            user_text=user_text,
            conversation_generation=conversation_generation,
            prompt_length=len(prompt),
            prompt=prompt,
        )

        def worker() -> None:
            nonlocal pending_result, pending_error
            try:
                result = send_chat_turn(session_snapshot, settings, prompt)
                with state_lock:
                    pending_result = result
                    pending_error = None
            except Exception as exc:  # noqa: BLE001
                with state_lock:
                    pending_result = None
                    pending_error = str(exc)

        with state_lock:
            pending_result = None
            pending_error = None
        pending_thread = threading.Thread(target=worker, daemon=True)
        pending_thread.start()

    def handle_completed_turn() -> None:
        nonlocal pending_thread, pending_result, pending_error, last_status_line, last_help_line
        nonlocal startup_thread, startup_announced, messages
        if startup_thread is not None and not startup_thread.is_alive() and not startup_announced:
            startup_announced = True
            startup_thread = None
            with state_lock:
                session_snapshot = session
                startup_error_snapshot = startup_error
            if session_snapshot is not None:
                messages = seed_messages(session_snapshot)
                last_status_line = "Ready"
                last_help_line = "Type a message and press Enter"
                append_dashboard_debug(
                    settings,
                    "startup.announced",
                    run_id=session_snapshot.run_id,
                )
            elif startup_error_snapshot is not None:
                last_status_line = "Startup failed"
                last_help_line = "Check the event log or restart the dashboard"
        if pending_thread is None or pending_thread.is_alive():
            return
        with state_lock:
            result = pending_result
            pending_error_snapshot = pending_error
        pending_thread = None
        with state_lock:
            pending_result = None
            pending_error = None
        if pending_generation != conversation_generation:
            last_status_line = "Conversation cleared"
            last_help_line = "Type a new message to start fresh"
            append_dashboard_debug(
                settings,
                "turn.discarded",
                pending_generation=pending_generation,
                conversation_generation=conversation_generation,
            )
            return
        if pending_error_snapshot:
            messages.append(ChatMessage("assistant", f"NPU chat failed: {pending_error_snapshot}"))
            last_status_line = "Last turn failed"
            last_help_line = "Check the event log or switch to /view log"
            append_dashboard_debug(
                settings,
                "turn.failed",
                error=pending_error_snapshot,
            )
            return
        if result is None:
            return
        if result.exit_code != 0:
            messages.append(
                ChatMessage(
                    "assistant",
                    "The NPU run failed. Check the latest watch and llm artifacts for details.",
                )
            )
            last_status_line = "Last turn failed"
            last_help_line = "Check the latest watch and llm artifacts"
            append_dashboard_debug(
                settings,
                "turn.failed",
                exit_code=result.exit_code,
                run_id=result.run_id,
            )
            return
        messages.append(ChatMessage("assistant", result.response_text.strip()))
        last_status_line = (
            f"Last turn completed in {result.generate_seconds:.2f}s "
            f"(peak NPU {result.peak_npu_util_percent:.1f}%)"
        )
        last_help_line = "Type another message, or use /view split|chat|metrics|log"
        append_dashboard_debug(
            settings,
            "turn.completed",
            run_id=result.run_id,
            generate_seconds=result.generate_seconds,
            peak_npu_util_percent=result.peak_npu_util_percent,
        )

    def dispatch_command(command_text: str) -> bool:
        nonlocal view, messages, input_buffer, log_follow, log_top_line
        nonlocal last_help_line, last_status_line, conversation_generation
        if command_text == "/quit":
            append_dashboard_debug(settings, "command.quit")
            raise typer.Exit(code=0)
        if command_text == "/help":
            messages.append(
                ChatMessage(
                    "assistant",
                    "Commands: /view split, /view chat, /view metrics, /view log, /clear, /quit",
                )
            )
            append_dashboard_debug(settings, "command.help")
            return True
        if command_text == "/clear":
            messages = seed_messages()
            input_buffer = ""
            conversation_generation += 1
            last_status_line = "Conversation cleared"
            last_help_line = "Type a new message to start fresh"
            append_dashboard_debug(
                settings,
                "command.clear",
                conversation_generation=conversation_generation,
            )
            return True
        if command_text.startswith("/view "):
            _, _, selected = command_text.partition(" ")
            if selected in {"split", "chat", "metrics", "log"}:
                view = selected
                last_help_line = (
                    "Type a message and press Enter"
                    if view != "log"
                    else "Use arrows/PgUp/PgDn to scroll log, f toggles follow"
                )
                if view == "log":
                    log_follow = True
                    log_top_line = 0
                append_dashboard_debug(
                    settings,
                    "command.view",
                    selected=view,
                    log_follow=log_follow,
                    log_top_line=log_top_line,
                )
                return True
            messages.append(
                ChatMessage("assistant", "Unknown view. Use split, chat, metrics, or log.")
            )
            append_dashboard_debug(settings, "command.unknown_view", command_text=command_text)
            return True
        return False

    def read_input_events(fd: int, timeout: float) -> list[str]:
        ready, _, _ = select.select([fd], [], [], timeout)
        if not ready:
            return []
        data = bytearray(os.read(fd, 1024))
        more_ready, _, _ = select.select([fd], [], [], 0.01)
        while more_ready:
            data.extend(os.read(fd, 1024))
            more_ready, _, _ = select.select([fd], [], [], 0.01)

        events: list[str] = []
        index = 0
        while index < len(data):
            byte = data[index]
            if byte == 0x1B:
                matched = None
                for seq in ESCAPE_SEQUENCES:
                    if data[index : index + len(seq)] == seq:
                        matched = seq
                        break
                if matched is not None:
                    events.append(matched.decode("utf-8", "ignore"))
                    index += len(matched)
                    continue
                events.append("\x1b")
                index += 1
                continue
            if byte in (0x0D, 0x0A):
                events.append("\n")
                index += 1
                continue
            if byte in (0x08, 0x7F):
                events.append("\x7f")
                index += 1
                continue
            start = index
            while index < len(data) and data[index] not in CONTROL_BYTES:
                index += 1
            chunk = bytes(data[start:index]).decode("utf-8", "ignore")
            if chunk:
                events.append(chunk)
        return events

    def handle_log_key(key: str, total_lines: int, viewport_rows: int) -> bool:
        nonlocal log_follow, log_top_line
        if view != "log" or input_buffer:
            return False
        if key.lower() == "f":
            log_follow = not log_follow
            if log_follow:
                log_top_line = max(0, total_lines - viewport_rows)
            append_dashboard_debug(
                settings,
                "log.follow_toggled",
                log_follow=log_follow,
                log_top_line=log_top_line,
            )
            return True
        if key in ("\x1b[A", "k"):
            log_follow = False
            log_top_line = max(0, log_top_line - 1)
            append_dashboard_debug(settings, "log.scroll", direction="up", log_top_line=log_top_line)
            return True
        if key in ("\x1b[B", "j"):
            log_follow = False
            log_top_line = min(max(0, total_lines - viewport_rows), log_top_line + 1)
            append_dashboard_debug(
                settings,
                "log.scroll",
                direction="down",
                log_top_line=log_top_line,
            )
            return True
        if key == "\x1b[5~":
            log_follow = False
            log_top_line = max(0, log_top_line - 10)
            append_dashboard_debug(
                settings,
                "log.scroll",
                direction="page_up",
                log_top_line=log_top_line,
            )
            return True
        if key == "\x1b[6~":
            log_follow = False
            log_top_line = min(max(0, total_lines - viewport_rows), log_top_line + 10)
            append_dashboard_debug(
                settings,
                "log.scroll",
                direction="page_down",
                log_top_line=log_top_line,
            )
            return True
        return False

    try:
        if not sys.stdin.isatty():
            while True:
                console.clear()
                console.print(render_state(last_status_line, last_help_line))
                line = sys.stdin.readline()
                if line == "":
                    break
                user_text = line.strip()
                if not user_text:
                    continue
                if dispatch_command(user_text):
                    continue
                do_turn(user_text)
                while pending_thread is not None and pending_thread.is_alive():
                    time.sleep(0.1)
                handle_completed_turn()
        else:
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                with AtomicLive(
                    render_state(last_status_line, last_help_line),
                    console=console,
                    screen=True,
                    refresh_per_second=8,
                    auto_refresh=False,
                    vertical_overflow="crop",
                ) as live:
                    while True:
                        handle_completed_turn()
                        live.update(render_state(last_status_line, last_help_line), refresh=True)
                        events = read_input_events(fd, 0.2)
                        if not events:
                            continue
                        total_lines = len(load_events(settings.event_log))
                        layout_metrics = compute_chat_layout_metrics(
                            width=live_render_width(settings, console.size.width),
                            height=console.size.height,
                            view_mode=view,
                        )
                        for key in events:
                            if handle_log_key(key, total_lines, layout_metrics.log_viewport_rows):
                                continue
                            if key == "\n":
                                user_text = input_buffer.strip()
                                input_buffer = ""
                                if not user_text:
                                    continue
                                append_dashboard_debug(
                                    settings,
                                    "input.submitted",
                                    text=user_text,
                                )
                                if dispatch_command(user_text):
                                    continue
                                do_turn(user_text)
                                continue
                            if key == "\x7f":
                                input_buffer = input_buffer[:-1]
                                append_dashboard_debug(settings, "input.backspace", buffer_len=len(input_buffer))
                                continue
                            if key and key.isprintable():
                                input_buffer += key
                                append_dashboard_debug(
                                    settings,
                                    "input.buffered",
                                    text=key,
                                    buffer_len=len(input_buffer),
                                )
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    finally:
        with state_lock:
            session_snapshot = session
        if session_snapshot is not None:
            append_dashboard_debug(settings, "session.stop", run_id=session_snapshot.run_id)
            stop_chat_session(session_snapshot)


def run_dashboard(
    command: Annotated[
        str | None,
        typer.Option(
            "--command",
            help="Optionally launch one backend command inside the live dashboard.",
        ),
    ] = None,
    static: Annotated[
        bool,
        typer.Option(
            "--static",
            help="Render the static dashboard snapshot instead of live mode.",
        ),
    ] = False,
    replay: Annotated[
        str | None,
        typer.Option(
            "--replay",
            help="Replay a specific JSONL event log instead of the default live event log.",
        ),
    ] = None,
    once: Annotated[
        bool,
        typer.Option(
            "--once",
            help="Render a single live frame and exit. Useful for tests and review.",
        ),
    ] = False,
    refresh_hz: Annotated[
        float,
        typer.Option(
            "--refresh-hz",
            min=1.0,
            max=10.0,
            help="Refresh rate for live mode.",
        ),
    ] = 4.0,
) -> None:
    """Render the operator dashboard."""

    settings = get_settings()
    if command is None and replay is None and not static and not once:
        interactive_dashboard()
        raise typer.Exit(code=0)
    if static:
        state = build_iteration_two_state(settings)
        console.print(
            render_dashboard(
                state,
                width=live_render_width(settings, console.size.width),
                height=console.size.height,
            )
        )
        console.print(
            "\nStatic dashboard mode is intended for review and snapshot validation. "
            "Use the default dashboard mode for live updates."
        )
        raise typer.Exit(code=0)

    event_log = settings.event_log if replay is None else Path(replay)
    backend_process = None
    backend_lines: list[str] = []

    if command is not None:
        if command not in SCRIPT_TARGETS:
            console.print(f"[red]ERROR:[/red] Unknown command '{command}'")
            raise typer.Exit(code=1)
        backend_process = start_script(settings, command)
        backend_lines.append(f"started backend command: {command}")

    def current_state() -> RenderableType:
        events = load_events(event_log)
        state = reduce_dashboard_state(
            settings,
            events,
            backend_lines=tuple(backend_lines[-12:]),
            forced_command=command,
        )
        return render_dashboard(
            state,
            width=live_render_width(settings, console.size.width),
            height=console.size.height,
        )

    if once:
        console.print(current_state())
        raise typer.Exit(code=0)

    refresh_interval = 1.0 / refresh_hz
    with AtomicLive(
        current_state(),
        console=console,
        screen=True,
        refresh_per_second=refresh_hz,
        auto_refresh=False,
        vertical_overflow="crop",
    ) as live:
        while True:
            if backend_process is not None:
                streams = [
                    stream
                    for stream in (backend_process.stdout, backend_process.stderr)
                    if stream is not None
                ]
                if streams:
                    pump_process_output(backend_process, backend_lines)
                if backend_process.poll() is not None:
                    drain_process_output(backend_process, backend_lines)
                    backend_lines.append(f"backend exit code: {backend_process.returncode}")
                    live.update(current_state(), refresh=True)
                    raise typer.Exit(code=int(backend_process.returncode or 0))

            live.update(current_state(), refresh=True)
            time.sleep(refresh_interval)


@app.command("dashboard")
def dashboard(
    command: Annotated[
        str | None,
        typer.Option(
            "--command",
            help="Optionally launch one backend command inside the dashboard.",
        ),
    ] = None,
    static: Annotated[
        bool,
        typer.Option("--static", help="Render the static dashboard snapshot instead of live mode."),
    ] = False,
    replay: Annotated[
        str | None,
        typer.Option(
            "--replay",
            help="Replay a specific JSONL event log instead of the default live event log.",
        ),
    ] = None,
    once: Annotated[
        bool,
        typer.Option("--once", help="Render a single frame and exit."),
    ] = False,
    refresh_hz: Annotated[
        float,
        typer.Option("--refresh-hz", min=1.0, max=10.0, help="Refresh rate for live mode."),
    ] = 4.0,
) -> None:
    """Render the main operator dashboard."""

    run_dashboard(
        command=command,
        static=static,
        replay=replay,
        once=once,
        refresh_hz=refresh_hz,
    )


@app.command("serve")
def serve(
    host: Annotated[
        str,
        typer.Option("--host", help="Host interface for the browser API."),
    ] = "127.0.0.1",
    port: Annotated[
        int,
        typer.Option("--port", min=1, max=65535, help="Port for the browser API."),
    ] = 8765,
) -> None:
    """Serve the browser-facing API for the React Native UI."""

    import uvicorn

    uvicorn.run("npu_service.web_api:app", host=host, port=port)


@app.command("endurance")
def endurance(
    runs: Annotated[
        int,
        typer.Option("--runs", min=1, help="Number of repeated runs to execute."),
    ] = 5,
    command: Annotated[
        str,
        typer.Option(
            "--command",
            help="Backend command to repeat for endurance validation.",
        ),
    ] = "watch",
    stop_on_failure: Annotated[
        bool,
        typer.Option(
            "--stop-on-failure/--keep-going",
            help="Stop immediately when a run fails.",
        ),
    ] = True,
) -> None:
    """Run repeated backend executions for endurance validation."""

    if command not in SCRIPT_TARGETS:
        console.print(f"[red]ERROR:[/red] Unknown command '{command}'")
        raise typer.Exit(code=1)

    settings = get_settings()
    endurance_dir = settings.artifacts_dir / "endurance"
    endurance_dir.mkdir(parents=True, exist_ok=True)

    completed_runs: list[RunSummary] = []
    backend_lines: list[str] = []
    current_index = 0
    current_process = None
    current_started = 0.0
    current_run_id: str | None = None
    run_id_cursor: set[str] = set()

    def compose_state() -> RenderableType:
        events = load_events(settings.event_log)
        if current_run_id is None:
            selected_run_id = completed_runs[-1].run_id if completed_runs else None
        else:
            selected_run_id = current_run_id
        state = reduce_dashboard_state(
            settings,
            events,
            selected_run_id=selected_run_id,
            backend_lines=tuple(backend_lines[-12:]),
            forced_command=command,
        )
        status = f"endurance {len(completed_runs)}/{runs}"
        if current_process is not None:
            status = f"endurance {current_index}/{runs} running"
        report = build_endurance_report(command, runs, completed_runs)
        notes = (
            f"Completed: {report.completed_runs}/{report.requested_runs}",
            f"Pass/Fail: {report.passed_runs}/{report.failed_runs}",
            f"Mean/Max: {report.mean_duration_seconds:.3f}s / {report.max_duration_seconds:.3f}s",
            f"CPU mem drift: {report.overall_cpu_mem_delta_mib:.1f} MiB",
            "Endurance is dashboard-native in this mode.",
        )
        artifact_rows = tuple(state.artifact_rows) + (
            ("Mean", f"{report.mean_duration_seconds:.3f}s"),
            ("Median", f"{report.median_duration_seconds:.3f}s"),
            ("P95", f"{report.p95_duration_seconds:.3f}s"),
            ("Max", f"{report.max_duration_seconds:.3f}s"),
        )
        return render_dashboard(
            replace(
                state,
                mode="endurance",
                status=status,
                notes=notes,
                artifact_rows=artifact_rows,
            ),
            width=live_render_width(settings, console.size.width),
            height=console.size.height,
        )

    refresh_interval = 0.25
    with AtomicLive(
        compose_state(),
        console=console,
        screen=True,
        refresh_per_second=4,
        auto_refresh=False,
        vertical_overflow="crop",
    ) as live:
        while len(completed_runs) < runs:
            if current_process is None:
                current_index = len(completed_runs) + 1
                backend_lines.append(f"starting run {current_index}/{runs}: {command}")
                current_started = time.perf_counter()
                current_process = start_script(settings, command)
                live.update(compose_state(), refresh=True)

            pump_process_output(current_process, backend_lines)
            events = load_events(settings.event_log)
            if current_run_id is None:
                unseen_run_ids = [
                    event.run_id
                    for event in events
                    if event.run_id.startswith(f"{command}-") and event.run_id not in run_id_cursor
                ]
                if unseen_run_ids:
                    current_run_id = unseen_run_ids[-1]
                    run_id_cursor.add(current_run_id)

            if current_process.poll() is not None:
                drain_process_output(current_process, backend_lines)
                exit_code = int(current_process.returncode or 0)
                duration = round(time.perf_counter() - current_started, 3)
                run_events = load_events(settings.event_log)
                if current_run_id is None:
                    current_run_id = current_run_id or "unknown"
                run_summary = build_run_summary(
                    run_events,
                    run_id=current_run_id,
                    run_number=current_index,
                    command=command,
                    duration_seconds=duration,
                    exit_code=exit_code,
                )
                completed_runs.append(run_summary)
                backend_lines.append(
                    f"completed run {current_index}/{runs}: "
                    f"exit={exit_code} duration={duration:.3f}s"
                )
                current_process = None
                current_run_id = None
                live.update(compose_state(), refresh=True)
                if exit_code != 0 and stop_on_failure:
                    break

            live.update(compose_state(), refresh=True)
            time.sleep(refresh_interval)

    report = build_endurance_report(command, runs, completed_runs)
    report_path = endurance_dir / "latest.json"
    report_path.write_text(
        json.dumps(
            {
                "command": report.command,
                "requested_runs": report.requested_runs,
                "completed_runs": report.completed_runs,
                "passed_runs": report.passed_runs,
                "failed_runs": report.failed_runs,
                "mean_duration_seconds": report.mean_duration_seconds,
                "median_duration_seconds": report.median_duration_seconds,
                "p95_duration_seconds": report.p95_duration_seconds,
                "max_duration_seconds": report.max_duration_seconds,
                "overall_cpu_mem_delta_mib": report.overall_cpu_mem_delta_mib,
                "peak_npu_util_percent": report.peak_npu_util_percent,
                "peak_gpu_util_percent": report.peak_gpu_util_percent,
                "runs": [run.__dict__ for run in report.runs],
            },
            indent=2,
        )
        + "\n"
    )

    table = Table(title="Endurance Summary")
    table.add_column("Run", justify="right")
    table.add_column("Exit", justify="right")
    table.add_column("Seconds", justify="right")
    table.add_column("Peak NPU", justify="right")
    table.add_column("Mem Δ MiB", justify="right")
    for run_summary in completed_runs:
        table.add_row(
            str(run_summary.run_number),
            str(run_summary.exit_code),
            f"{run_summary.duration_seconds:.3f}",
            f"{run_summary.peak_npu_util_percent:.1f}",
            f"{run_summary.cpu_mem_delta_mib:.1f}",
        )
    console.print(table)

    aggregate = Table(title="Aggregate")
    aggregate.add_column("Metric")
    aggregate.add_column("Value", justify="right")
    aggregate.add_row("Requested runs", str(report.requested_runs))
    aggregate.add_row("Completed runs", str(report.completed_runs))
    aggregate.add_row("Passed runs", str(report.passed_runs))
    aggregate.add_row("Failed runs", str(report.failed_runs))
    aggregate.add_row("Mean seconds", f"{report.mean_duration_seconds:.3f}")
    aggregate.add_row("Median seconds", f"{report.median_duration_seconds:.3f}")
    aggregate.add_row("P95 seconds", f"{report.p95_duration_seconds:.3f}")
    aggregate.add_row("Max seconds", f"{report.max_duration_seconds:.3f}")
    aggregate.add_row("Peak NPU", f"{report.peak_npu_util_percent:.1f}%")
    aggregate.add_row("Peak GPU", f"{report.peak_gpu_util_percent:.1f}%")
    aggregate.add_row("CPU mem drift", f"{report.overall_cpu_mem_delta_mib:.1f} MiB")
    aggregate.add_row("Artifact", str(report_path))
    console.print(aggregate)

    if report.failed_runs:
        console.print(f"[red]Endurance failed[/red] after {report.completed_runs} run(s).")
        raise typer.Exit(code=1)
    console.print(f"[green]Endurance passed[/green] for {report.completed_runs} run(s).")
    raise typer.Exit(code=0)


@app.command("status")
def status() -> None:
    """Show the current operator paths and artifacts."""

    settings = get_settings()
    table = Table(title="NPU Console Status")
    table.add_column("Key")
    table.add_column("Value")
    table.add_row("Event log", str(settings.event_log))
    table.add_row("Scripts dir", str(settings.scripts_dir))
    table.add_row("Artifacts dir", str(settings.artifacts_dir))
    for target in SCRIPT_TARGETS.values():
        table.add_row(target.command_name, target.description)
    console.print(table)
