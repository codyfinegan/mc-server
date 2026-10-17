from collections.abc import Callable
from pathlib import Path

import pytest

MINIMAL_TOML = """\
[server]
dir = "/srv/minecraft"
start_command = "./run.sh"
"""


@pytest.fixture
def minimal_toml() -> str:
    """The smallest valid config, for tests to extend."""
    return MINIMAL_TOML


@pytest.fixture
def write_config(tmp_path: Path) -> Callable[[str], Path]:
    """Return a function that writes TOML to tmp_path/config.toml."""

    def write(text: str) -> Path:
        path = tmp_path / "config.toml"
        path.write_text(text)
        return path

    return write
