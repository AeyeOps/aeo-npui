"""Backend script runners for the NPU console."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from npu_service.core.settings import Settings


class RunnerError(Exception):
    """Raised when the Windows-backed runner cannot be invoked."""


@dataclass(frozen=True)
class ScriptTarget:
    """A named backend script."""

    command_name: str
    script_name: str
    description: str


SCRIPT_TARGETS: dict[str, ScriptTarget] = {
    "phase-zero": ScriptTarget("phase-zero", "run_phase_zero.sh", "Raw NPU access proof"),
    "run": ScriptTarget("run", "run_llm_probe.sh", "Actual local LLM generation on NPU"),
    "watch": ScriptTarget("watch", "run_llm_probe_watch.sh", "LLM generation with live metrics"),
    "trace": ScriptTarget(
        "trace", "run_llm_probe_trace.sh", "LLM generation with WPR NeuralProcessing trace"
    ),
}


def resolve_script(settings: Settings, command_name: str) -> Path:
    """Resolve a backend script path."""

    target = SCRIPT_TARGETS[command_name]
    script_path = settings.scripts_dir / target.script_name
    if not script_path.exists():
        raise RunnerError(f"Backend script not found: {script_path}")
    return script_path


def run_script(settings: Settings, command_name: str) -> int:
    """Run a backend script and return its exit code."""

    script_path = resolve_script(settings, command_name)
    result = subprocess.run([str(script_path)], check=False)
    return int(result.returncode)


def start_script(settings: Settings, command_name: str) -> subprocess.Popen[str]:
    """Start a backend script with captured stdout/stderr."""

    script_path = resolve_script(settings, command_name)
    return subprocess.Popen(
        [str(script_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
