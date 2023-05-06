try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

from pathlib import Path
from typing import List

import click
from mctools import RCONClient  # Import the RCONClient


def debug_echo(debug: bool, message: str) -> None:
    if debug:
        click.echo(message)


class Config:
    """Config object parses and holds the config read from file."""

    def __init__(self, data: dict, debug) -> None:
        self.data = data
        self.debug = debug
        pass

    def __str__(self) -> str:
        return str(self.data)

    def get(self, key):
        return self.data[key]

    def server(self, key):
        return self.data["server"][key]

    @classmethod
    def load(cls, config_file: str, debug: bool):
        """Parse the provided config file and return a config instance.

        Args:
            config_file (str): TOML file config path.

        Raises:
            SystemExit: Will exit if the file does not exist.

        Returns:
            Config: Returns an instance of the Config class
        """
        config_file = Path(config_file)

        # Don't create the file if it doesn't exist, make them do it
        if not config_file.exists():
            click.echo(f"Config is read from: {config_file}")
            click.echo(
                "Config file does not exist. Please create it or call the --init attribute.",
            )
            raise SystemExit

        data = tomllib.loads(config_file.read_text(encoding="utf-8"))
        return cls(data, debug)

    @classmethod
    def write(cls, config_file: str):
        """Create a default config file in the provided path.

        Args:
            config_file (str): Path to the config file.
        """
        if config_file.exists():
            click.echo(f"Config is read from: {config_file}")
            click.echo(
                "Config file already exists. Please delete it if you want to init again.",
            )
            return

        config_file = Path(config_file)
        with open(config_file, "w") as f:
            f.write("# Default Configuration")
            click.echo(f"Created config file {config_file}")


class Communicator:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    def _send(self, commands: List[str]):
        host = self.cfg.server("host")
        port = self.cfg.server("port")
        password = self.cfg.server("password")

        try:
            debug_echo(self.cfg.debug, "Starting to login...")
            rcon = RCONClient(host, port)
            if rcon.login(password):
                for command in commands:
                    debug_echo(self.cfg.debug, f"Command send: {command}")
                    resp = rcon.command(command)
                    click.echo(resp)
        except ConnectionRefusedError as e:
            debug_echo(self.cfg.debug, str(e))
            raise click.UsageError(f"Unable to connect to server {host}:{port}")

    def online(self):
        self._send(["/list"])
