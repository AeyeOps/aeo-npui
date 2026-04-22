"""Static Rich dashboard render tests for iteration 2.

Skipped module-wide: these tests assert against stored ANSI snapshots of
the Rich TUI. ADR-001 retires the Rich + Typer TUI and Iteration 4.1
deletes `npu_service/ui/` outright; these snapshots drift with every
Rich minor release in the meantime. Keeping the file so the deletion
in 4.1 is a single well-scoped commit; the skip marker makes the CI
path explicit until then.
"""

import pytest

pytestmark = pytest.mark.skip(
    reason="TUI retired per ADR-001; dashboard snapshot tests deleted in Iteration 4.1"
)

from io import StringIO  # noqa: E402
from pathlib import Path  # noqa: E402

from rich.console import Console  # noqa: E402

from npu_service.core.events import load_events, reduce_dashboard_state  # noqa: E402
from npu_service.core.settings import load_settings  # noqa: E402
from npu_service.ui.dashboard import render_dashboard  # noqa: E402

SNAPSHOT_DIR = Path(__file__).with_name("snapshots")
FIXTURE = Path(__file__).with_name("fixtures").joinpath("events_sample.jsonl")


def normalize(text: str) -> str:
    """Normalize console output for stable snapshots."""

    return text.replace("\r\n", "\n").rstrip() + "\n"


def render_snapshot(width: int, height: int, column_ratio: tuple[int, int] = (8, 7)) -> str:
    """Render the dashboard at a fixed viewport size."""

    console = Console(
        file=StringIO(),
        width=width,
        height=height,
        record=True,
        force_terminal=False,
        color_system=None,
    )
    state = reduce_dashboard_state(load_settings(), load_events(FIXTURE))
    console.print(render_dashboard(state, width=width, height=height, column_ratio=column_ratio))
    return normalize(console.export_text())


def assert_snapshot(name: str, actual: str) -> None:
    """Assert against a stored snapshot file."""

    expected = SNAPSHOT_DIR.joinpath(name).read_text()
    assert actual == expected


def test_dashboard_snapshot_80x24() -> None:
    assert_snapshot("dashboard_80x24.txt", render_snapshot(80, 24))


def test_dashboard_snapshot_100x30() -> None:
    assert_snapshot("dashboard_100x30.txt", render_snapshot(100, 30))


def test_dashboard_snapshot_140x40() -> None:
    assert_snapshot("dashboard_140x40.txt", render_snapshot(140, 40))


def test_dashboard_snapshot_140x40_ratio_3_to_1() -> None:
    assert_snapshot(
        "dashboard_140x40_ratio_3_to_1.txt",
        render_snapshot(140, 40, column_ratio=(3, 1)),
    )


def test_dashboard_snapshot_140x40_ratio_1_to_3() -> None:
    assert_snapshot(
        "dashboard_140x40_ratio_1_to_3.txt",
        render_snapshot(140, 40, column_ratio=(1, 3)),
    )
