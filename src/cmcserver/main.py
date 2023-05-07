import os
import time as timelib
from pathlib import Path

import click

from .lib import Config, ScreenManager, ToolLoader

pass_loader = click.make_pass_decorator(ToolLoader, ensure=True)


@click.group(invoke_without_command=True)
@click.option("--debug/--no-debug", default=False)
@click.option("--init", is_flag=True, default=False)
@click.option("--force", is_flag=True, default=False)
@click.pass_context
def cli(ctx, debug, init, force):
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
    print(x)


@cli.command(name="server:stats")
@pass_loader
def ping(loader: ToolLoader):
    print(loader.communicator.ping_server(ping=False))


@cli.command(name="server:stop")
@click.option(
    "-t",
    "--time",
    default=5,
    type=click.IntRange(0, 120),
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

    # 5 second countdown
    for i in range(5, 0, -1):
        loader.communicator.tell_all(f"In {i}...")
        timelib.sleep(1)

    loader.communicator.tell_all("Off we go!", sound="block.bell.use")
    timelib.sleep(1)
    loader.communicator.send(
        [
            "/kick @a Sever is stopping, check Discord for info",
            "/stop",
        ],
    )


@cli.command(name="server:start")
@pass_loader
def boot(loader: ToolLoader):
    """Boot the server."""
    if ScreenManager.exists():
        click.echo("There is already a running server (or at least a screen session.)")
        click.echo("Run `screen -ls mcs` to see the existing processes.")
        return

    context_path = Path(loader.config.get("context_dir"))
    startup = Path(loader.config.get("startup"))
    startup_script = context_path.joinpath(startup)

    if not ScreenManager.start(
        loader.config.debug,
        startup_script,
        context_path,
        loader.config.get("boot_pause"),
    ):
        raise SystemExit

    # Now we want to wait for Minecraft to be up and good
    # We're going to check about 10 times with a pause between each
    # And try to rcon
    # If rcon is not configured then this might be a problem

    loaded = False
    for i in range(10):
        # We want to check if our screen window is alive

        # Are we alive?
        click.echo("Checking if the server is up yet...")
        if loader.communicator.ping_server():
            loaded = True
            break
        click.echo("Not yet, waiting a few moments...")
        timelib.sleep(5)

    if loaded:
        click.echo("Server has been loaded.")
    else:
        click.echo(
            "Could not tell if the server loaded successfully, check it out. Make sure rcon/query has been configured",
        )
