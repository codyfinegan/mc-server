import os
from pathlib import Path

import click

from .backup import BackupManager
from .configuration import Config
from .server import ServerManager


class ToolLoader:
    """Middleman just to make the communicator and config available to commands."""

    def setup(self, config: Config):
        self.config = config
        self.server = ServerManager(self.config)

    def decouple(self):
        return self.config, self.communicator


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
    x = loader.server.rcon_send(["list"])
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
    loader.server.stop(reason, time)


@cli.command(name="start")
@pass_loader
def start(loader: ToolLoader):
    """Boot the server."""
    loader.server.start()


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
    loader.server.stop(reason, time, "restarting")
    loader.server.start()


@cli.command(name="backup")
@click.option(
    "--incremental",
    is_flag=True,
    default=False,
    help="Backs up into the incremental folder",
)
@click.option(
    "--sync",
    is_flag=True,
    default=False,
    help="Pushes the backup up to the remote storage.",
)
@pass_loader
def backup(loader: ToolLoader, incremental: bool, sync: bool):
    """Create a backup of the world folder into the backups folder."""
    server = loader.server

    backup_manager = BackupManager(server=server, incremental=incremental)

    # Tell people the backup is happening
    server.tell_all("Saving the world...", play_sound=False)

    # Sync the content across
    backup_manager.sync_world_folder()

    if incremental:
        if sync:
            backup_manager.git_sync()
            pass

        server.tell_all("Save complete", play_sound=False)
        return

    # Compress the full backup
    success, file = backup_manager.compress_backup()
    if not success:
        click.echo(f"Backup failed to compress, expected {file}")
        return

    click.echo(f"Backup saved in {file}")
    server.tell_all("Save complete", play_sound=False)

    if not sync:
        click.echo("No syncing, backup complete.")
        return

    # Upload the most recent backup file
    backup_manager.aws_sync(upload=True, limit=1)
    click.echo("Sync complete")


@cli.command(name="backup:sync-aws")
@click.option(
    "--download",
    is_flag=True,
    default=False,
    help="Download missing files from AWS to the local backups folder",
)
@click.option(
    "--upload",
    is_flag=True,
    default=False,
    help="Upload missing files to AWS",
)
@click.option(
    "--limit",
    default=1,
    type=click.IntRange(0, 20),
    help="Number of files to upload or download",
)
@pass_loader
def sync_backup_aws(loader: ToolLoader, download: bool, upload: bool, limit: int):
    """Upload and download full backup files to a configured S3 bucket"""
    backup_manager = BackupManager(server=loader.server, incremental=False)

    backup_manager.aws_sync(upload=upload, download=download, limit=limit)


@cli.command(name="backup:sync-git")
@click.option(
    "--push",
    is_flag=True,
    default=False,
    help="Push the results up",
)
@pass_loader
def sync_backup_git(loader: ToolLoader, push: bool):
    """Upload incremental changes to git"""
    backup_manager = BackupManager(server=loader.server, incremental=True)
    backup_manager.git_sync()
