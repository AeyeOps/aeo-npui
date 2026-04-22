"""Chat turn execution against the Windows NPU backend."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from npu_service.core.events import latest_run_id, load_events
from npu_service.core.settings import Settings


class ChatTurnError(Exception):
    """Raised when a chat turn cannot be completed."""


class ChatSessionError(Exception):
    """Raised when the persistent chat session cannot be started."""


@dataclass(frozen=True)
class ChatMessage:
    """One chat transcript item."""

    role: str
    content: str


@dataclass(frozen=True)
class ChatTurnResult:
    """Structured result from one backend-backed chat turn."""

    prompt: str
    response_text: str
    run_id: str
    exit_code: int
    generate_seconds: float
    load_seconds: float
    peak_npu_util_percent: float
    cpu_mem_delta_mib: float
    phase_pass: bool
    watch_artifact: str | None
    probe_artifact: str | None
    stdout: str
    stderr: str


SYSTEM_PROMPT = (
    "You are a helpful conversational assistant running locally on an Intel NPU. "
    "Respond in clear English, stay on the user's topic, and preserve conversation continuity "
    "across turns. If the user greets you, greet them naturally and briefly."
)


@dataclass
class ChatSession:
    """Persistent chat session state."""

    run_id: str
    process: subprocess.Popen[str]
    monitor: subprocess.Popen[str]
    load_seconds: float
    worker_pid: int
    model_dir: str


def build_prompt(history: list[ChatMessage], user_message: str, max_turns: int = 6) -> str:
    """Build a simple rolling prompt from recent history."""

    recent = [
        message
        for message in history[-max_turns:]
        if not message.content.startswith("You are chatting")
    ]
    parts = [f"System: {SYSTEM_PROMPT}"]
    for message in recent:
        prefix = "User" if message.role == "user" else "Assistant"
        parts.append(f"{prefix}: {message.content}")
    parts.append(f"User: {user_message}")
    parts.append("Assistant:")
    return "\n".join(parts)


def run_chat_turn(settings: Settings, prompt: str) -> ChatTurnResult:
    """Run one watch-backed chat turn on the Windows NPU path."""

    event_log = settings.event_log
    before_events = load_events(event_log)
    previous_run_id = latest_run_id(before_events)
    script_path = f"{settings.windows_root}\\scripts\\watch_llm_probe.ps1"

    result = subprocess.run(
        [
            "pwsh.exe",
            "-NoProfile",
            "-File",
            script_path,
            "-RootDir",
            settings.windows_root,
            "-Prompt",
            prompt,
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    after_events = load_events(event_log)
    new_run_ids = [event.run_id for event in after_events if event.run_id != previous_run_id]
    run_id = new_run_ids[-1] if new_run_ids else (latest_run_id(after_events) or "unknown")

    watch_path = settings.artifacts_dir / "watch" / "latest.json"
    if not watch_path.exists():
        raise ChatTurnError("Missing latest watch artifact after chat turn")

    watch_data = json.loads(watch_path.read_text(encoding="utf-8"))
    probe_artifact = watch_data.get("ProbeArtifact") or watch_data.get("probe_artifact")
    if not probe_artifact:
        raise ChatTurnError("Watch artifact did not record a probe artifact path")
    probe_path_str = str(probe_artifact).replace("\\", "/")
    if len(probe_path_str) >= 2 and probe_path_str[1] == ":":
        drive = probe_path_str[0].lower()
        relative = probe_path_str[2:].lstrip("/")
        llm_path = Path("/mnt") / drive / relative
    else:
        llm_path = Path(probe_path_str)

    if not llm_path.exists():
        raise ChatTurnError(f"Missing run-specific llm-probe artifact after chat turn: {llm_path}")

    llm_data = json.loads(llm_path.read_text(encoding="utf-8"))
    watch_artifact = str(watch_path)
    watch_summary = watch_data

    return ChatTurnResult(
        prompt=prompt,
        response_text=str(llm_data.get("response_text", "")),
        run_id=run_id,
        exit_code=int(result.returncode),
        generate_seconds=float(llm_data.get("generate_seconds", 0.0) or 0.0),
        load_seconds=float(llm_data.get("load_seconds", 0.0) or 0.0),
        peak_npu_util_percent=float(watch_summary.get("PeakNpuUtilPercent", 0.0) or 0.0),
        cpu_mem_delta_mib=float(watch_summary.get("CpuMemDeltaMiB", 0.0) or 0.0),
        phase_pass=bool(watch_summary.get("ProbePhasePass", result.returncode == 0)),
        watch_artifact=watch_artifact,
        probe_artifact=str(llm_path),
        stdout=result.stdout,
        stderr=result.stderr,
    )


def _parse_json_line(line: str) -> dict[str, object]:
    return json.loads(line)


def _payload_str(payload: dict[str, object], key: str, default: str = "") -> str:
    value = payload.get(key, default)
    return str(value)


def _payload_int(payload: dict[str, object], key: str, default: int = 0) -> int:
    value = payload.get(key, default)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return int(str(value))


def _payload_float(payload: dict[str, object], key: str, default: float = 0.0) -> float:
    value = payload.get(key, default)
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    return float(str(value))


def cleanup_stale_chat_processes(settings: Settings) -> None:
    """Kill stale Windows chat worker and monitor processes."""

    root = settings.windows_root.replace("\\", "\\\\")
    script = (
        "$patterns = @("
        f"'{root}\\\\scripts\\\\openvino_genai_chat_worker.py',"
        f"'{root}\\\\scripts\\\\monitor_npu_worker.ps1',"
        f"'{root}\\\\scripts\\\\start_chat_worker.ps1'"
        "); "
        "Get-CimInstance Win32_Process | "
        "Where-Object { "
        "$cmd = $_.CommandLine; "
        "$null -ne $cmd -and ($patterns | Where-Object { $cmd -like ('*' + $_ + '*') }) "
        "} | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    )
    subprocess.run(
        ["pwsh.exe", "-NoProfile", "-Command", script],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def start_chat_session(settings: Settings) -> ChatSession:
    """Start a persistent Windows-side chat worker and monitor."""

    cleanup_stale_chat_processes(settings)
    run_id = "chat-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    worker_script = f"{settings.windows_root}\\scripts\\start_chat_worker.ps1"
    process = subprocess.Popen(
        [
            "pwsh.exe",
            "-NoProfile",
            "-File",
            worker_script,
            "-RootDir",
            settings.windows_root,
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    if process.stdout is None:
        raise ChatSessionError("Chat worker stdout pipe is unavailable")
    ready_line = process.stdout.readline()
    if not ready_line:
        stderr = process.stderr.read() if process.stderr else ""
        raise ChatSessionError(f"Chat worker failed to start: {stderr}")
    payload = _parse_json_line(ready_line)
    if payload.get("type") != "ready":
        raise ChatSessionError(f"Unexpected worker bootstrap payload: {payload}")

    monitor_script = f"{settings.windows_root}\\scripts\\monitor_npu_worker.ps1"
    monitor = subprocess.Popen(
        [
            "pwsh.exe",
            "-NoProfile",
            "-File",
            monitor_script,
            "-RootDir",
            settings.windows_root,
            "-RunId",
            run_id,
            "-TargetProcessId",
            str(_payload_int(payload, "worker_pid")),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return ChatSession(
        run_id=run_id,
        process=process,
        monitor=monitor,
        load_seconds=_payload_float(payload, "load_seconds"),
        worker_pid=_payload_int(payload, "worker_pid"),
        model_dir=_payload_str(payload, "model_dir"),
    )


def send_chat_turn(session: ChatSession, settings: Settings, prompt: str) -> ChatTurnResult:
    """Send one turn through the persistent worker."""

    if session.process.stdin is None or session.process.stdout is None:
        raise ChatTurnError("Chat session pipes are unavailable")

    payload = {"type": "generate", "prompt": prompt}
    session.process.stdin.write(json.dumps(payload) + "\n")
    session.process.stdin.flush()

    line = session.process.stdout.readline()
    if not line:
        stderr = session.process.stderr.read() if session.process.stderr else ""
        raise ChatTurnError(f"Chat worker terminated unexpectedly: {stderr}")
    result = _parse_json_line(line)
    if result.get("type") != "result":
        raise ChatTurnError(f"Unexpected worker result payload: {result}")

    events = load_events(settings.event_log)
    summary = next(
        (
            event
            for event in reversed(events)
            if event.run_id == session.run_id and event.event == "metric.sample"
        ),
        None,
    )
    latest_run_events = [event for event in events if event.run_id == session.run_id]
    peak_npu = 0.0
    if latest_run_events:
        peak_npu = max(
            float(event.data.get("npu_util_percent", 0.0) or 0.0)
            for event in latest_run_events
            if event.event == "metric.sample"
        )

    return ChatTurnResult(
        prompt=prompt,
        response_text=_payload_str(result, "response_text"),
        run_id=session.run_id,
        exit_code=0,
        generate_seconds=_payload_float(result, "generate_seconds"),
        load_seconds=session.load_seconds,
        peak_npu_util_percent=peak_npu,
        cpu_mem_delta_mib=float(summary.data.get("cpu_mem_delta_mib", 0.0) or 0.0)
        if summary
        else 0.0,
        phase_pass=True,
        watch_artifact=None,
        probe_artifact=None,
        stdout="",
        stderr="",
    )


def stop_chat_session(session: ChatSession) -> None:
    """Stop the persistent worker and monitor."""

    if session.process.stdin is not None:
        try:
            session.process.stdin.write(json.dumps({"type": "shutdown"}) + "\n")
            session.process.stdin.flush()
        except BrokenPipeError:
            pass
    try:
        session.process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        session.process.kill()
    try:
        session.monitor.wait(timeout=5)
    except subprocess.TimeoutExpired:
        session.monitor.kill()
