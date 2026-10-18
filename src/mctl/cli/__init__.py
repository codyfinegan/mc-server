"""The ``mctl`` command line interface."""

from pathlib import Path

import click

from mctl.cli.config import config_group
from mctl.cli.doctor import doctor_command
from mctl.cli.state import AppState
from mctl.config import find_config


@click.group(name="mctl")
@click.option(
    "--config",
    "config_path",
    type=click.Path(path_type=Path),
    envvar="MCTL_CONFIG",
    show_envvar=True,
    help="Config file. [default: ~/.config/mctl/config.toml]",
)
@click.version_option(package_name="mctl")
@click.pass_context
def cli(ctx: click.Context, config_path: Path | None) -> None:
    """Run and maintain a Minecraft server"""
    ctx.obj = AppState(find_config(config_path))


cli.add_command(config_group)
cli.add_command(doctor_command)


def main() -> None:
    cli()
