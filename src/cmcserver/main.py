import os
import time as timelib
from pathlib import Path

import click

from .lib import (
    Config,
    ScreenManager,
    ToolLoader,
    seconds_to_countdown,
    start_server,
    stop_server,
)

pass_loader = click.make_pass_decorator(ToolLoader, ensure=True)


@click.group(invoke_without_command=True)
@click.option("--debug/--no-debug", default=False)
@click.option("--init", is_flag=True, default=False)
@click.option("--force", is_flag=True, default=False)
@click.pass_context
def cli(ctx, debug, init, force):
    """Group all of our commands together"""

    ctx.ensure_object(dict)
    ctx.obj = ToolLoader()

    config_folder = os.environ.get("CMC_CONFIG", str(Path.home()))
    config_path = Path(config_folder).joinpath(".cmcconfig.toml")

    # Are we running init?
    if init:
        Config.write(config_path, force)
        raise SystemExit

    if ctx.invoked_subcommand is None:
        ctx = click.get_current_context()
        click.echo(ctx.get_help())
        ctx.exit()

    # Load the config option
    ctx.obj.setup(Config.load(config_path, debug))


@cli.command()
@pass_loader
def status(loader: ToolLoader):
    """See the status of the server"""
    x = loader.communicator.send(["list"])
    click.echo(x)


@cli.command(name="stop")
@click.option(
    "-t",
    "--time",
    default=5,
    type=click.IntRange(0, 600),
    help="How many seconds until shutdown?",
)
@click.argument("reason", type=str, default=None, required=False)
@pass_loader
def stop(loader: ToolLoader, time: int, reason: str):
    """Stop the server"""
    if not ScreenManager.exists() and not loader.communicator.ping_server():
        click.echo("The server is not running.")
        return

    if not reason:
        reason = ""
    else:
        reason = f" {reason}"

    if time < 5:
        time = 5

    loader.communicator.tell_all(
        f"The server is stopping in {time} seconds",
        sound="block.bell.use",
    )

    if time > 5:
        timelib.sleep(time - 5)

    stop_server(loader)


@cli.command(name="restart")
@click.option(
    "-t",
    "--time",
    default=60,
    type=click.IntRange(0, 600),
    help="How many seconds until restart?",
)
@click.argument("reason", type=str, default=None, required=False)
@pass_loader
def restart(loader: ToolLoader, time: int, reason: str):
    """Restart the server"""
    if not ScreenManager.exists() and not loader.communicator.ping_server():
        click.echo("The server is not running, call server:up instead.")
        return

    if not reason:
        reason = ""
    else:
        reason = f" {reason}"

    if time < 5:
        time = 5

    for sleep, text in seconds_to_countdown(time):
        timelib.sleep(sleep)
        if text:
            loader.communicator.tell_all(
                f"The server will restart in {text}",
                sound="block.bell.use",
            )

    # Stop the server
    stop_server(loader)

    click.echo("Server not running, restarting...")

    # Start the server
    start_server(loader)


@cli.command(name="start")
@pass_loader
def boot(loader: ToolLoader):
    """Boot the server."""
    start_server(loader)
