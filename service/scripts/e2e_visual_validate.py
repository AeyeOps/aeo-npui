#!/usr/bin/env python3
"""Visual + E2E validation for the live NPU dashboard."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import pexpect

ROOT = Path(__file__).resolve().parents[1]
HELPER = Path(__file__).with_name("windows_terminal_driver.ps1")
EVENT_LOG = Path("/mnt/c/dev/npu/scripts/npu-events.jsonl")
ENDURANCE_ARTIFACT = Path("/mnt/c/dev/npu/artifacts/endurance/latest.json")
SCREENSHOT_DELAY_SECONDS = 0.8


class E2EFailure(RuntimeError):
    """Raised when a validation scenario fails."""


@dataclass(frozen=True)
class Settings:
    artifacts_root: Path


def read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def append_note(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(text.rstrip() + "\n")


def wsl_to_windows(path: Path) -> str:
    return subprocess.check_output(["wslpath", "-w", str(path)], text=True).strip()


def pwsh_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def windows_driver(action: str, **kwargs: str | int) -> dict[str, object]:
    command = [
        "pwsh.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        wsl_to_windows(HELPER),
        "-Action",
        action,
    ]
    for key, value in kwargs.items():
        if value is None:
            continue
        command.extend([f"-{key}", str(value)])
    result = subprocess.run(command, check=False, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        raise E2EFailure(
            f"Windows helper failed for {action}: exit={result.returncode} stderr={result.stderr}"
        )
    output = result.stdout.strip()
    return json.loads(output) if output else {}


def wait_for(predicate, timeout: float, message: str):
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.2)
    raise E2EFailure(message)


def wait_startup_ready(startup_artifact: Path, timeout: float = 120.0) -> None:
    def predicate() -> bool:
        if not startup_artifact.exists():
            return False
        text = startup_artifact.read_text(encoding="utf-8").strip()
        if text == "ok":
            return True
        if text and text != "starting":
            raise E2EFailure(f"Startup artifact reported failure: {text}")
        return False

    wait_for(predicate, timeout, "Timed out waiting for startup-last.txt to report ok")


def build_dashboard_command(arguments: list[str], startup_artifact: Path, debug_log: Path) -> str:
    command = " ".join(arg if arg.isalnum() or arg.startswith("--") else pwsh_quote(arg) for arg in arguments)
    return (
        "wsl.exe -d Ubuntu-22.04 --cd /opt/aeo/aeo-infra/npu/console "
        f"env NPU_CONSOLE_DASHBOARD_CAPTURE_METRICS=1 "
        f"NPU_CONSOLE_CHAT_STARTUP_ARTIFACT_OVERRIDE={startup_artifact} "
        f"NPU_CONSOLE_DASHBOARD_UI_LOG_OVERRIDE={debug_log} "
        f"uv run npu-service {command}"
    )


@dataclass
class VisualSession:
    title: str
    arguments: list[str]
    scenario_dir: Path

    def __post_init__(self) -> None:
        self.event_baseline = len(read_jsonl(EVENT_LOG))
        self.debug_cursor = 0
        self.startup_artifact = self.scenario_dir / "startup-last.txt"
        self.debug_log = self.scenario_dir / "dashboard-ui.jsonl"

    def open(self) -> None:
        self.scenario_dir.mkdir(parents=True, exist_ok=True)
        if self.startup_artifact.exists():
            self.startup_artifact.unlink()
        if self.debug_log.exists():
            self.debug_log.unlink()
        windows_driver(
            "open-tab",
            Title=self.title,
            StartingDirectory="C:\\dev\\npu",
            TimeoutSeconds=30,
        )
        metadata = windows_driver("metadata")
        (self.scenario_dir / "metadata.json").write_text(
            json.dumps(metadata, indent=2) + "\n",
            encoding="utf-8",
        )
        self.send_line(build_dashboard_command(self.arguments, self.startup_artifact, self.debug_log))
        time.sleep(SCREENSHOT_DELAY_SECONDS)

    def capture(self, name: str) -> Path:
        output = self.scenario_dir / f"{name}.png"
        windows_driver("capture-screen", OutputPath=wsl_to_windows(output))
        return output

    def send_text(self, text: str) -> None:
        windows_driver("send-text", Title=self.title, Text=text, TimeoutSeconds=15)
        time.sleep(0.4)

    def send_key(self, keys: str) -> None:
        windows_driver("send-key", Title=self.title, Keys=keys, TimeoutSeconds=15)
        time.sleep(0.4)

    def send_line(self, text: str) -> None:
        self.send_text(text)
        self.send_key("{ENTER}")

    def wait_for_debug(
        self,
        event_name: str,
        predicate,
        timeout: float = 60.0,
    ) -> dict[str, object]:
        def inner() -> dict[str, object] | None:
            rows = read_jsonl(self.debug_log)
            for index in range(self.debug_cursor, len(rows)):
                row = rows[index]
                if row.get("event") != event_name:
                    continue
                if predicate(row):
                    self.debug_cursor = index + 1
                    return row
            return None

        return wait_for(
            inner,
            timeout,
            f"Timed out waiting for dashboard debug event {event_name!r}",
        )

    def wait_for_zero_wrap_frame(self, timeout: float = 30.0) -> dict[str, object]:
        return self.wait_for_debug(
            "frame.rendered",
            lambda row: int(row["data"]["raw_width"]) - int(row["data"]["max_line_length"]) >= 2,
            timeout=timeout,
        )

    def finalize(self) -> None:
        event_rows = read_jsonl(EVENT_LOG)[self.event_baseline :]
        event_slice = self.scenario_dir / "npu-events.slice.jsonl"
        event_slice.write_text(
            "".join(json.dumps(row, ensure_ascii=True) + "\n" for row in event_rows),
            encoding="utf-8",
        )
        try:
            windows_driver("close-tab", Title=self.title, TimeoutSeconds=5)
        except E2EFailure:
            # The tab may already have exited after /quit.
            pass


def run_pty_wrapper_quit(artifact_dir: Path) -> None:
    transcript = artifact_dir / "pty-wrapper-quit.txt"
    command = (
        "$env:NPU_CONSOLE_DASHBOARD_CAPTURE_METRICS='1'; "
        "& 'C:\\dev\\npu\\scripts\\npu-service.ps1' dashboard"
    )
    child = pexpect.spawn(
        "pwsh.exe",
        ["-NoProfile", "-Command", command],
        cwd=str(ROOT),
        encoding="utf-8",
        timeout=180,
        env={
            **os.environ,
            "TERM": "xterm-256color",
            "PATH": os.environ.get("PATH", ""),
            "NPU_CONSOLE_DASHBOARD_CAPTURE_METRICS": "1",
        },
    )
    with transcript.open("w", encoding="utf-8") as handle:
        child.logfile_read = handle
        child.expect("Chat With Local NPU")
        wait_startup_ready()
        child.send("/quit")
        child.send("\r")
        child.expect(pexpect.EOF, timeout=60)


def scenario_startup_width_and_quit(settings: Settings) -> None:
    scenario_dir = settings.artifacts_root / "01_startup_width_and_quit"
    session = VisualSession(f"Codex NPU Startup {settings.artifacts_root.name}", ["dashboard"], scenario_dir)
    session.open()
    try:
        session.capture("startup")
        wait_startup_ready()
        frame = session.wait_for_zero_wrap_frame()
        (scenario_dir / "frame-zero-wrap.json").write_text(
            json.dumps(frame, indent=2) + "\n",
            encoding="utf-8",
        )
        session.capture("ready")
        session.send_line("/quit")
        session.wait_for_debug("command.quit", lambda _row: True, timeout=20)
    finally:
        session.finalize()


def scenario_typing_and_single_turn(settings: Settings) -> None:
    scenario_dir = settings.artifacts_root / "02_typing_and_single_turn"
    session = VisualSession(f"Codex NPU Typing {settings.artifacts_root.name}", ["dashboard"], scenario_dir)
    session.open()
    try:
        wait_startup_ready()
        session.wait_for_zero_wrap_frame()
        session.send_text("abcdefghij")
        session.capture("typing-buffer")
        session.send_key("{ENTER}")
        turn_started = session.wait_for_debug(
            "turn.started",
            lambda row: row["data"].get("user_text") == "abcdefghij"
            and "User: abcdefghij" in str(row["data"].get("prompt", "")),
            timeout=30,
        )
        (scenario_dir / "turn-started.json").write_text(
            json.dumps(turn_started, indent=2) + "\n",
            encoding="utf-8",
        )
        turn_completed = session.wait_for_debug(
            "turn.completed",
            lambda _row: True,
            timeout=120,
        )
        (scenario_dir / "turn-completed.json").write_text(
            json.dumps(turn_completed, indent=2) + "\n",
            encoding="utf-8",
        )
        session.capture("after-turn")
        session.send_line("/quit")
        session.wait_for_debug("command.quit", lambda _row: True, timeout=20)
    finally:
        session.finalize()


def scenario_continuity_and_clear(settings: Settings) -> None:
    scenario_dir = settings.artifacts_root / "03_continuity_and_clear"
    session = VisualSession(
        f"Codex NPU Continuity {settings.artifacts_root.name}",
        ["dashboard"],
        scenario_dir,
    )
    run_ids: list[str] = []
    session.open()
    try:
        wait_startup_ready()
        session.wait_for_zero_wrap_frame()

        session.send_line("hello")
        first_started = session.wait_for_debug(
            "turn.started",
            lambda row: row["data"].get("user_text") == "hello"
            and "User: hello" in str(row["data"].get("prompt", "")),
            timeout=30,
        )
        first_completed = session.wait_for_debug("turn.completed", lambda _row: True, timeout=120)
        run_ids.append(str(first_completed["data"]["run_id"]))

        session.send_line("what did i just say?")
        second_started = session.wait_for_debug(
            "turn.started",
            lambda row: row["data"].get("user_text") == "what did i just say?"
            and "User: hello" in str(row["data"].get("prompt", ""))
            and "User: what did i just say?" in str(row["data"].get("prompt", "")),
            timeout=30,
        )
        second_completed = session.wait_for_debug("turn.completed", lambda _row: True, timeout=120)
        run_ids.append(str(second_completed["data"]["run_id"]))
        session.capture("multi-turn")

        session.send_line("/clear")
        session.wait_for_debug("command.clear", lambda _row: True, timeout=20)

        session.send_line("new topic")
        clear_started = session.wait_for_debug(
            "turn.started",
            lambda row: row["data"].get("user_text") == "new topic"
            and "User: new topic" in str(row["data"].get("prompt", ""))
            and "User: hello" not in str(row["data"].get("prompt", "")),
            timeout=30,
        )
        clear_completed = session.wait_for_debug("turn.completed", lambda _row: True, timeout=120)
        run_ids.append(str(clear_completed["data"]["run_id"]))
        session.capture("after-clear")

        if len(set(run_ids)) != 1:
            raise E2EFailure(f"Expected one persistent run_id across turns, got {run_ids}")

        (scenario_dir / "turns.json").write_text(
            json.dumps(
                {
                    "first_started": first_started,
                    "second_started": second_started,
                    "clear_started": clear_started,
                    "run_ids": run_ids,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        session.send_line("/quit")
        session.wait_for_debug("command.quit", lambda _row: True, timeout=20)
    finally:
        session.finalize()


def scenario_log_view_and_follow(settings: Settings) -> None:
    scenario_dir = settings.artifacts_root / "04_log_view_and_follow"
    session = VisualSession(
        f"Codex NPU Log View {settings.artifacts_root.name}",
        ["dashboard"],
        scenario_dir,
    )
    session.open()
    try:
        wait_startup_ready()
        session.wait_for_zero_wrap_frame()
        session.send_line("/view log")
        session.wait_for_debug(
            "command.view",
            lambda row: row["data"].get("selected") == "log",
            timeout=20,
        )
        session.capture("log-view")

        session.send_text("f")
        session.wait_for_debug(
            "log.follow_toggled",
            lambda row: row["data"].get("log_follow") is False,
            timeout=20,
        )
        session.capture("follow-off")

        session.send_key("{PGDN}")
        session.wait_for_debug(
            "log.scroll",
            lambda row: row["data"].get("direction") == "page_down",
            timeout=20,
        )

        session.send_text("f")
        session.wait_for_debug(
            "log.follow_toggled",
            lambda row: row["data"].get("log_follow") is True,
            timeout=20,
        )
        session.capture("follow-on")

        session.send_line("/quit")
        session.wait_for_debug("command.quit", lambda _row: True, timeout=20)
    finally:
        session.finalize()


def scenario_endurance(settings: Settings) -> None:
    scenario_dir = settings.artifacts_root / "05_endurance"
    baseline_mtime = ENDURANCE_ARTIFACT.stat().st_mtime if ENDURANCE_ARTIFACT.exists() else 0.0
    session = VisualSession(
        f"Codex NPU Endurance {settings.artifacts_root.name}",
        ["endurance", "--runs", "3", "--command", "watch"],
        scenario_dir,
    )
    session.open()
    try:
        time.sleep(3)
        session.capture("endurance-running")

        def predicate() -> Path | None:
            if ENDURANCE_ARTIFACT.exists() and ENDURANCE_ARTIFACT.stat().st_mtime > baseline_mtime:
                return ENDURANCE_ARTIFACT
            return None

        wait_for(predicate, 420, "Timed out waiting for endurance/latest.json")
        session.capture("endurance-summary")
        shutil.copy2(ENDURANCE_ARTIFACT, scenario_dir / ENDURANCE_ARTIFACT.name)
    finally:
        session.finalize()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Visual + E2E validation for the NPU dashboard.")
    parser.add_argument(
        "--scenario",
        action="append",
        choices=("startup", "typing", "continuity", "log", "endurance", "pty"),
        help="Run only the named scenario. Defaults to the full suite.",
    )
    parser.add_argument(
        "--artifact-root",
        default=None,
        help="Override the artifact directory root. Defaults to /mnt/c/dev/npu/artifacts/e2e/<timestamp>.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    artifact_root = (
        Path(args.artifact_root)
        if args.artifact_root
        else Path("/mnt/c/dev/npu/artifacts/e2e") / timestamp
    )
    settings = Settings(artifacts_root=artifact_root)
    settings.artifacts_root.mkdir(parents=True, exist_ok=True)

    scenario_map = {
        "startup": scenario_startup_width_and_quit,
        "typing": scenario_typing_and_single_turn,
        "continuity": scenario_continuity_and_clear,
        "log": scenario_log_view_and_follow,
        "endurance": scenario_endurance,
        "pty": lambda cfg: run_pty_wrapper_quit(cfg.artifacts_root / "06_pty_wrapper_quit"),
    }
    selected = args.scenario or ["startup", "typing", "continuity", "log", "endurance", "pty"]

    started = time.perf_counter()
    for name in selected:
        print(f"[run] {name}", flush=True)
        scenario_start = time.perf_counter()
        scenario_map[name](settings)
        duration = time.perf_counter() - scenario_start
        print(f"[ok] {name} {duration:.2f}s", flush=True)

    total = time.perf_counter() - started
    print(f"[ok] e2e_visual_validate total {total:.2f}s", flush=True)
    print(f"[artifacts] {settings.artifacts_root}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
