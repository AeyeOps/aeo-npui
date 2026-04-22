"""Command-shape tests for iteration 1."""

from typer.testing import CliRunner

from npu_service.cli import app

runner = CliRunner()


def normalize(text: str) -> str:
    """Normalize line endings for snapshot-like assertions."""

    return text.replace("\r\n", "\n")


def test_root_help_contains_golden_path() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    output = normalize(result.stdout)
    assert "npu-service" in output
    assert "watch" in output
    assert "trace" in output
    assert "phase-zero" in output
    assert "live" in output


def test_watch_help_is_specific() -> None:
    result = runner.invoke(app, ["watch", "--help"])
    assert result.exit_code == 0
    output = normalize(result.stdout)
    assert "live metrics" in output.lower()


def test_dashboard_stub_is_clear() -> None:
    result = runner.invoke(app, ["dashboard", "--static"])
    assert result.exit_code == 0
    output = normalize(result.stdout)
    assert "rolling trends" in output.lower() or "summary" in output.lower()
    assert "watch" in output.lower()


def test_endurance_help_is_present() -> None:
    result = runner.invoke(app, ["endurance", "--help"])
    assert result.exit_code == 0
    output = normalize(result.stdout)
    assert "repeated backend executions" in output.lower()


def test_dashboard_help_mentions_static_and_command() -> None:
    result = runner.invoke(app, ["dashboard", "--help"])
    assert result.exit_code == 0
    output = normalize(result.stdout)
    assert "--static" in output
    assert "--command" in output
