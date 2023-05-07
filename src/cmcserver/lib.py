import json
import subprocess
import time
from pathlib import Path
from typing import List

import click
import tomlkit
from mctools import PINGClient, RCONClient


def debug_echo(debug: bool, message: str) -> None:
    if debug:
        click.echo(message)


def default_config() -> dict:
    return {
        "server": {
            "host": "127.0.0.1",
            "rcon_port": 25575,
            "rcon_password": "",
            "query_port": 25565,
        },
        "context_dir": "/path/to/game/folder",
        "startup": "startup_script.sh",
        "boot_pause": 15,
    }


def default_config_toml() -> tomlkit.document:
    cfg = default_config()
    doc = tomlkit.document()
    doc.add(tomlkit.comment("Configuration for cmcserver command"))
    doc.add(tomlkit.nl())

    doc.add("context_dir", cfg["context_dir"])
    doc["context_dir"].comment(
        "The path to the folder containing the game / startup script.",
    )
    doc.add("startup", cfg["startup"])
    doc["startup"].comment(
        "The actual shell script or whatever that will invoke the server.",
    )
    doc.add("boot_pause", cfg["boot_pause"])
    doc["boot_pause"].comment(
        "How long to wait for the server to start before continuing. Increase this if needed.",
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

    return doc


class Config:
    """Config object parses and holds the config read from file."""

    def __init__(self, data: dict, debug) -> None:
        self.data = default_config() | data
        self.debug = debug
        pass

    def __str__(self) -> str:
        return str(self.data)

    def get(self, key):
        return self.data[key]

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

        with open(config_file, mode="rt", encoding="utf-8") as fp:
            data = tomlkit.load(fp)
            return cls(data, debug)

    @classmethod
    def write(cls, config_file: str, force: bool):
        """Create a default config file in the provided path.

        Args:
            config_file (str): Path to the config file.
        """
        if config_file.exists():
            click.echo(f"Config is read from: {config_file}")
            if not force:
                click.echo(
                    "Config file already exists. Please delete it if you want to init again.",
                )
                return

        config_file = Path(config_file)
        doc = default_config_toml()

        with open(config_file, mode="wt", encoding="utf-8") as fp:
            tomlkit.dump(doc, fp)
            click.echo(f"Created config file {config_file}")


class Communicator:
    """Communication class to a RCON service"""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.client = None

    def ping_server(self, ping: bool = True):
        try:
            debug_echo(self.cfg.debug, "Attempting to ping the server...")
            host = self.cfg.data["server"]["host"]
            port = self.cfg.data["server"]["query_port"]

            ping_q = PINGClient(host=host, port=port, format_method=PINGClient.REMOVE)

            if not ping:
                return ping_q.get_stats()

            ping_q.ping()
            return True
        except IndexError:
            # Happens when we ping too soon
            return False
        except ConnectionError:
            return False

    def _get_client(self):
        if type(self.client) == RCONClient and self.client.is_authenticated:
            return self.client

        host = self.cfg.data["server"]["host"]
        port = self.cfg.data["server"]["rcon_port"]
        password = self.cfg.data["server"]["rcon_password"]

        self.client = RCONClient(host, port, format_method=RCONClient.REMOVE)
        if not self.client.login(password):
            debug_echo(self.cfg.debug, "Login refused")
            raise ConnectionRefusedError

        debug_echo(self.cfg.debug, "Login complete")
        return self.client

    def _raw_send(self, commands: List[str]):
        r = list()
        rcon = self._get_client()

        for command in commands:
            debug_echo(self.cfg.debug, f"Command send: {command}")
            r.append((command, rcon.command(command)))

        return r

    def send(self, commands: List[str]):
        if type(commands) == str:
            commands = [commands]
        try:
            debug_echo(self.cfg.debug, "Starting to login...")
            return self._raw_send(commands)
        except ConnectionRefusedError as e:
            debug_echo(self.cfg.debug, str(e))
            host = self.cfg.data["server"]["host"]
            port = self.cfg.data["server"]["rcon_port"]
            raise click.UsageError(f"Unable to connect to server {host}:{port}")

    def tell_all(
        self,
        message: str,
        formatted: bool = False,
        color: str = "gray",
        italic: bool = True,
        play_sound: bool = True,
        sound: str = "ui.button.click",
    ):
        if not formatted:
            message = {
                "text": message,
                "color": color,
                "italic": italic,
            }
            message = json.dumps(message)

        commands = [
            f"/tellraw @a {message}",
        ]
        if play_sound:
            commands.insert(0, f"playsound minecraft:{sound} voice @a")

        debug_echo(self.cfg.debug, commands)
        self.send(commands)


class ToolLoader:
    """Middleman just to make the communicator and config available to commands."""

    def setup(self, config: Config):
        self.config = config
        self.communicator = Communicator(config)


class ScreenManager:
    """Simple commands for managing screen calls."""

    @staticmethod
    def exists() -> bool:
        command = ["screen", "-list", "mcs"]
        retcode = subprocess.call(command, stdout=subprocess.PIPE)
        if retcode == 0:
            return True
        return False

    @staticmethod
    def start(debug: bool, startup_script: Path, context_path: Path, sleep: int):
        command = ["screen", "-dmS", "mcs", "sh", "-c", startup_script]

        if debug:
            click.echo("Command: " + " ".join(command))
            return False

        process = subprocess.Popen(
            command,
            cwd=context_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        process.wait()

        time.sleep(sleep)

        # Check, is our screen running?
        if not ScreenManager.exists():
            click.echo(f"No screen session was detected after {sleep} seconds.")
            return False

        # Screen has loaded, we don't know about the server but screen is running
        return True
