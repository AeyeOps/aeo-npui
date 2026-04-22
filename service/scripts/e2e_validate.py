#!/usr/bin/env python3
"""E2E validation for the live NPU dashboard."""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path

import pexpect

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / ".venv" / "bin" / "npu-service"
EVENT_LOG = Path("/mnt/c/dev/npu/scripts/npu-events.jsonl")
WATCH_DIR = Path("/mnt/c/dev/npu/artifacts/watch")
CHAT_STARTUP = Path("/mnt/c/dev/npu/artifacts/chat/startup-last.txt")


class E2EFailure(RuntimeError):
    """Raised when an E2E scenario fails."""


def latest_watch_start_prompt() -> str:
    rows = [
        json.loads(line)
        for line in EVENT_LOG.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    starts = [row for row in rows if row.get("event") == "watch.start"]
    if not starts:
        raise E2EFailure("No watch.start event found")
    return str(starts[-1]["data"]["prompt"])


def latest_watch_artifact() -> dict[str, object]:
    latest = WATCH_DIR / "latest.json"
    if not latest.exists():
        raise E2EFailure("Missing latest watch artifact")
    return json.loads(latest.read_text(encoding="utf-8"))


def spawn_dashboard(command: list[str]) -> pexpect.spawn:
    executable = command[0]
    if executable == "uv":
        raise E2EFailure("spawn_dashboard should use the concrete npu-service executable, not uv")
    child = pexpect.spawn(
        executable,
        command[1:],
        cwd=str(ROOT),
        encoding="utf-8",
        timeout=180,
        env={**os.environ, "TERM": "xterm-256color", "PATH": os.environ.get("PATH", "")},
    )
    return child


def wait_ready(child: pexpect.spawn) -> None:
    child.expect("Chat With Local NPU")


def wait_prompt(child: pexpect.spawn) -> None:
    child.expect("  > ")


def wait_session_loaded(child: pexpect.spawn) -> None:
    deadline = time.time() + 120
    while time.time() < deadline:
        if CHAT_STARTUP.exists():
            state = CHAT_STARTUP.read_text(encoding="utf-8").strip()
            if state == "ok":
                return
            if state.startswith("Exception") or state.startswith("ChatSessionError"):
                raise E2EFailure(f"Startup artifact reported failure: {state}")
        time.sleep(0.2)
    raise E2EFailure("Timed out waiting for startup artifact to report success")


def send_line(child: pexpect.spawn, text: str) -> None:
    child.send(text)
    child.send("\r")


def wait_output_contains(child: pexpect.spawn, needle: str, timeout: float = 10.0) -> None:
    """Poll the PTY output until a substring appears."""

    deadline = time.time() + timeout
    seen = ""
    while time.time() < deadline:
        try:
            chunk = child.read_nonblocking(size=4096, timeout=0.2)
        except pexpect.TIMEOUT:
            continue
        except pexpect.EOF as exc:
            raise E2EFailure(f"Process exited before output contained {needle!r}") from exc
        seen += chunk
        if needle in seen:
            return
    raise E2EFailure(f"Timed out waiting for output containing {needle!r}")


def expect_turn_complete(child: pexpect.spawn) -> None:
    child.expect(re.compile(r"Last turn completed in .*peak NPU"))


def shutdown(child: pexpect.spawn) -> None:
    child.close(force=True)


def scenario_startup_and_quit() -> None:
    child = spawn_dashboard([str(CLI), "dashboard"])
    wait_ready(child)
    wait_prompt(child)
    shutdown(child)


def scenario_non_tty_quit_command() -> None:
    result = subprocess.run(
        [str(CLI), "dashboard"],
        cwd=str(ROOT),
        input="/quit\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        env={**os.environ, "TERM": "xterm-256color"},
    )
    if result.returncode != 0:
        raise E2EFailure(f"Non-TTY /quit exited with {result.returncode}: {result.stderr}")


def scenario_typing_fidelity() -> None:
    child = spawn_dashboard([str(CLI), "dashboard"])
    wait_session_loaded(child)
    child.send("abcdefghij")
    wait_output_contains(child, "abcdefghij", timeout=10.0)
    shutdown(child)


def scenario_single_turn_prompt_alignment() -> None:
    child = spawn_dashboard([str(CLI), "dashboard"])
    wait_session_loaded(child)
    send_line(child, "hi")
    expect_turn_complete(child)
    shutdown(child)
    prompt = latest_watch_start_prompt()
    if "User: hi" not in prompt:
        raise E2EFailure(f"Prompt did not contain latest user turn: {prompt!r}")


def scenario_multi_turn_continuity() -> None:
    child = spawn_dashboard([str(CLI), "dashboard"])
    wait_session_loaded(child)
    send_line(child, "hello")
    expect_turn_complete(child)
    wait_prompt(child)
    send_line(child, "what did i just say?")
    expect_turn_complete(child)
    shutdown(child)
    prompt = latest_watch_start_prompt()
    if "User: hello" not in prompt or "User: what did i just say?" not in prompt:
        raise E2EFailure(f"Conversation continuity missing from prompt: {prompt!r}")


def scenario_clear_resets_conversation() -> None:
    child = spawn_dashboard([str(CLI), "dashboard"])
    wait_session_loaded(child)
    send_line(child, "hello")
    expect_turn_complete(child)
    wait_prompt(child)
    send_line(child, "/clear")
    child.expect("Conversation cleared")
    wait_prompt(child)
    send_line(child, "new topic")
    expect_turn_complete(child)
    shutdown(child)
    prompt = latest_watch_start_prompt()
    if "User: hello" in prompt:
        raise E2EFailure(f"Cleared conversation leaked previous history: {prompt!r}")
    if "User: new topic" not in prompt:
        raise E2EFailure(f"New post-clear prompt missing: {prompt!r}")


def scenario_log_view_follow_toggle() -> None:
    child = spawn_dashboard([str(CLI), "dashboard"])
    wait_session_loaded(child)
    send_line(child, "/view log")
    child.expect("Run Log")
    child.expect("Follow: ON")
    child.send("f")
    child.expect("Follow: OFF")
    shutdown(child)


def scenario_windows_wrapper_startup() -> None:
    child = spawn_dashboard(
        [
            "pwsh.exe",
            "-NoProfile",
            "-Command",
            "& 'C:\\dev\\npu\\scripts\\npu-service.ps1' dashboard",
        ]
    )
    wait_ready(child)
    shutdown(child)


def scenario_endurance_summary() -> None:
    child = spawn_dashboard([str(CLI), "endurance", "--runs", "2", "--command", "watch"])
    child.expect("Endurance Summary", timeout=240)
    child.expect("Aggregate")
    child.expect("Endurance passed for 2 run\\(s\\)\\.")
    child.expect(pexpect.EOF)


def main() -> int:
    scenarios = [
        ("startup_and_quit", scenario_startup_and_quit),
        ("non_tty_quit_command", scenario_non_tty_quit_command),
        ("typing_fidelity", scenario_typing_fidelity),
        ("single_turn_prompt_alignment", scenario_single_turn_prompt_alignment),
        ("multi_turn_continuity", scenario_multi_turn_continuity),
        ("clear_resets_conversation", scenario_clear_resets_conversation),
        ("log_view_follow_toggle", scenario_log_view_follow_toggle),
        ("windows_wrapper_startup", scenario_windows_wrapper_startup),
        ("endurance_summary", scenario_endurance_summary),
    ]
    started = time.perf_counter()
    for name, fn in scenarios:
        print(f"[run] {name}", flush=True)
        scenario_start = time.perf_counter()
        fn()
        duration = time.perf_counter() - scenario_start
        print(f"[ok] {name} {duration:.2f}s", flush=True)
    total = time.perf_counter() - started
    print(f"[ok] e2e_validate total {total:.2f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
