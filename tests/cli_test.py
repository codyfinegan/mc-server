import json
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from click.testing import CliRunner

from mctl.cli import cli, main

BAD_TOML = '[server]\nstart_command = "x"\nport = 1\n'


@pytest.fixture
def runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> CliRunner:
    """A CliRunner that can never see the real ~/.config or $MCTL_CONFIG."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("MCTL_CONFIG", raising=False)
    return CliRunner()


def test_help_lists_groups(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "Usage: mctl" in result.output
    assert "MCTL_CONFIG" in result.output
    assert "config" in result.output


def test_version(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["--version"])

    assert result.exit_code == 0
    assert result.output.startswith("mctl, version ")


def test_help_does_not_load_config(runner: CliRunner, tmp_path: Path) -> None:
    missing = tmp_path / "missing.toml"

    result = runner.invoke(cli, ["--config", str(missing), "config", "--help"])

    assert result.exit_code == 0


def test_check_good_config(
    runner: CliRunner, write_config: Callable[[str], Path], minimal_toml: str
) -> None:
    path = write_config(minimal_toml)

    result = runner.invoke(cli, ["config", "check"], env={"MCTL_CONFIG": str(path)})

    assert result.exit_code == 0
    assert result.output == f"OK: {path}\n"


def test_check_bad_config(
    runner: CliRunner, write_config: Callable[[str], Path]
) -> None:
    path = write_config(BAD_TOML)

    result = runner.invoke(cli, ["config", "check"], env={"MCTL_CONFIG": str(path)})

    assert result.exit_code == 2
    lines = result.output.splitlines()
    assert lines[0] == f"Error: config error in {path}:"
    assert [line.strip() for line in lines[1:]] == [
        "server.dir: Field required",
        "server.port: Extra inputs are not permitted",
    ]


def test_check_missing_file(runner: CliRunner, tmp_path: Path) -> None:
    path = tmp_path / "missing.toml"

    result = runner.invoke(cli, ["--config", str(path), "config", "check"])

    assert result.exit_code == 2
    assert "No such file or directory" in result.output


def test_show_prints_resolved_json(
    runner: CliRunner, write_config: Callable[[str], Path], tmp_path: Path
) -> None:
    path = write_config('[server]\ndir = "server"\nstart_command = "./run.sh"\n')

    result = runner.invoke(cli, ["--config", str(path), "config", "show"])

    assert result.exit_code == 0
    shown = json.loads(result.output)
    assert shown["server"] == {
        "dir": str(tmp_path / "server"),
        "start_command": "./run.sh",
        "screen_session": "mcs",
    }
    assert shown["java"] == {"path": "/usr/bin/java", "min_version": 25}
    assert shown["mca"] is None


def test_show_bad_config(
    runner: CliRunner, write_config: Callable[[str], Path]
) -> None:
    path = write_config(BAD_TOML)

    result = runner.invoke(cli, ["--config", str(path), "config", "show"])

    assert result.exit_code == 2
    assert "server.dir: Field required" in result.output


def test_config_option_beats_env_var(
    runner: CliRunner,
    write_config: Callable[[str], Path],
    minimal_toml: str,
    tmp_path: Path,
) -> None:
    good = write_config(minimal_toml)
    bad = tmp_path / "bad.toml"
    bad.write_text(BAD_TOML)

    result = runner.invoke(
        cli,
        ["--config", str(good), "config", "check"],
        env={"MCTL_CONFIG": str(bad)},
    )

    assert result.exit_code == 0
    assert result.output == f"OK: {good}\n"


def test_default_config_path(
    runner: CliRunner, tmp_path: Path, minimal_toml: str
) -> None:
    default = tmp_path / "home/.config/mctl/config.toml"
    default.parent.mkdir(parents=True)
    default.write_text(minimal_toml)

    result = runner.invoke(cli, ["config", "check"])

    assert result.exit_code == 0
    assert result.output == f"OK: {default}\n"


def test_main_runs_cli(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["mctl", "--version"])

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 0
    assert capsys.readouterr().out.startswith("mctl, version ")
