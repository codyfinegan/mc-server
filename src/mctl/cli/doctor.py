"""``mctl doctor``."""

import click

from mctl.cli.state import AppState
from mctl.doctor import Status, run_checks

_SYMBOLS = {Status.OK: "✓", Status.FAIL: "✗", Status.SKIP: "-"}


@click.command("doctor")
@click.pass_obj
def doctor_command(state: AppState) -> None:
    """Check that the tools, jars and server settings mctl needs are ready."""
    checks = run_checks(state.settings)
    width = max(len(check.name) for check in checks)
    for check in checks:
        click.echo(f"{_SYMBOLS[check.status]} {check.name:<{width}}  {check.detail}")
    if any(check.status is Status.FAIL for check in checks):
        raise click.exceptions.Exit(1)
