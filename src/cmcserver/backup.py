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
        self.cfg_backups = self.server.config.get_dict("backups")

        # Calculate the backup folder
        self.backup_dest_base = Path(self.cfg_backups["folder"])
        self.backup_dest = self.backup_dest_base.joinpath(
            self.cfg_backups["incremental"]
            if incremental
            else self.cfg_backups["full"],
        )

        if not self.backup_dest.exists():
            self.backup_dest.mkdir(parents=True)

        self.backup_source = Path(self.cfg.get_str("game_folder")).joinpath(
            self.cfg.get_str("world"),
        )

        self.backup_dest_world = self.backup_dest.joinpath(self.cfg.get_str("world"))

        if not self.backup_source.exists():
            click.echo(f"Game folder does not exist: {self.backup_source}")

    def _s3(self):
        endpoint_url = None
        aws_service = self.cfg.tree_str("backups", "aws", "service")
        if aws_service:
            endpoint_url = aws_service

        client = boto3.client("s3", endpoint_url=endpoint_url)

        return client

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
            raise click.UsageError("Cannot compress incremental.")

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

    def git_sync(self, push: bool = False):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        command = [
            "git",
            "commit",
            "-am",
            f"Backup at {timestamp}",
        ]

        subprocess.call(
            command,
            cwd=str(self.backup_dest_world),
            stderr=subprocess.STDOUT,
        )

        if push:
            command = [
                "git",
                "push",
            ]
            subprocess.call(
                command,
                cwd=str(self.backup_dest_world),
                stderr=subprocess.STDOUT,
            )

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

        bucket = self.server.config.tree_str("backups", "aws", "bucket")
        if not bucket or len(bucket) == 0:
            click.echo("No backups.aws.bucket is defined in config.")
            return
        subfolder = self.server.config.tree_str("backups", "aws", "subfolder")
        if len(subfolder):
            subfolder = f"{subfolder}/"

        # Figure out what files we're going to upload
        path = Path(self.backup_dest)
        paths = list()

        for file in path.rglob(self.server.config.tree_str("backups", "name") % "*"):
            if file.is_dir():
                continue
            paths.append(str(file).replace(f"{str(path)}/", ""))

        paths = set(sorted(paths))

        s3 = self._s3()
        contents = set()
        try:
            objects = s3.list_objects_v2(
                Bucket=bucket,
                Prefix=subfolder,
                EncodingType="url",
            )["Contents"]
            if len(objects) > 0:
                contents = set([obj["Key"].replace(subfolder, "") for obj in objects])
        except KeyError:
            pass

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

    def prune_local(self, count: int, yes: bool):
        # Load the list of files
        path = Path(self.backup_dest)
        paths = list()
        for file in path.rglob(self.server.config.tree_str("backups", "name") % "*"):
            if file.is_dir():
                continue
            paths.append(str(file).replace(f"{str(path)}/", ""))

        contents = sorted(paths)
        remove = contents[: -count or None]
        keep = contents[-count:]

        click.echo(
            self._print_files(keep, "We are going to keep the following files:", 8),
        )
        click.echo()

        if remove:
            click.echo(
                self._print_files(
                    remove,
                    "We are going to delete the following files:",
                    100,
                ),
            )
            click.echo()

            if not yes and not click.confirm("Confirm?"):
                click.echo("Delete rejected.")
                return self

            for file_path in remove:
                path.joinpath(file_path).unlink()
                click.echo(f"Deleting {file_path}")
            click.echo()
            click.echo("Complete")
        else:
            click.echo("Nothing to delete")

    def prune_aws(self, count: int, yes: bool):
        if self.incremental:
            click.echo("Cannot prune in incremental mode")
            return self

        if count <= 0:
            click.echo("Count must be 1 or more")
            return self

        bucket = self.server.config.tree_str("backups", "aws", "bucket")
        if not bucket or len(bucket) == 0:
            click.echo("No backups.aws.bucket is defined in config.")
            return
        subfolder = self.server.config.tree_str("backups", "aws", "subfolder")
        if len(subfolder):
            subfolder = f"{subfolder}/"

        s3 = self._s3()
        contents = list()
        try:
            objects = s3.list_objects_v2(
                Bucket=bucket,
                Prefix=subfolder,
                EncodingType="url",
            )["Contents"]
            if len(objects) > 0:
                for obj in objects:
                    val = obj["Key"].replace(subfolder, "")
                    if val:
                        contents.append(val)
        except KeyError:
            pass

        remove = contents[: -count or None]
        keep = contents[-count:]
        click.echo(
            self._print_files(keep, "We are going to keep the following files:", 8),
        )
        click.echo()

        if remove:
            click.echo(
                self._print_files(
                    remove,
                    "We are going to delete the following files:",
                    100,
                ),
            )
            click.echo()

            if not yes and not click.confirm("Confirm?"):
                click.echo("Delete rejected.")
                return self

            for file in remove:
                s3.delete_object(
                    Bucket=bucket,
                    Key=f"{subfolder}{file}",
                )
                click.echo(f"Deleted {subfolder}{file}")
            click.echo()
            click.echo("Complete")
        else:
            click.echo("Nothing to delete")

        return self

    @staticmethod
    def _print_files(files: list, message: str, max: int = 8) -> str:
        return message + "\n + %s" % "\n + ".join(files[:max])
