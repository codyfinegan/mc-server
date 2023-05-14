import datetime
import subprocess
from pathlib import Path

import boto3
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
        """Copy the game world contents across to the backup folder."""
        self.server.save_off()

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

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
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

    def aws_sync(self, upload: bool = False, download: bool = False, limit: int = 2):
        """Sync the backups folder with AWS S3

        Args:
            upload (bool, optional): Write missing backup files into AWS. Defaults to False.
            download (bool, optional): Download missing backup files locally. Defaults to False.
            limit (int, optional): Number of most recent files to download or upload. Defaults to 2.
        """
        if self.incremental:
            click.echo("Cannot AWS ship incremental")
            return self

        bucket = self.server.config.tree("backups", "aws_bucket")
        if not bucket or len(bucket) == 0:
            click.echo("No backups.aws_bucket is defined in config.")
            return
        subfolder = self.server.config.tree("backups", "aws_subfolder")
        if len(subfolder):
            subfolder = f"{subfolder}/"

        # Figure out what files we're going to upload
        path = Path(self.backup_dest)
        paths = list()

        for file in path.rglob(self.server.config.tree("backups", "name") % "*"):
            if file.is_dir():
                continue
            paths.append(str(file).replace(f"{str(path)}/", ""))

        paths = set(sorted(paths))

        s3 = boto3.client("s3")
        try:
            objects = s3.list_objects_v2(
                Bucket=bucket,
                Prefix=subfolder,
                EncodingType="url",
            )["Contents"]
            if len(objects) > 0:
                contents = set([obj["Key"].replace(subfolder, "") for obj in objects])
        except KeyError:
            contents = set()

        combined = paths.union(contents)
        valid_files = set(sorted(combined, reverse=True)[0:limit])

        to_upload = valid_files - contents
        to_upload_str = ", ".join(to_upload) if to_upload else "None"

        click.echo(f"Missing from S3 (prefix {subfolder}): {to_upload_str}")

        to_download = valid_files - paths
        to_download_str = ", ".join(to_download) if to_download else "None"

        click.echo(f"Missing from local: {to_download_str}")

        # Upload the files if needed
        if upload and to_upload:
            for sync_path in to_upload:
                key = subfolder + sync_path
                local_file = str(path.joinpath(sync_path))
                click.echo(f"Uploading {local_file}...")
                s3.upload_file(local_file, Bucket=bucket, Key=key)
                click.echo(f"Uploaded {local_file} to s3://{bucket}/{key}")
        else:
            click.echo(f"Not uploading - {len(to_upload)} potentially (max {limit})")

        # Download the files if needed
        if download and to_download:
            for download_file in to_download:
                key = subfolder + download_file
                local_file = str(path.joinpath(download_file))
                click.echo(f"Downloading s3://{bucket}/{key}...")
                s3.download_file(bucket, key, local_file)
                click.echo(f"Downloaded s3://{bucket}/{key} to {local_file}")
        else:
            click.echo(
                f"Not downloading - {len(to_download)} potentially (max {limit})",
            )
