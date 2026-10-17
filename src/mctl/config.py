"""Load and validate mctl's config"""

import os
import tomllib
from pathlib import Path
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    ValidationError,
    ValidationInfo,
)

DEFAULT_CONFIG = Path("~/.config/mctl/config.toml")


class ConfigError(Exception):
    """Config could not be found, parsed or validated"""

    def __init__(self, path: Path, messages: list[str]) -> None:
        super().__init__(f"{path}: {'; '.join(messages)}")
        self.path = path
        self.messages = messages


def _resolve(value: Path, info: ValidationInfo) -> Path:
    value = value.expanduser()
    if value.is_absolute():
        return value
    context = info.context or {}
    if "base_dir" not in context:
        raise ValueError("relative path needs base_dir in the validation context")
    return Path(os.path.normpath(context["base_dir"] / value))


ConfigPath = Annotated[Path, AfterValidator(_resolve)]


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ServerConfig(_Section):
    dir: ConfigPath
    start_command: str
    screen_session: str = "mcs"


class JavaConfig(_Section):
    path: ConfigPath = Path("/usr/bin/java")
    min_version: int = 25


class McaConfig(_Section):
    jar: ConfigPath
    jvm_args: list[str] = []


class PackwizConfig(_Section):
    bootstrap_jar: ConfigPath
    pack_url: str


class ResticConfig(_Section):
    repository: str
    password_file: ConfigPath


class Settings(_Section):
    server: ServerConfig
    java: JavaConfig = JavaConfig()
    mca: McaConfig | None = None
    packwiz: PackwizConfig | None = None
    restic: ResticConfig | None = None


def find_config(path: Path | None = None) -> Path:
    if path is None:
        path = DEFAULT_CONFIG
    return path.expanduser()


def load(path: Path) -> Settings:
    """Read, parse and validate the config file at path"""
    try:
        with path.open("rb") as fp:
            data = tomllib.load(fp)
    except OSError as e:
        raise ConfigError(path, [e.strerror or str(e)]) from e
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(path, [str(e)]) from e

    try:
        return Settings.model_validate(
            data, context={"base_dir": path.absolute().parent}
        )
    except ValidationError as e:
        raise ConfigError(path, _format(e)) from e


def _format(error: ValidationError) -> list[str]:
    """One dotted.location: message line per validation error."""
    return [
        f"{'.'.join(str(part) for part in err['loc'])}: {err['msg']}"
        for err in error.errors()
    ]
