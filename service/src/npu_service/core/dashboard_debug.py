"""Structured debug helpers for the live dashboard."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from io import StringIO

from rich.console import Console, RenderableType

from npu_service.core.settings import Settings


def reset_dashboard_debug_log(settings: Settings) -> None:
    """Reset the dashboard debug log for a fresh interactive run."""

    settings.dashboard_ui_log.parent.mkdir(parents=True, exist_ok=True)
    settings.dashboard_ui_log.write_text("", encoding="utf-8")


def append_dashboard_debug(settings: Settings, event: str, **data: object) -> None:
    """Append one structured dashboard debug event."""

    settings.dashboard_ui_log.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ts": datetime.now(UTC).isoformat(),
        "event": event,
        "data": data,
    }
    with settings.dashboard_ui_log.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True) + "\n")


def measure_renderable(renderable: RenderableType, width: int, height: int) -> dict[str, int]:
    """Measure line lengths for one rendered frame."""

    console = Console(
        file=StringIO(),
        width=width,
        height=height,
        record=True,
        force_terminal=False,
        color_system=None,
    )
    console.print(renderable)
    lines = console.export_text().splitlines()
    visible_lengths = [len(line.rstrip()) for line in lines]
    max_line_length = max(visible_lengths, default=0)
    exact_width_lines = sum(1 for length in visible_lengths if length == width)
    return {
        "rendered_lines": len(lines),
        "max_line_length": max_line_length,
        "exact_width_lines": exact_width_lines,
    }
