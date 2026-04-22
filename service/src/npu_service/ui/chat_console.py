"""Chat-first Rich console renderers."""

from __future__ import annotations

from dataclasses import dataclass

from rich.console import Console, ConsoleOptions, Group, RenderableType, RenderResult
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from npu_service.core.chat import ChatMessage
from npu_service.ui.dashboard import DashboardState, shorten_path, sparkline


@dataclass(frozen=True)
class ChatConsoleState:
    """State for the chat-first console."""

    view_mode: str
    title: str
    subtitle: str
    status_line: str
    help_line: str
    system_message: str | None
    dashboard: DashboardState
    messages: tuple[ChatMessage, ...]
    input_buffer: str
    log_lines: tuple[str, ...]
    log_follow: bool
    log_top_line: int
    controls: tuple[str, ...]


@dataclass(frozen=True)
class ChatLayoutMetrics:
    """Computed layout sizing for the chat console."""

    render_width: int
    render_height: int
    status_h: int
    metrics_h: int
    controls_h: int
    transcript_h: int
    log_viewport_rows: int


@dataclass(frozen=True)
class ClippedLinesRenderable:
    """Render line-oriented content without terminal-width wrapping."""

    lines: tuple[str, ...]
    overflow: str = "ellipsis"
    style: str | None = None

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        width = max(1, options.max_width)
        if not self.lines:
            yield Text("")
            return
        last_index = len(self.lines) - 1
        for index, line in enumerate(self.lines):
            text = Text(line, style=self.style or "")
            text.truncate(width, overflow=self.overflow, pad=False)
            if index < last_index:
                text.append("\n")
            yield text


@dataclass(frozen=True)
class PromptLineRenderable:
    """Render the prompt line with a stable width budget."""

    input_buffer: str

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        prefix = Text("  > ", style="bold cyan")
        available = max(0, options.max_width - prefix.cell_len)
        rendered = self.input_buffer
        if len(rendered) > available:
            tail = max(0, available - 3)
            rendered = "..." + rendered[-tail:] if tail else ""
        yield prefix + Text(rendered)


def compute_chat_layout_metrics(width: int, height: int, view_mode: str) -> ChatLayoutMetrics:
    """Compute stable layout metrics for the live chat console."""

    render_width = max(60, width)
    render_height = max(16, height)
    status_h = min(10, max(5, render_height // 3))
    metrics_h = min(14, max(6, render_height // 3))
    controls_h = min(10, max(4, render_height // 4))

    if view_mode == "chat":
        transcript_h = max(6, render_height - 1 - controls_h)
    else:
        transcript_h = max(6, render_height - 1 - status_h - controls_h)

    # The panel border consumes two rows; keep at least three visible rows when possible.
    log_viewport_rows = max(3, transcript_h - 2)
    return ChatLayoutMetrics(
        render_width=render_width,
        render_height=render_height,
        status_h=status_h,
        metrics_h=metrics_h,
        controls_h=controls_h,
        transcript_h=transcript_h,
        log_viewport_rows=log_viewport_rows,
    )


def metric_value_text(current: float, peak: float, unit: str) -> str:
    """Format the metric value column."""

    return f"{current:.0f}/{peak:.0f}{unit}"


def sparkline_to_width(values: tuple[float, ...], width: int) -> str:
    """Resize a sparkline to a target width."""

    if width <= 0:
        return ""
    if not values:
        return " " * width
    if len(values) == width:
        return sparkline(values)
    if len(values) == 1:
        return sparkline(values) * width

    resampled: list[float] = []
    for index in range(width):
        source_index = round(index * (len(values) - 1) / max(1, width - 1))
        resampled.append(values[source_index])
    return sparkline(tuple(resampled))


@dataclass(frozen=True)
class MetricsSummaryRenderable:
    """Width-aware metric summary renderable."""

    rows: tuple[tuple[str, str, tuple[float, ...]], ...]

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        available = max(18, options.max_width - 2)
        label_width = max(len(label) for label, _, _ in self.rows)
        value_width = max(len(value) for _, value, _ in self.rows)
        graph_width = max(8, available - label_width - value_width - 4)
        for label, value, values in self.rows:
            graph = sparkline_to_width(values, graph_width)
            line = f"{label:<{label_width}}  {value:<{value_width}}  {graph}"
            yield Text(line)


def build_transcript_panel(state: ChatConsoleState) -> Panel:
    """Build the transcript panel."""

    rendered: list[Text] = []
    if not state.messages:
        rendered.append(
            Text("No conversation yet.\nType a message below to talk to the local NPU model.")
        )
    for message in state.messages:
        prefix = "You" if message.role == "user" else "NPU"
        style = "bold cyan" if message.role == "user" else "bold green"
        rendered.append(Text(f"{prefix}: ", style=style) + Text(message.content))
    if state.system_message:
        rendered.append(
            Text("System: ", style="bold yellow") + Text(state.system_message, style="yellow")
        )
    return Panel(Group(*rendered), title=state.title, subtitle=state.subtitle, border_style="cyan")


def build_log_panel(state: ChatConsoleState, viewport_rows: int) -> Panel:
    """Build the parsed log panel with scroll state."""

    lines = list(state.log_lines)
    if not lines:
        lines = ["No log entries yet."]

    if state.log_follow:
        visible = lines[-viewport_rows:]
        subtitle = "Follow: ON"
    else:
        start = max(0, min(state.log_top_line, max(0, len(lines) - 1)))
        visible = lines[start : start + viewport_rows]
        subtitle = f"Follow: OFF  Line {start + 1}/{len(lines)}"

    return Panel(
        ClippedLinesRenderable(tuple(visible)),
        title="Run Log",
        subtitle=subtitle,
        border_style="cyan",
    )


def build_status_panel(state: ChatConsoleState) -> Panel:
    """Build the operator status panel."""

    npu_state = "unknown"
    npu_source = "unspecified"
    for label, value in state.dashboard.artifact_rows:
        if label == "NPU state":
            npu_state = value
        elif label == "NPU source":
            npu_source = value

    table = Table.grid(padding=(0, 1), expand=True)
    table.add_column(style="bold cyan", ratio=2, no_wrap=True)
    table.add_column(style="white", ratio=4, overflow="ellipsis", no_wrap=True)
    table.add_row("Mode", state.view_mode)
    table.add_row("Status", state.status_line)
    table.add_row("Prompt", state.help_line)
    table.add_row("NPU", npu_state)
    table.add_row("Model", shorten_path(state.dashboard.active_model, 40))
    table.add_row("Run ID", shorten_path(state.dashboard.active_run_id, 32))
    table.add_row("Signal", npu_source)
    return Panel(table, title="Now", border_style="green")


def build_metrics_panel(state: ChatConsoleState) -> Panel:
    """Build the supporting metrics panel."""

    npu = state.dashboard.trends[0]
    cpu = state.dashboard.trends[1]
    gpu = state.dashboard.trends[3]
    metrics_renderable = MetricsSummaryRenderable(
        (
            ("NPU", metric_value_text(npu.current, npu.peak, npu.unit), npu.values),
            ("CPU", metric_value_text(cpu.current, cpu.peak, cpu.unit), cpu.values),
            ("GPU", metric_value_text(gpu.current, gpu.peak, gpu.unit), gpu.values),
        )
    )
    lines: list[str] = []
    for label, value in state.dashboard.artifact_rows[:6]:
        lines.append(f"{label}: {shorten_path(value, 44)}")
    return Panel(
        Group(metrics_renderable, Text(""), ClippedLinesRenderable(tuple(lines))),
        title="Metrics",
        border_style="magenta",
    )


def build_controls_panel(state: ChatConsoleState) -> Panel:
    """Build the visible controls panel."""

    if state.view_mode == "log":
        visible_commands = (
            "/view split",
            "/view chat",
            "/view metrics",
            "f toggle follow",
            "↑↓ / PgUp PgDn scroll",
            "/quit",
        )
    else:
        visible_commands = state.controls

    return Panel(ClippedLinesRenderable(tuple(visible_commands)), title="Commands", border_style="yellow")


def build_prompt_line(state: ChatConsoleState) -> RenderableType:
    """Build the inline input prompt under the main pane."""

    return PromptLineRenderable(state.input_buffer)


def render_chat_console(state: ChatConsoleState, width: int, height: int) -> RenderableType:
    """Render the chat-first console."""

    metrics = compute_chat_layout_metrics(width=width, height=height, view_mode=state.view_mode)
    main_panel = (
        build_transcript_panel(state)
        if state.view_mode != "log"
        else build_log_panel(state, viewport_rows=metrics.log_viewport_rows)
    )
    prompt_line = build_prompt_line(state)

    if state.view_mode == "chat":
        layout = Layout(size=metrics.render_height)
        layout.split_column(
            Layout(main_panel, name="transcript"),
            Layout(prompt_line, name="prompt", size=1),
            Layout(build_controls_panel(state), name="controls", size=metrics.controls_h),
        )
        return layout

    if state.view_mode == "metrics":
        layout = Layout(size=metrics.render_height)
        layout.split_row(
            Layout(name="left", ratio=2),
            Layout(name="right", ratio=1),
        )
        layout["left"].split_column(
            Layout(main_panel, name="transcript"),
            Layout(prompt_line, name="prompt", size=1),
        )
        layout["right"].split_column(
            Layout(build_status_panel(state), size=metrics.status_h),
            Layout(build_metrics_panel(state), size=metrics.metrics_h),
            Layout(build_controls_panel(state), size=metrics.controls_h),
        )
        return layout

    layout = Layout(size=metrics.render_height)
    if metrics.render_width < 110:
        layout.split_column(
            Layout(main_panel, name="transcript"),
            Layout(prompt_line, name="prompt", size=1),
            Layout(build_status_panel(state), name="status", size=metrics.status_h),
            Layout(build_controls_panel(state), name="controls", size=metrics.controls_h),
        )
    else:
        layout.split_row(
            Layout(name="left", ratio=2),
            Layout(name="right", ratio=1),
        )
        layout["left"].split_column(
            Layout(main_panel, name="transcript"),
            Layout(prompt_line, name="prompt", size=1),
        )
        layout["right"].split_column(
            Layout(build_status_panel(state), size=metrics.status_h),
            Layout(build_metrics_panel(state), size=metrics.metrics_h),
            Layout(build_controls_panel(state), size=metrics.controls_h),
        )
    return layout
