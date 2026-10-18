"""``mctl config`` commands."""

import json

import click

from mctl.cli.state import AppState


@click.group("config")
def config_group() -> None:
    """Inspect and validate the config file"""


@config_group.command()
@click.pass_obj
def show(state: AppState) -> None:
    """Print the loaded config, with defaults filled in and paths resolved"""
    click.echo(json.dumps(state.settings.model_dump(mode="json"), indent=2))


@config_group.command()
@click.pass_obj
def check(state: AppState) -> None:
    """Validate the config file. Exits 2 if it has a problem."""
    _ = state.settings
    click.echo(f"OK: {state.config_path}")
