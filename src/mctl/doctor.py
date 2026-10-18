"""Pre-flight checks for the tools, jars and server settings mctl needs."""

import re
import shutil
import stat
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from mctl.config import Settings
from mctl.properties import load_properties

Which = Callable[[str], str | None]
Run = Callable[[Sequence[str]], str]

_JAVA_VERSION = re.compile(r"\S+ (\d+)")


class Status(StrEnum):
    OK = "ok"
    FAIL = "fail"
    SKIP = "skip"


@dataclass(frozen=True)
class Check:
    name: str
    status: Status
    detail: str


def run_command(args: Sequence[str]) -> str:
    """Run a command and return its stdout. Raises if it fails or hangs."""
    result = subprocess.run(
        args, capture_output=True, text=True, check=True, timeout=10
    )
    return result.stdout


def run_checks(
    settings: Settings, which: Which = shutil.which, run: Run = run_command
) -> list[Check]:
    """Run every check. Sections that aren't configured are skipped."""
    mca, packwiz, restic = settings.mca, settings.packwiz, settings.restic
    return [
        check_java(settings.java.path, settings.java.min_version, run),
        check_tool("screen", which),
        check_tool("restic", which) if restic else _skip("restic", "[restic]"),
        check_file("MCA Selector jar", mca.jar if mca else None, "[mca]"),
        check_file(
            "packwiz bootstrap jar",
            packwiz.bootstrap_jar if packwiz else None,
            "[packwiz]",
        ),
        check_private(
            "restic password file", restic.password_file if restic else None, "[restic]"
        ),
        *check_server(settings.server.dir),
    ]


def check_java(path: Path, min_version: int, run: Run) -> Check:
    try:
        output = run([str(path), "--version"])
    except (OSError, subprocess.SubprocessError) as e:
        return Check("java", Status.FAIL, str(e))
    first_line = output.partition("\n")[0]
    match = _JAVA_VERSION.match(first_line)
    if match is None:
        return Check("java", Status.FAIL, f"can't read a version from {first_line!r}")
    version = int(match[1])
    if version < min_version:
        return Check(
            "java", Status.FAIL, f"{path} is Java {version}, need {min_version}+"
        )
    return Check("java", Status.OK, f"{path} (Java {version})")


def check_tool(name: str, which: Which) -> Check:
    found = which(name)
    if found is None:
        return Check(name, Status.FAIL, "not found on PATH")
    return Check(name, Status.OK, found)


def check_file(name: str, path: Path | None, section: str) -> Check:
    if path is None:
        return _skip(name, section)
    if not path.is_file():
        return Check(name, Status.FAIL, f"{path} not found")
    return Check(name, Status.OK, str(path))


def check_private(name: str, path: Path | None, section: str) -> Check:
    """The file exists and only its owner can read or write it."""
    if path is None:
        return _skip(name, section)
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError as e:
        return Check(name, Status.FAIL, f"{path}: {e.strerror}")
    if mode & 0o077:
        return Check(name, Status.FAIL, f"{path} is {mode:o}; run chmod 600")
    return Check(name, Status.OK, f"{path} is {mode:o}")


def check_server(server_dir: Path) -> list[Check]:
    path = server_dir / "server.properties"
    try:
        props = load_properties(path)
    except OSError as e:
        return [Check("server.properties", Status.FAIL, f"{path}: {e.strerror}")]

    port = props.get("management-server-port", "0")
    return [
        check_private("server.properties", path, ""),
        _expect(props, "management-server-enabled", "true"),
        Check("management-server-port", Status.OK, port)
        if port.isdigit() and port != "0"
        else Check(
            "management-server-port",
            Status.FAIL,
            f"{port!r}; set a fixed port (0 picks a random one each start)",
        ),
        _expect(props, "management-server-tls-enabled", "false"),
        _expect(props, "enable-rcon", "true"),
        Check("rcon.password", Status.OK, "set")
        if props.get("rcon.password")
        else Check("rcon.password", Status.FAIL, "empty"),
    ]


def _expect(props: dict[str, str], key: str, expected: str) -> Check:
    actual = props.get(key)
    if actual == expected:
        return Check(key, Status.OK, actual)
    return Check(key, Status.FAIL, f"is {actual!r}, needs {expected!r}")


def _skip(name: str, section: str) -> Check:
    return Check(name, Status.SKIP, f"{section} not configured")
