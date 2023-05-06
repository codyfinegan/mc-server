import os
from pathlib import Path

import click

from .lib import Communicator, Config


def debug_echo(debug: bool, message: str) -> None:
    if debug:
        click.echo(message)


@click.group(invoke_without_command=True)
@click.option("--debug/--no-debug", default=False)
@click.option("--init", is_flag=True, default=False)
@click.pass_context
def cli(ctx, debug, init):
    ctx.ensure_object(dict)
    ctx.obj["DEBUG"] = debug

    config_folder = os.environ.get("CMC_CONFIG", str(Path.home()))
    config_path = Path(config_folder).joinpath(".cmcconfig.toml")

    # Are we running init?
    if init:
        Config.write(config_path)
        raise SystemExit

    if ctx.invoked_subcommand is None:
        ctx = click.get_current_context()
        click.echo(ctx.get_help())
        ctx.exit()

    # Load the config option
    ctx.obj["cfg"] = Config.load(config_path, debug)
    ctx.obj["comm"] = Communicator(ctx.obj["cfg"])


@cli.command()
@click.pass_context
def online(context):
    context.obj["comm"].online()
