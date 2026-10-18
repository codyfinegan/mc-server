import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from mctl.config import Settings
from mctl.doctor import (
    Check,
    Status,
    check_file,
    check_java,
    check_private,
    check_server,
    check_tool,
    run_checks,
    run_command,
)

GOOD_PROPERTIES = """\
#Minecraft server properties
enable-rcon=true
rcon.password=secret
management-server-enabled=true
management-server-port=25585
management-server-tls-enabled=false
"""

OPENJDK = (
    "openjdk 25.0.4.1 2026-08-18\n"
    "OpenJDK Runtime Environment (build 25.0.4.1+1-1-deb13u1-Debian)\n"
)
TEMURIN = "openjdk 25.0.4.1 2026-07-15 LTS\nOpenJDK Runtime Environment Temurin\n"


def returns(output: str) -> Callable[[Sequence[str]], str]:
    """A fake ``run`` that always prints ``output``."""

    def run(args: Sequence[str]) -> str:
        return output

    return run


def raises(error: Exception) -> Callable[[Sequence[str]], str]:
    """A fake ``run`` that always raises ``error``."""

    def run(args: Sequence[str]) -> str:
        raise error

    return run


def which_finds(*names: str) -> Callable[[str], str | None]:
    """A fake ``shutil.which`` that only finds ``names``, in /usr/bin."""

    def which(name: str) -> str | None:
        return f"/usr/bin/{name}" if name in names else None

    return which


@pytest.fixture
def server_dir(tmp_path: Path) -> Path:
    """A server folder with a correct, private server.properties."""
    path = tmp_path / "server"
    path.mkdir()
    (path / "server.properties").write_text(GOOD_PROPERTIES)
    (path / "server.properties").chmod(0o600)
    return path


# --- run_command ---------------------------------------------------------


def test_run_command_returns_stdout() -> None:
    assert run_command(["echo", "hello"]) == "hello\n"


def test_run_command_raises_on_failure() -> None:
    with pytest.raises(subprocess.CalledProcessError):
        run_command(["false"])


# --- check_java ----------------------------------------------------------


@pytest.mark.parametrize("output", [OPENJDK, TEMURIN, "java 25 2025-09-16 LTS\n"])
def test_java_ok(output: str) -> None:
    check = check_java(Path("/usr/bin/java"), 25, returns(output))

    assert check == Check("java", Status.OK, "/usr/bin/java (Java 25)")


def test_java_passes_version_flag() -> None:
    seen: list[Sequence[str]] = []

    def run(args: Sequence[str]) -> str:
        seen.append(args)
        return OPENJDK

    check_java(Path("/opt/java/bin/java"), 25, run)

    assert seen == [["/opt/java/bin/java", "--version"]]


def test_java_too_old() -> None:
    check = check_java(Path("/usr/bin/java"), 25, returns("openjdk 21.0.5 2024\n"))

    assert check == Check("java", Status.FAIL, "/usr/bin/java is Java 21, need 25+")


def test_java_unreadable_version() -> None:
    check = check_java(Path("/usr/bin/java"), 25, returns("garbage\n"))

    assert check == Check("java", Status.FAIL, "can't read a version from 'garbage'")


@pytest.mark.parametrize(
    "error",
    [
        FileNotFoundError(2, "No such file or directory"),
        PermissionError(13, "Permission denied"),
        subprocess.CalledProcessError(1, ["java", "--version"]),
        subprocess.TimeoutExpired(["java", "--version"], 10),
    ],
    ids=["missing", "not-executable", "exit-code", "timeout"],
)
def test_java_cannot_run(error: Exception) -> None:
    check = check_java(Path("/usr/bin/java"), 25, raises(error))

    assert check == Check("java", Status.FAIL, str(error))


# --- check_tool ----------------------------------------------------------


def test_tool_found() -> None:
    assert check_tool("screen", which_finds("screen")) == Check(
        "screen", Status.OK, "/usr/bin/screen"
    )


def test_tool_missing() -> None:
    assert check_tool("restic", which_finds()) == Check(
        "restic", Status.FAIL, "not found on PATH"
    )


# --- check_file ----------------------------------------------------------


def test_file_not_configured() -> None:
    assert check_file("jar", None, "[mca]") == Check(
        "jar", Status.SKIP, "[mca] not configured"
    )


def test_file_missing(tmp_path: Path) -> None:
    path = tmp_path / "missing.jar"

    assert check_file("jar", path, "[mca]") == Check(
        "jar", Status.FAIL, f"{path} not found"
    )


def test_file_is_a_directory(tmp_path: Path) -> None:
    assert check_file("jar", tmp_path, "[mca]").status is Status.FAIL


def test_file_present(tmp_path: Path) -> None:
    path = tmp_path / "x.jar"
    path.touch()

    assert check_file("jar", path, "[mca]") == Check("jar", Status.OK, str(path))


# --- check_private -------------------------------------------------------


def test_private_not_configured() -> None:
    assert check_private("pw", None, "[restic]") == Check(
        "pw", Status.SKIP, "[restic] not configured"
    )


def test_private_missing(tmp_path: Path) -> None:
    path = tmp_path / "missing"

    assert check_private("pw", path, "[restic]") == Check(
        "pw", Status.FAIL, f"{path}: No such file or directory"
    )


@pytest.mark.parametrize("mode", [0o644, 0o640, 0o604, 0o660])
def test_private_readable_by_others(tmp_path: Path, mode: int) -> None:
    path = tmp_path / "pw"
    path.touch()
    path.chmod(mode)

    assert check_private("pw", path, "[restic]") == Check(
        "pw", Status.FAIL, f"{path} is {mode:o}; run chmod 600"
    )


@pytest.mark.parametrize("mode", [0o600, 0o400])
def test_private_ok(tmp_path: Path, mode: int) -> None:
    path = tmp_path / "pw"
    path.touch()
    path.chmod(mode)

    assert check_private("pw", path, "[restic]") == Check(
        "pw", Status.OK, f"{path} is {mode:o}"
    )


# --- check_server --------------------------------------------------------


def test_server_all_good(server_dir: Path) -> None:
    checks = check_server(server_dir)

    assert [(c.name, c.status) for c in checks] == [
        ("server.properties", Status.OK),
        ("management-server-enabled", Status.OK),
        ("management-server-port", Status.OK),
        ("management-server-tls-enabled", Status.OK),
        ("enable-rcon", Status.OK),
        ("rcon.password", Status.OK),
    ]
    assert checks[2].detail == "25585"


def test_server_properties_missing(tmp_path: Path) -> None:
    path = tmp_path / "server.properties"

    assert check_server(tmp_path) == [
        Check("server.properties", Status.FAIL, f"{path}: No such file or directory")
    ]


def test_server_properties_readable_by_others(server_dir: Path) -> None:
    (server_dir / "server.properties").chmod(0o664)

    check = check_server(server_dir)[0]

    assert check.name == "server.properties"
    assert check.status is Status.FAIL


def _with(server_dir: Path, **changes: str) -> dict[str, Check]:
    """Rewrite server.properties with ``changes`` and run check_server."""
    path = server_dir / "server.properties"
    lines = dict(line.split("=", 1) for line in GOOD_PROPERTIES.splitlines()[1:])
    lines.update({key.replace("_", "-"): value for key, value in changes.items()})
    path.write_text("".join(f"{key}={value}\n" for key, value in lines.items()))
    return {check.name: check for check in check_server(server_dir)}


def test_server_default_test_server_settings(server_dir: Path) -> None:
    checks = _with(
        server_dir,
        management_server_enabled="false",
        management_server_port="0",
        management_server_tls_enabled="true",
    )

    assert checks["management-server-enabled"] == Check(
        "management-server-enabled", Status.FAIL, "is 'false', needs 'true'"
    )
    assert checks["management-server-port"] == Check(
        "management-server-port",
        Status.FAIL,
        "'0'; set a fixed port (0 picks a random one each start)",
    )
    assert checks["management-server-tls-enabled"] == Check(
        "management-server-tls-enabled", Status.FAIL, "is 'true', needs 'false'"
    )


@pytest.mark.parametrize("port", ["", "abc", "-1"])
def test_server_port_not_a_number(server_dir: Path, port: str) -> None:
    check = _with(server_dir, management_server_port=port)["management-server-port"]

    assert check.status is Status.FAIL


def test_server_missing_keys(server_dir: Path) -> None:
    (server_dir / "server.properties").write_text("motd=hi\n")

    checks = {check.name: check for check in check_server(server_dir)}

    assert checks["management-server-enabled"].detail == "is None, needs 'true'"
    assert checks["management-server-port"].status is Status.FAIL
    assert checks["rcon.password"] == Check("rcon.password", Status.FAIL, "empty")


def test_server_rcon_disabled(server_dir: Path) -> None:
    check = _with(server_dir, enable_rcon="false")["enable-rcon"]

    assert check == Check("enable-rcon", Status.FAIL, "is 'false', needs 'true'")


def test_server_rcon_password_empty(server_dir: Path) -> None:
    check = _with(server_dir, **{"rcon.password": ""})["rcon.password"]

    assert check == Check("rcon.password", Status.FAIL, "empty")


# --- run_checks ----------------------------------------------------------


def test_run_checks_minimal_config_skips_optional_sections(server_dir: Path) -> None:
    settings = Settings.model_validate(
        {"server": {"dir": str(server_dir), "start_command": "./run.sh"}}
    )

    checks = run_checks(settings, which_finds("screen"), returns(OPENJDK))

    assert [(c.name, c.status) for c in checks[:6]] == [
        ("java", Status.OK),
        ("screen", Status.OK),
        ("restic", Status.SKIP),
        ("MCA Selector jar", Status.SKIP),
        ("packwiz bootstrap jar", Status.SKIP),
        ("restic password file", Status.SKIP),
    ]
    assert all(c.status is Status.OK for c in checks[6:])


def test_run_checks_full_config(server_dir: Path, tmp_path: Path) -> None:
    for name in ("mca.jar", "bootstrap.jar", "restic-pw"):
        (tmp_path / name).touch(mode=0o600)
    settings = Settings.model_validate(
        {
            "server": {"dir": str(server_dir), "start_command": "./run.sh"},
            "java": {"path": "/opt/java/bin/java"},
            "mca": {"jar": str(tmp_path / "mca.jar")},
            "packwiz": {
                "bootstrap_jar": str(tmp_path / "bootstrap.jar"),
                "pack_url": "https://example.com/pack.toml",
            },
            "restic": {
                "repository": "s3:example/bucket",
                "password_file": str(tmp_path / "restic-pw"),
            },
        }
    )

    checks = run_checks(settings, which_finds("screen", "restic"), returns(OPENJDK))

    assert all(c.status is Status.OK for c in checks), checks
    assert checks[0].detail == "/opt/java/bin/java (Java 25)"
