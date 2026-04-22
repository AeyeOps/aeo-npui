"""Static dashboard renderers for iteration 2."""

from __future__ import annotations

from dataclasses import dataclass

from rich.console import Group, RenderableType
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from npu_service.core.settings import Settings

SPARKLINE_BARS = "▁▂▃▄▅▆▇█"


@dataclass(frozen=True)
class TrendMetric:
    """A named trend line for the dashboard."""

    label: str
    unit: str
    values: tuple[float, ...]
    current: float
    peak: float


@dataclass(frozen=True)
class DashboardState:
    """Static dashboard state."""

    title: str
    mode: str
    status: str
    active_model: str
    active_run_id: str
    selected_command: str
    event_log_path: str
    windows_root: str
    wsl_root: str
    notes: tuple[str, ...]
    interaction_lines: tuple[str, ...]
    trends: tuple[TrendMetric, ...]
    artifact_rows: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ClippedLinesRenderable:
    """Render line-oriented content without width-triggered wrapping."""

    lines: tuple[str, ...]
    overflow: str = "ellipsis"

    def __rich_console__(self, console, options):
        width = max(1, options.max_width)
        if not self.lines:
            yield Text("")
            return
        last_index = len(self.lines) - 1
        for index, line in enumerate(self.lines):
            text = Text(line)
            text.truncate(width, overflow=self.overflow, pad=False)
            if index < last_index:
                text.append("\n")
            yield text


def sparkline(values: tuple[float, ...]) -> str:
    """Render a simple sparkline for a sequence of values."""

    if not values:
        return ""
    floor = min(values)
    ceiling = max(values)
    if ceiling == floor:
        return SPARKLINE_BARS[0] * len(values)
    span = ceiling - floor
    chars: list[str] = []
    for value in values:
        normalized = (value - floor) / span
        index = min(int(round(normalized * (len(SPARKLINE_BARS) - 1))), len(SPARKLINE_BARS) - 1)
        chars.append(SPARKLINE_BARS[index])
    return "".join(chars)


def compact_trend_line(trend: TrendMetric, label: str) -> str:
    """Format one compact trend line."""

    return f"{label}  {trend.current:.0f}/{trend.peak:.0f}{trend.unit}  {sparkline(trend.values)}"


def build_interaction_panel(state: DashboardState) -> Panel:
    """Build the left interaction panel."""

    return Panel(ClippedLinesRenderable(state.interaction_lines), title="Interaction", border_style="cyan")


def build_compact_interaction_panel(state: DashboardState) -> Panel:
    """Build a compact interaction panel for narrow terminals."""

    source_lines = list(state.interaction_lines[:6])
    if not source_lines:
        source_lines = [
            "No live interaction yet.",
            f"Next: npu-service {state.selected_command}",
        ]
    return Panel(ClippedLinesRenderable(tuple(source_lines)), title="Interaction", border_style="cyan")


def build_kpi_panel(state: DashboardState) -> Panel:
    """Build the top-right KPI panel."""

    table = Table.grid(padding=(0, 1), expand=True)
    table.add_column(style="bold cyan", ratio=2, no_wrap=True)
    table.add_column(style="white", ratio=3, overflow="ellipsis", no_wrap=True)
    table.add_row("Mode", state.mode)
    table.add_row("Status", state.status)
    table.add_row("Command", state.selected_command)
    table.add_row("Run ID", state.active_run_id)
    table.add_row("Model", state.active_model)
    return Panel(table, title="KPIs", border_style="green")


def build_compact_kpi_panel(state: DashboardState, width: int) -> Panel:
    """Build a compact KPI panel for narrow terminals."""

    table = Table.grid(padding=(0, 1), expand=True)
    table.add_column(style="bold cyan", ratio=2, no_wrap=True)
    table.add_column(style="white", ratio=3, overflow="ellipsis", no_wrap=True)
    table.add_row("Mode", state.mode)
    table.add_row("Status", state.status)
    table.add_row("Run", state.active_run_id)
    table.add_row("Model", shorten_path(state.active_model, max(28, width - 20)))
    return Panel(table, title="KPIs", border_style="green")


def build_trends_panel(state: DashboardState) -> Panel:
    """Build the middle-right trends panel."""

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Metric", ratio=2, overflow="ellipsis", no_wrap=True)
    table.add_column("Current", justify="right", no_wrap=True)
    table.add_column("Peak", justify="right", no_wrap=True)
    table.add_column("Trend", ratio=4, overflow="crop", no_wrap=True)
    for trend in state.trends:
        table.add_row(
            trend.label,
            f"{trend.current:.1f}{trend.unit}",
            f"{trend.peak:.1f}{trend.unit}",
            sparkline(trend.values),
        )
    return Panel(table, title="Rolling Trends", border_style="magenta")


def build_artifacts_panel(state: DashboardState) -> Panel:
    """Build the bottom-right artifacts and notes panel."""

    artifact_table = Table.grid(padding=(0, 1), expand=True)
    artifact_table.add_column(style="bold yellow", ratio=2, no_wrap=True)
    artifact_table.add_column(style="white", ratio=5, overflow="ellipsis", no_wrap=True)
    for label, value in state.artifact_rows:
        artifact_table.add_row(label, value)

    notes = tuple(f"- {line}" for line in state.notes)
    group = Group(
        artifact_table,
        Text(""),
        Text("Notes", style="bold yellow"),
        ClippedLinesRenderable(notes),
    )
    return Panel(group, title="Artifacts", border_style="yellow")


def shorten_path(path: str, max_length: int) -> str:
    """Shorten a path for compact renders."""

    if len(path) <= max_length:
        return path
    head = max_length - 3
    return "..." + path[-head:]


def build_compact_summary_panel(state: DashboardState, width: int) -> Panel:
    """Build a compact summary panel for constrained terminals."""

    npu_trend = state.trends[0]
    cpu_trend = state.trends[1]
    gpu_trend = state.trends[3]
    lines = [
        compact_trend_line(npu_trend, "NPU"),
        compact_trend_line(cpu_trend, "CPU"),
        compact_trend_line(gpu_trend, "GPU"),
        "",
        f"Use: {state.selected_command}",
        f"Log: {shorten_path(state.event_log_path, max(30, width - 18))}",
    ]
    return Panel(ClippedLinesRenderable(tuple(lines)), title="Summary", border_style="yellow")


def build_dashboard(state: DashboardState) -> Layout:
    """Build the static Rich dashboard layout."""

    return build_dashboard_for_viewport(state, width=120, height=40)


def build_dashboard_for_viewport(
    state: DashboardState,
    width: int,
    height: int,
    column_ratio: tuple[int, int] = (8, 7),
) -> Layout:
    """Build the static Rich dashboard layout for a target viewport."""

    layout = Layout(name="root", size=height)
    if width < 110 or height < 30:
        layout.split_column(
            Layout(build_compact_interaction_panel(state), name="interaction", size=8),
            Layout(build_compact_kpi_panel(state, width), name="kpis", size=7),
            Layout(build_compact_summary_panel(state, width), name="summary"),
        )
    elif width < 120 or height < 36:
        layout.split_column(
            Layout(build_interaction_panel(state), name="interaction", size=10),
            Layout(build_kpi_panel(state), name="kpis", size=8),
            Layout(build_trends_panel(state), name="trends", size=9),
            Layout(build_artifacts_panel(state), name="artifacts"),
        )
    else:
        layout.split_row(
            Layout(name="left", ratio=column_ratio[0]),
            Layout(name="right", ratio=column_ratio[1]),
        )
        layout["left"].update(build_interaction_panel(state))
        layout["right"].split_column(
            Layout(name="kpis", size=8),
            Layout(name="trends", size=12),
            Layout(name="artifacts"),
        )
        layout["right"]["kpis"].update(build_kpi_panel(state))
        layout["right"]["trends"].update(build_trends_panel(state))
        layout["right"]["artifacts"].update(build_artifacts_panel(state))
    return layout


def build_iteration_two_state(settings: Settings) -> DashboardState:
    """Build the static dashboard state for iteration 2."""

    return DashboardState(
        title="NPU Console Dashboard",
        mode="dashboard",
        status="iteration-2-static",
        active_model="OpenVINO/TinyLlama-1.1B-Chat-v1.0-int4-ov",
        active_run_id="watch-iteration2-preview",
        selected_command="watch",
        event_log_path=str(settings.event_log),
        windows_root=settings.windows_root,
        wsl_root=str(settings.wsl_root),
        notes=(
            "Left pane is reserved for interaction and logs.",
            "Right side holds KPIs, trends, and artifact paths.",
            "Live tailing is scheduled for iteration 3.",
        ),
        interaction_lines=(
            "npu-service dashboard",
            "",
            "Current focus:",
            "  - prove the split layout is readable",
            "  - keep the golden path obvious",
            "  - validate width handling before live updates",
            "",
            "Recommended next command:",
            "  npu-service watch",
        ),
        trends=(
            TrendMetric("NPU util", "%", (0, 0, 0, 24, 42, 81, 91, 88), 88.0, 91.0),
            TrendMetric("CPU util", "%", (12, 18, 21, 27, 33, 29, 24, 19), 19.0, 33.0),
            TrendMetric(
                "CPU mem",
                " MiB",
                (36200, 36410, 36600, 37020, 37840, 37600, 37000),
                37000.0,
                37840.0,
            ),
            TrendMetric("GPU util", "%", (0, 0, 0, 0, 0, 0, 0, 0), 0.0, 0.0),
            TrendMetric("GPU mem", " MiB", (0, 0, 5.7, 5.7, 5.7, 5.7, 3.7), 3.7, 5.7),
        ),
        artifact_rows=(
            ("Event log", str(settings.event_log)),
            ("Windows root", settings.windows_root),
            ("WSL root", str(settings.wsl_root)),
            ("Golden path", "npu-service watch"),
        ),
    )


def render_dashboard(
    state: DashboardState,
    width: int = 120,
    height: int = 40,
    column_ratio: tuple[int, int] = (8, 7),
) -> RenderableType:
    """Return the top-level static dashboard renderable."""

    return build_dashboard_for_viewport(
        state,
        width=width,
        height=height,
        column_ratio=column_ratio,
    )
