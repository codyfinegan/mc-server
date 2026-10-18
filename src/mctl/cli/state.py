"""State shared by every commannd"""

from functools import cached_property
from pathlib import Path

import click

from mctl.config import ConfigError, Settings, load


class ConfigFailed(click.ClickException):
    """A config error, reported with exit code 2."""

    exit_code = 2

    def __init__(self, error: ConfigError):
        lines = "\n".join(f" {message}" for message in error.messages)
        super().__init__(f"config error in {error.path}:\n{lines}")


class AppState:
    """Holds the config path; loads settings the first time a command needs them"""

    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path

    @cached_property
    def settings(self) -> Settings:
        try:
            return load(self.config_path)
        except ConfigError as e:
            raise ConfigFailed(e) from e
