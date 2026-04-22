"""Event log parsing and reduction."""

from __future__ import annotations

import json
from dataclasses import dataclass
from math import ceil
from pathlib import Path
from statistics import mean, median
from typing import Any

from npu_service.core.settings import Settings
from npu_service.ui.dashboard import DashboardState, TrendMetric


@dataclass(frozen=True)
class EventRecord:
    """One parsed event row."""

    raw: dict[str, Any]

    @property
    def ts(self) -> str:
        return str(self.raw["ts"])

    @property
    def run_id(self) -> str:
        return str(self.raw["run_id"])

    @property
    def kind(self) -> str:
        return str(self.raw["kind"])

    @property
    def level(self) -> str:
        return str(self.raw["level"])

    @property
    def module(self) -> str:
        return str(self.raw["module"])

    @property
    def event(self) -> str:
        return str(self.raw["event"])

    @property
    def message(self) -> str:
        return str(self.raw["message"])

    @property
    def data(self) -> dict[str, Any]:
        return dict(self.raw.get("data", {}))


@dataclass(frozen=True)
class RunSummary:
    """Structured summary for one completed run."""

    run_number: int
    run_id: str
    command: str
    exit_code: int
    duration_seconds: float
    phase_pass: bool
    peak_npu_util_percent: float
    peak_npu_util_raw_percent: float
    peak_gpu_util_percent: float
    peak_cpu_percent: float
    peak_cpu_mem_used_mib: float
    start_cpu_mem_used_mib: float
    end_cpu_mem_used_mib: float
    cpu_mem_delta_mib: float
    npu_signal_source: str
    watch_artifact: str | None
    probe_artifact: str | None
    trace_metadata: str | None = None
    etl_path: str | None = None


@dataclass(frozen=True)
class EnduranceReport:
    """Aggregate endurance statistics."""

    command: str
    requested_runs: int
    completed_runs: int
    passed_runs: int
    failed_runs: int
    mean_duration_seconds: float
    median_duration_seconds: float
    p95_duration_seconds: float
    max_duration_seconds: float
    overall_cpu_mem_delta_mib: float
    peak_npu_util_percent: float
    peak_gpu_util_percent: float
    runs: tuple[RunSummary, ...]


def load_events(path: Path) -> list[EventRecord]:
    """Load newline-delimited JSON events."""

    if not path.exists():
        return []
    records: list[EventRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        records.append(EventRecord(json.loads(line)))
    return records


def latest_run_id(events: list[EventRecord]) -> str | None:
    """Return the latest run id if any."""

    if not events:
        return None
    return events[-1].run_id


def latest_summary_event(
    events: list[EventRecord], run_id: str | None = None
) -> EventRecord | None:
    """Return the latest summary event, optionally for one run id."""

    summaries = [event for event in events if event.kind == "summary"]
    if run_id is not None:
        summaries = [event for event in summaries if event.run_id == run_id]
    return summaries[-1] if summaries else None


def p95(values: list[float]) -> float:
    """Compute a simple p95 percentile."""

    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, ceil(len(ordered) * 0.95) - 1)
    return float(ordered[index])


def build_endurance_report(
    command: str, requested_runs: int, runs: list[RunSummary]
) -> EnduranceReport:
    """Build aggregate endurance statistics from per-run summaries."""

    durations = [run.duration_seconds for run in runs]
    completed_runs = len(runs)
    passed_runs = sum(1 for run in runs if run.exit_code == 0 and run.phase_pass)
    failed_runs = completed_runs - passed_runs
    overall_delta = 0.0
    if runs:
        overall_delta = runs[-1].end_cpu_mem_used_mib - runs[0].start_cpu_mem_used_mib
    return EnduranceReport(
        command=command,
        requested_runs=requested_runs,
        completed_runs=completed_runs,
        passed_runs=passed_runs,
        failed_runs=failed_runs,
        mean_duration_seconds=round(mean(durations), 3) if durations else 0.0,
        median_duration_seconds=round(median(durations), 3) if durations else 0.0,
        p95_duration_seconds=round(p95(durations), 3) if durations else 0.0,
        max_duration_seconds=max(durations) if durations else 0.0,
        overall_cpu_mem_delta_mib=round(overall_delta, 1),
        peak_npu_util_percent=max((run.peak_npu_util_percent for run in runs), default=0.0),
        peak_gpu_util_percent=max((run.peak_gpu_util_percent for run in runs), default=0.0),
        runs=tuple(runs),
    )


def build_run_summary(
    events: list[EventRecord],
    run_id: str,
    run_number: int,
    command: str,
    duration_seconds: float,
    exit_code: int,
) -> RunSummary:
    """Build one run summary from the event log."""

    summary_event = latest_summary_event(events, run_id=run_id)
    data = summary_event.data if summary_event else {}
    return RunSummary(
        run_number=run_number,
        run_id=run_id,
        command=command,
        exit_code=exit_code,
        duration_seconds=duration_seconds,
        phase_pass=bool(data.get("probe_phase_pass", exit_code == 0)),
        peak_npu_util_percent=float(data.get("peak_npu_util_percent", 0.0) or 0.0),
        peak_npu_util_raw_percent=float(data.get("peak_npu_util_raw_percent", 0.0) or 0.0),
        peak_gpu_util_percent=float(data.get("peak_gpu_util_percent", 0.0) or 0.0),
        peak_cpu_percent=float(data.get("peak_cpu_percent", 0.0) or 0.0),
        peak_cpu_mem_used_mib=float(data.get("peak_cpu_mem_used_mib", 0.0) or 0.0),
        start_cpu_mem_used_mib=float(data.get("start_cpu_mem_used_mib", 0.0) or 0.0),
        end_cpu_mem_used_mib=float(data.get("end_cpu_mem_used_mib", 0.0) or 0.0),
        cpu_mem_delta_mib=float(data.get("cpu_mem_delta_mib", 0.0) or 0.0),
        npu_signal_source=str(data.get("npu_signal_source", "unspecified")),
        watch_artifact=data.get("watch_artifact"),
        probe_artifact=data.get("probe_artifact"),
        trace_metadata=data.get("trace_metadata"),
        etl_path=data.get("etl_path"),
    )


def reduce_dashboard_state(
    settings: Settings,
    events: list[EventRecord],
    selected_run_id: str | None = None,
    backend_lines: tuple[str, ...] = (),
    forced_command: str | None = None,
) -> DashboardState:
    """Reduce event rows to dashboard state."""

    run_id = selected_run_id or latest_run_id(events) or "idle"
    run_events = [event for event in events if event.run_id == run_id]
    metric_events = [event for event in run_events if event.event == "metric.sample"]
    summary_events = [event for event in run_events if event.kind == "summary"]
    latest_summary = summary_events[-1] if summary_events else None
    latest_metric = metric_events[-1] if metric_events else None

    selected_command = forced_command or run_id.split("-", 1)[0]
    status = "idle"
    if run_events:
        status = "running"
    if latest_summary:
        status = "ok" if bool(latest_summary.data.get("probe_phase_pass", True)) else "error"

    interaction_lines: list[str] = list(backend_lines[-8:])
    for event in run_events[-8:]:
        interaction_lines.append(f"[{event.level}] {event.module}:{event.event} - {event.message}")
    if not interaction_lines:
        interaction_lines = [
            "No live events yet.",
            "",
            "Run one of:",
            "  npu-service watch",
            "  npu-service trace",
            "  npu-service dashboard --command watch",
        ]

    def metric_values(key: str) -> tuple[float, ...]:
        values: list[float] = []
        for event in metric_events:
            value = event.data.get(key)
            if value is None:
                continue
            values.append(float(value))
        return tuple(values)

    npu_values = metric_values("npu_util_percent")
    cpu_values = metric_values("cpu_percent")
    cpu_mem_values = metric_values("cpu_mem_used_mib")
    gpu_values = metric_values("gpu_util_percent")
    gpu_mem_values = metric_values("gpu_mem_mib")

    def trend(label: str, unit: str, values: tuple[float, ...]) -> TrendMetric:
        if not values:
            return TrendMetric(label, unit, (0.0,), 0.0, 0.0)
        return TrendMetric(label, unit, values[-20:], values[-1], max(values))

    artifact_rows = [
        ("Event log", str(settings.event_log)),
        ("Windows root", settings.windows_root),
        ("WSL root", str(settings.wsl_root)),
        ("Run ID", run_id),
    ]
    if latest_metric:
        npu_state = str(latest_metric.data.get("npu_state", "unknown"))
        if latest_summary and npu_state == "unknown":
            peak_npu = float(latest_summary.data.get("peak_npu_util_percent", 0.0) or 0.0)
            if peak_npu > 0:
                npu_state = f"idle (last turn active, peak {peak_npu:.1f}%)"
        artifact_rows.append(("NPU state", npu_state))
        artifact_rows.append(
            ("NPU source", str(latest_metric.data.get("npu_signal_source", "unspecified")))
        )
    if latest_summary:
        for key in ("probe_artifact", "watch_artifact", "trace_metadata", "etl_path"):
            value = latest_summary.data.get(key)
            if value:
                artifact_rows.append((key, str(value)))

    return DashboardState(
        title="NPU Console Dashboard",
        mode="dashboard-live",
        status=status,
        active_model="OpenVINO/TinyLlama-1.1B-Chat-v1.0-int4-ov",
        active_run_id=run_id,
        selected_command=selected_command,
        event_log_path=str(settings.event_log),
        windows_root=settings.windows_root,
        wsl_root=str(settings.wsl_root),
        notes=(
            "Live dashboard is reading structured event rows.",
            "Ctrl+C exits the dashboard loop.",
            "Use --command to launch a backend run from the dashboard.",
        ),
        interaction_lines=tuple(interaction_lines),
        trends=(
            trend("NPU util", "%", npu_values),
            trend("CPU util", "%", cpu_values),
            trend("CPU mem", " MiB", cpu_mem_values),
            trend("GPU util", "%", gpu_values),
            trend("GPU mem", " MiB", gpu_mem_values),
        ),
        artifact_rows=tuple(artifact_rows),
    )
