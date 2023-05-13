import datetime
import subprocess
from pathlib import Path

import click

from .server import ServerManager


class BackupManager:
    def __init__(self, server: ServerManager, incremental: bool = False) -> None:
        self.server = server
        self.cfg = server.config
        self.incremental = incremental
        self.cfg_backups = self.server.config.get("backups")

        # Calculate the backup folder
        self.backup_dest_base = Path(self.cfg_backups["folder"])
        self.backup_dest = self.backup_dest_base.joinpath(
            self.cfg_backups["incremental"]
            if incremental
            else self.cfg_backups["full"],
        )

        if not self.backup_dest.exists():
            self.backup_dest.mkdir(parents=True)

        self.backup_source = Path(self.cfg.get("game_folder")).joinpath(
            self.cfg.get("world"),
        )

        self.backup_dest_world = self.backup_dest.joinpath(self.cfg.get("world"))

        if not self.backup_source.exists():
            click.echo(f"Game folder does not exist: {self.backup_source}")

    def sync_world_folder(self):
        self.server.save_off()

        """Copy the game world contents across to the backup folder."""
        command = [
            "rsync",
            "-xavh",
            "--delete",
            "--exclude=.git",
            str(self.backup_source),
            str(self.backup_dest),
        ]

        subprocess.call(command, cwd=self.backup_source, stderr=subprocess.STDOUT)

        self.server.save_on()
        return self

    def compress_backup(self):
        if self.incremental:
            click.echo("Cannot compress incremental.")
            return self

        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        compressed_name = (
            self.cfg_backups["name"] % f"{self.backup_dest_world}_{timestamp}"
        )

        if not self.cfg_backups["compress"]:
            command = [
                "tar",
                "-c",
                "-f",
                str(compressed_name),
                "-C",
                str(self.backup_dest_world),
                ".",
            ]
        else:
            command = [
                "tar",
                "-c",
                "-I",
                f"{self.cfg_backups['compress']}",
                "-f",
                str(compressed_name),
                "-C",
                str(self.backup_dest_world),
                ".",
            ]

        subprocess.call(
            command,
            cwd=str(self.backup_dest),
            stderr=subprocess.STDOUT,
        )

        if Path(compressed_name).exists():
            return True, compressed_name
        else:
            return False, compressed_name

    def git_push(self):
        click.echo("TODO - incremental sync")
        pass

    def aws_sync(self):
        click.echo("TODO - aws s3 syncing")
        pass
