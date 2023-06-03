import json
import math
import subprocess
import time
from pathlib import Path
from typing import List

import click
from mctools import PINGClient, RCONClient

from .configuration import Config


def debug_echo(debug: bool, message: str) -> None:
    if debug:
        click.echo(message)


def text_prefix(code: str = "SERVER") -> list:
    return [
        {"text": "[", "color": "gray"},
        {"text": code, "color": "yellow"},
        {"text": "] ", "color": "gray"},
    ]


def seconds_to_countdown(seconds: int, range: List[int] = None) -> list:
    # Be given a range of seconds, then break it down
    # into call points, and how long to wait in between each

    if seconds < 5:
        seconds = 10

    if range is None:
        range = [600, 300, 180, 120, 60, 30, 10, 5]

    countdown = []

    # Find our range
    t_range = []
    for step in range:
        if seconds >= step:
            t_range.append(step)

    upper = max(t_range)
    if seconds > upper:
        t_range.insert(0, seconds)

    # Now build our actual call object
    last = max(t_range)
    for step in t_range:
        countdown.append((last - step, seconds_to_time_text(step)))
        last = step

    last_r = countdown.pop()
    countdown.append((last_r[0], None))

    return countdown


def seconds_to_time_text(seconds: int) -> str:
    t_mins = math.floor(seconds / 60)
    t_seconds = seconds % 60

    if t_mins == 1 and t_seconds:
        return f"{t_mins} minute and {t_seconds} seconds"
    if t_mins and t_seconds:
        return f"{t_mins} minutes and {t_seconds} seconds"
    if t_mins and t_mins == 1:
        return f"{t_mins} minute"
    if t_mins:
        return f"{t_mins} minutes"
    if t_seconds > 9:
        return f"{t_seconds} seconds"
    return f"{t_seconds}"


class ServerManager:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.debug = self.config.debug
        self.client = None

    def _get_client(self):
        if type(self.client) == RCONClient and self.client.is_authenticated:
            return self.client

        host = self.config.data["server"]["host"]
        port = self.config.data["server"]["rcon_port"]
        password = self.config.data["server"]["rcon_password"]

        self.client = RCONClient(host, port, format_method=RCONClient.REMOVE)
        if not self.client.login(password):
            debug_echo(self.config.debug, "Login refused")
            raise ConnectionRefusedError

        debug_echo(self.config.debug, "Login complete")
        return self.client

    def _raw_send(self, commands: List[str]):
        r = list()
        rcon = self._get_client()

        for command in commands:
            debug_echo(self.debug, f"Command send: {command}")
            r.append((command, rcon.command(command)))

        return r

    def _ping_server(self, ping: bool = True):
        try:
            debug_echo(self.config.debug, "Attempting to ping the server...")
            host = self.config.data["server"]["host"]
            port = self.config.data["server"]["query_port"]

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

    def rcon_send(self, commands: List[str]):
        if type(commands) == str:
            commands = [commands]
        try:
            debug_echo(self.debug, "Starting to login...")
            return self._raw_send(commands)
        except ConnectionRefusedError as e:
            debug_echo(self.debug, str(e))
            host = self.config.data["server"]["host"]
            port = self.config.data["server"]["rcon_port"]
            raise click.UsageError(f"Unable to connect to server {host}:{port}")

    def save_off(self):
        if not self.screen_exists():
            click.echo("Server is not live, save-off not needed.")
            return self

        self.rcon_send(["/save-all"])
        time.sleep(3)
        self.rcon_send(["/save-off"])
        time.sleep(2)
        return self

    def save_on(self):
        if not self.screen_exists():
            click.echo("Server is not live, save-on not needed.")
            return self

        self.rcon_send(["/save-on"])
        time.sleep(2)
        return self

    def screen_exists(self) -> bool:
        command = ["screen", "-list", "mcs"]
        retcode = subprocess.call(command, stdout=subprocess.PIPE)
        if retcode == 0:
            return True
        return False

    def _screen_start(self, debug: bool, startup_script: Path, sleep: int):
        command = ["screen", "-dmS", "mcs", "sh", "-c", str(startup_script)]

        if debug:
            click.echo(f"Command: {' '.join(command)}")
            return False

        code = subprocess.call(
            command,
            cwd=str(startup_script.parent),
            stderr=subprocess.STDOUT,
        )
        if code == 1 and not self.screen_exists():
            click.echo("There was an error with the startup script.")
            raise SystemExit

        time.sleep(sleep)

        # Check, is our screen running?
        if not self.screen_exists():
            click.echo(f"No screen session was detected after {sleep} seconds.")
            return False

        # Screen has loaded, we don't know about the server but screen is running
        return True

    def tell_all(
        self,
        message: str,
        formatted: bool = False,
        color: str = "gray",
        italic: bool = False,
        play_sound: bool = True,
        sound: str = "ui.button.click",
        prefixed: bool = True,
    ):
        if not self.screen_exists():
            click.echo(f"Server not running, did not send: {message}")
            return

        if not formatted:
            click.echo(message)
            message = [
                {
                    "text": message,
                    "color": color,
                    "italic": italic,
                },
            ]

            if prefixed:
                message = text_prefix() + message

            message = json.dumps(message)

        commands = [
            f"/tellraw @a {message}",
        ]
        if play_sound:
            commands.insert(0, f"playsound minecraft:{sound} voice @a")

        debug_echo(self.config.debug, commands)
        self.rcon_send(commands)

    def start(self):
        if self.screen_exists():
            click.echo(
                "There is already a running server (or at least a screen session.)",
            )
            click.echo("Run `screen -ls mcs` to see the existing processes.")
            return

        click.echo("Starting server...")

        startup = Path(self.config.get("startup_script"))

        if not self._screen_start(
            self.config.debug,
            startup,
            self.config.get("boot_pause"),
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
            if self._ping_server():
                loaded = True
                break
            click.echo("Not yet, waiting a few moments...")
            time.sleep(5)

        if loaded:
            click.echo("Server has been loaded.")
        else:
            click.echo(
                "Could not tell if the server loaded successfully, check it out.",
            )
            click.echo("Make sure rcon/query has been configured")

    def stop(self, reason: str = None, countdown: int = 5, action: str = "stopping"):
        if not self.screen_exists() and not self._ping_server():
            click.echo("Server is not running")
            return

        if not reason:
            reason = ""
        else:
            reason = f" {reason}"

        if countdown < 5:
            countdown = 5

        self.tell_all(
            f"The server is {action} in {countdown} seconds{reason}",
            sound="block.bell.use",
        )

        for sleep, text in seconds_to_countdown(countdown):
            time.sleep(sleep)
            if text:
                self.tell_all(
                    f"The server is {action} in {text}",
                    sound="block.bell.use",
                )

        # Final 5 second countdown
        for i in range(5, 0, -1):
            self.tell_all(f"In {i}...")
            time.sleep(1)

        self.tell_all("Off we go!", sound="block.bell.use")
        time.sleep(1)
        self.rcon_send(
            [
                f"/kick @a Sever is {action}, check Discord for info",
                "/stop",
            ],
        )

        # Now wait
        time.sleep(5)
        if self.screen_exists():
            down = False
            for i in range(1, 100):
                if not self.screen_exists():
                    down = True
                    break
                time.sleep(2)

        if down:
            click.echo("Server has stopped")
        else:
            click.echo(
                "Waited, but could not tell if the server stopped. Try checking screen.",
            )
