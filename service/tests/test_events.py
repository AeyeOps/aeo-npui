"""Event reduction and replay tests."""

from pathlib import Path

from npu_service.core.events import (
    build_endurance_report,
    build_run_summary,
    load_events,
    reduce_dashboard_state,
)
from npu_service.core.settings import load_settings

FIXTURE = Path(__file__).with_name("fixtures").joinpath("events_sample.jsonl")


def test_load_events_fixture() -> None:
    events = load_events(FIXTURE)
    assert len(events) == 4
    assert events[-1].event == "watch.summary"


def test_reduce_dashboard_state_uses_latest_run() -> None:
    state = reduce_dashboard_state(load_settings(), load_events(FIXTURE))
    assert state.active_run_id == "watch-20260320T220638Z"
    assert state.selected_command == "watch"
    assert state.status == "ok"
    assert state.trends[0].peak == 91.0
    assert ("NPU source", "gpu_engine_luid_inference") in state.artifact_rows


def test_build_run_summary_uses_summary_fields() -> None:
    events = load_events(FIXTURE)
    summary = build_run_summary(
        events,
        run_id="watch-20260320T220638Z",
        run_number=1,
        command="watch",
        duration_seconds=20.5,
        exit_code=0,
    )
    assert summary.peak_npu_util_percent == 91.0
    assert summary.peak_npu_util_raw_percent == 104.0
    assert summary.cpu_mem_delta_mib == 126.2
    assert summary.npu_signal_source == "gpu_engine_luid_inference"


def test_build_endurance_report_aggregates_runs() -> None:
    events = load_events(FIXTURE)
    runs = [
        build_run_summary(events, "watch-20260320T220638Z", 1, "watch", 20.5, 0),
        build_run_summary(events, "watch-20260320T220638Z", 2, "watch", 19.5, 0),
    ]
    report = build_endurance_report("watch", 2, runs)
    assert report.completed_runs == 2
    assert report.failed_runs == 0
    assert report.mean_duration_seconds == 20.0
    assert report.p95_duration_seconds == 20.5
