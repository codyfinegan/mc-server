from pathlib import Path

import click
import tomlkit
from tomlkit.items import String, Table


def default_config() -> dict:
    return {
        "server": {
            "host": "127.0.0.1",
            "rcon_port": 25575,
            "rcon_password": "",
            "query_port": 25565,
        },
        "backups": {
            "folder": "/path/to/backups",
            "full": "full",
            "incremental": "incremental",
            "compress": "/usr/bin/zstd -19 -T2",
            "name": "%s.tar.zst",
            "aws": {
                "bucket": "",
                "subfolder": "",
            },
            "git": {
                "push": False,
            },
        },
        "startup_script": "/path/to/startup_script.sh",
        "game_folder": "/path/to/game",
        "mod_script": "/path/to/mod_downloads.sh",
        "world": "world",
        "boot_pause": 25,
    }


def default_config_toml() -> tomlkit.TOMLDocument:
    cfg = default_config()
    doc = tomlkit.document()
    doc.add(tomlkit.comment("Configuration for cmcserver command"))
    doc.add(tomlkit.nl())

    doc.add("startup_script", cfg["startup_script"])
    doc["startup_script"].comment(  # type: ignore
        "Full path to the startup script.",
    )
    doc.add("game_folder", cfg["game_folder"])
    doc["game_folder"].comment(  # type: ignore
        "The path to the minecraft base folder that holds the world_name",
    )
    doc.add("world", cfg["world"])
    doc["world"].comment(  # type: ignore
        "Name of the minecraft game folder",
    )
    doc.add("boot_pause", cfg["boot_pause"])
    doc["boot_pause"].comment(  # type: ignore
        "How long to wait for the server to start before continuing. Increase this if needed.",
    )
    doc.add("mod_script", cfg["mod_script"])
    doc["mod_script"].comment(  # type: ignore
        "Full path to the script used to download mods.",
    )
    doc.add(tomlkit.nl())

    table = tomlkit.table()
    table.add(
        tomlkit.comment(
            "Options related to server access, check your server.properties file.",
        ),
    )
    table.add(
        tomlkit.comment(
            "If running on the same server, make sure ports are blocked exernally",
        ),
    )
    table.add(tomlkit.comment("so rcon and query cannot be accessed externally."))
    table.add("host", cfg["server"]["host"])
    table.add("rcon_password", cfg["server"]["rcon_password"])
    table.add("rcon_port", cfg["server"]["rcon_port"])
    table.add("query_port", cfg["server"]["query_port"])
    table["rcon_password"].comment("Password set in server.properties. Make it good.")
    doc.add("server", table)

    doc.add(tomlkit.nl())

    table = tomlkit.table()
    table.add(
        tomlkit.comment(
            "Backup configuration.",
        ),
    )
    table.add("folder", cfg["backups"]["folder"])
    table.add("full", cfg["backups"]["full"])
    table.add("incremental", cfg["backups"]["incremental"])
    table.add("compress", cfg["backups"]["compress"])
    table.add("name", cfg["backups"]["name"])

    aws = tomlkit.table()
    aws.add("bucket", cfg["backups"]["aws"]["bucket"])
    aws.add("subfolder", cfg["backups"]["aws"]["subfolder"])
    aws["bucket"].comment(
        "Bucket to store full backups in.",
    )
    aws["subfolder"].comment(
        "Path inside the bucket to store backups in.",
    )
    table.add("aws", aws)

    git = tomlkit.table()
    git.add("push", tomlkit.boolean(cfg["backups"]["git"]["push"]))
    table.add("git", git)

    table["folder"].comment("Base path to the backups folder")
    table["compress"].comment("Command to apply compression to the backups")
    table["name"].comment(
        "Syntax of the backup filename. If compression changes, change the extension here.",
    )
    doc.add("backups", table)

    return doc


class Config:
    """Config object parses and holds the config read from file."""

    def __init__(self, data: dict, debug) -> None:
        self.data = default_config() | data
        self.debug = debug
        pass

    def __str__(self) -> str:
        return str(self.data)

    def get(self, key) -> str | dict | None:
        if key in self.data:
            return self.data[key]
        return None

    def get_str(self, key) -> str:
        val = self.get(key)
        if type(val) == str:
            return val
        if type(val) == String:
            return str(val)
        raise TypeError(f"{key} was not a string (was {type(val)})")

    def get_dict(self, key) -> dict:
        val = self.get(key)
        if type(val) == dict:
            return val
        if type(val) == Table:
            return dict(val)

        raise TypeError(f"{key} was not a dict (was {type(val)})")

    def tree(self, *keys) -> str | dict | None:
        val = self.data
        for key in keys:
            if type(val) == dict and key in val:
                val = val[key]
            else:
                val = None
        return val

    def tree_str(self, *keys) -> str:
        val = self.tree(keys)
        if type(val) == str:
            return val
        raise TypeError(f"{'.'.join(keys)} was not a string")

    @classmethod
    def load(cls, config_file: Path, debug: bool):
        """Parse the provided config file and return a config instance.

        Args:
            config_file (Path): TOML file config path.

        Raises:
            SystemExit: Will exit if the file does not exist.

        Returns:
            Config: Returns an instance of the Config class
        """
        # Don't create the file if it doesn't exist, make them do it
        if not config_file.exists():
            click.echo(f"Config is read from: {config_file}")
            click.echo(
                "Config file does not exist. Please create it or call the --init attribute.",
            )
            raise SystemExit

        with open(config_file, mode="rt", encoding="utf-8") as fp:
            data = tomlkit.load(fp)
            return cls(data, debug)

    @classmethod
    def dumps(cls):
        doc = default_config_toml()
        return str(tomlkit.dumps(doc))

    @classmethod
    def write(cls, config_file: Path):
        """Create a default config file in the provided path."""

        doc = default_config_toml()
        click.echo(tomlkit.dumps(doc))

        with open(config_file, mode="wt", encoding="utf-8") as fp:
            tomlkit.dump(doc, fp)
