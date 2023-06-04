import os
import pathlib
from pathlib import Path
from shutil import get_terminal_size

import click

from .backup import BackupManager
from .configuration import Config
from .server import ServerManager


class ToolLoader:
    """Middleman just to make the communicator and config available to commands."""

    config: Config
    server: ServerManager
    config_path: str

    def __init__(self, config_path) -> None:
        self.config_path = config_path

    def setup(self, config: Config):
        self.config = config
        self.server = ServerManager(self.config)


pass_loader = click.make_pass_decorator(ToolLoader, ensure=True)


class DetailedGroup(click.Group):
    """Override the default click help so it can actually show a wider width."""

    def format_help(self, ctx, formatter):
        formatter.width = get_terminal_size().columns
        super().format_help(ctx, formatter)

    def format_commands(
        self,
        ctx: click.Context,
        formatter: click.HelpFormatter,
    ) -> None:
        def command_tree(items, prefix: str = ""):
            rows = {prefix: []}
            for c_name, command in items:
                if isinstance(command, click.Group):
                    rows = rows | command_tree(
                        command.commands.items(),
                        f"{prefix} {c_name}".strip(),
                    )
                if isinstance(command, click.Command) and not command.hidden:
                    # Single instance
                    rows[prefix].append((f"{c_name}".strip(), command))
            return rows

        groups = command_tree(ctx.command.commands.items())  # type: ignore
        if len(groups):
            limit = get_terminal_size().columns

            formatter.write_paragraph()

            for group, commands in groups.items():
                if len(group):
                    formatter.write_heading(group)
                    formatter.indent()

                rows = []
                for subcommand, cmd in commands:
                    help = cmd.get_short_help_str(limit)
                    rows.append((subcommand, help))
                rows.sort()
                formatter.write_dl(rows)
                formatter.write_paragraph()
                if len(group):
                    formatter.dedent()


@click.group(
    invoke_without_command=True,
    cls=DetailedGroup,
    help="Utility commands related to running a Minecraft server.",
)
@click.option("--debug/--no-debug", default=False)
@click.option(
    "-C",
    "--config",
    type=click.Path(exists=False),
    default=None,
    multiple=False,
)
@click.pass_context
def cli(ctx: click.Context, debug, config):
    """Group all of our commands together"""
    ctx.ensure_object(dict)

    config_path = ""
    if config:
        config_path = Path(config)
    elif "PYTEST_CURRENT_TEST" not in os.environ:
        config_path = Path(click.get_app_dir("cmcserver.toml"))

    ctx.obj = ToolLoader(config_path)

    if ctx.invoked_subcommand in ("config", "readme", "backup", "server"):
        return

    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())
        ctx.exit()

    if not config_path:
        raise click.UsageError("No config file was defined")

    ctx.obj.setup(Config.load(config_path, debug))


### SERVER COMMANDS


@cli.group(invoke_without_command=True, cls=DetailedGroup)
@click.pass_context
def server(ctx: click.Context):
    """See commands relating to the server"""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())
        ctx.exit()


@server.command()
@pass_loader
def status(loader: ToolLoader):
    """See the status of the server"""
    x = loader.server.rcon_send(["list"])
    click.echo(x)


@server.command(name="stop")
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


@server.command(name="start")
@pass_loader
def start(loader: ToolLoader):
    """Boot the server."""
    loader.server.start()


@server.command(name="restart")
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


### BACKUP COMMANDS
@cli.group(invoke_without_command=True, cls=DetailedGroup)
@click.pass_context
def backup(ctx):
    """Backup and restore the game using both remote and local options"""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())
        ctx.exit()


@backup.command(name="create")
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
def base_backup(loader: ToolLoader, incremental: bool, sync: bool):
    """Create either a full or incremental backup"""
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
    cfile = click.format_filename(file)
    if not success:
        click.echo(f"Backup failed to compress, expected {cfile}")
        return

    click.echo(f"Backup saved in {cfile}")
    server.tell_all("Save complete", play_sound=False)

    if not sync:
        click.echo("No syncing, backup complete.")
        return

    # Upload the most recent backup file
    backup_manager.aws_sync(upload=True, limit=1)
    click.echo("Sync complete")


### AWS Commands
@backup.group(invoke_without_command=True, cls=DetailedGroup)
@click.pass_context
def aws(ctx):
    """Backup and restore the game using AWS as a remote storage option"""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())
        ctx.exit()


@aws.command(name="sync")
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
    """Upload and download full backup files to a configured AWS S3 bucket"""
    backup_manager = BackupManager(server=loader.server, incremental=False)

    backup_manager.aws_sync(upload=upload, download=download, limit=limit)


@aws.command("prune")
@click.option(
    "--count",
    default=10,
    type=click.IntRange(0, 20),
    help="Number of backups to keep in AWS",
)
@pass_loader
def prune_aws(loader: ToolLoader, count: int):
    """Delete excess backup files from a configured AWS S3 bucket"""
    backup_manager = BackupManager(server=loader.server, incremental=False)
    backup_manager.prune_aws(count)


### OTHER BACKUPS
@backup.command(name="git")
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


@backup.command("prune")
@click.option(
    "--count",
    default=10,
    type=click.IntRange(0, 20),
    help="Number of backups to keep locally",
)
@pass_loader
def prune_local(loader: ToolLoader, count: int):
    """Prune the backups in the local system"""
    backup_manager = BackupManager(server=loader.server, incremental=False)
    backup_manager.prune_local(count)
    click.echo("Prune complete")


### MISC COMMANDS


@cli.command("mods")
@pass_loader
def download_mods(loader: ToolLoader):
    """Run the download mods script if it is defined"""

    script_path = str(loader.config.get("mod_script") or "")
    if len(script_path) == 0:
        raise click.UsageError(
            "Must define a mod_script config to a shell script to run.",
        )

    script = Path(script_path)
    if not script.exists():
        raise click.UsageError(f"{script} does not exist.")

    from subprocess import STDOUT, call

    command = [str(script)]

    if loader.config.debug:
        click.echo(f"Command: {' '.join(command)}")
        return False

    call(
        command,
        cwd=str(script.parent),
        stderr=STDOUT,
        stdout=STDOUT,
    )
    click.echo("Complete")


@cli.command(name="config")
@click.option(
    "--edit",
    is_flag=True,
    default=False,
    help="Open the editor for this config file",
)
@click.option("--delete", is_flag=True, default=False, help="Delete the config file")
@click.option("--path", is_flag=True, default=False, help="Path of the config file")
@click.option(
    "--default",
    is_flag=True,
    default=False,
    help="Show the default config option",
)
@click.option(
    "--raw",
    is_flag=True,
    default=False,
    help="Show the value of the config file",
)
@click.option("--config", hidden=True, type=click.Path(dir_okay=False), default=None)
@pass_loader
def config(
    loader: ToolLoader,
    edit: bool,
    delete: bool,
    path: bool,
    default: bool,
    raw: bool,
    config,
):
    """Edit the configuration file, or generate it if it does not exist."""

    config_file = Path(config or loader.config_path)
    config_file_str = click.format_filename(config_file)

    if default:
        click.echo(Config.dumps())
        return

    exists = config_file.exists()

    if path:
        click.echo(config_file_str)
        return

    if not exists:
        click.echo(f'Config file "{config_file_str}" does not exist.')
        if click.confirm("Do you want to create it with default values?"):
            Config.write(config_file)
            click.echo(f'Created config file "{config_file_str}"')
        else:
            click.echo("No config file was created.")
            return

    if edit:
        click.edit(
            filename=loader.config_path,
            extension=".toml",
        )
        return

    if delete:
        config_file.unlink()
        click.echo("Deleted the config file")
        return

    if raw:
        click.echo(config_file.read_text())
    else:
        cfg = Config.load(config_file, False)
        click.echo(cfg.flatten())


@cli.command(
    name="readme",
    help="Update the readme with the config & commands",
)
@click.argument(
    "readme",
    type=click.Path(
        exists=True,
        dir_okay=False,
        writable=True,
        readable=True,
        resolve_path=True,
        path_type=pathlib.Path,
    ),
    default="README.md",
)
@click.pass_context
def write_readme_config(ctx: click.Context, readme: pathlib.Path):
    content = Config.dumps().splitlines()
    to_write = []
    with open(readme) as f:
        in_config = False
        in_commands = False
        for line in f:
            if "# (config-start)" in line:
                in_config = True
                to_write.append(line)
                to_write.append("```\n")
                to_write.append("\n".join(content))
                continue
            elif "# (config-end)" in line:
                in_config = False
                to_write.append("\n```\n")
                to_write.append(line)
                continue
            elif "# (command-start)" in line:
                in_commands = True
                to_write.append(line)
                to_write.append("```\n")
                to_write.append(ctx.find_root().get_help())
                continue
            elif "# (command-end)" in line:
                in_commands = False
                to_write.append("\n```\n")
                to_write.append(line)
                continue

            if not in_config and not in_commands:
                to_write.append(line)
    with open(readme, "w") as f:
        f.write("".join(to_write))
    click.echo("Readme has been updated")
