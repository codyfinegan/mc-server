import os
from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import ValidationError

from mctl.config import ConfigError, Settings, find_config, load


def test_minimal_config_gets_defaults(
    write_config: Callable[[str], Path], minimal_toml: str
) -> None:
    settings = load(write_config(minimal_toml))

    assert settings.server.dir == Path("/srv/minecraft")
    assert settings.server.screen_session == "mcs"
    assert settings.java.path == Path("/usr/bin/java")
    assert settings.java.min_version == 25
    assert settings.mca is None
    assert settings.packwiz is None
    assert settings.restic is None


@pytest.mark.parametrize(
    ("toml", "expected"),
    [
        pytest.param(
            '[server]\ndir = "/a"\nstart_command = "x"\ndirr = "/b"',
            ["server.dirr: Extra inputs are not permitted"],
            id="unknown-key",
        ),
        pytest.param(
            '[server]\nstart_command = "x"',
            ["server.dir: Field required"],
            id="missing-field",
        ),
        pytest.param("", ["server: Field required"], id="missing-section"),
        pytest.param(
            '[server]\ndir = "/a"\nstart_command = "x"\n[java]\nmin_version = "x"',
            [
                "java.min_version: Input should be a valid integer, "
                "unable to parse string as an integer"
            ],
            id="wrong-type",
        ),
    ],
)
def test_validation_errors(
    write_config: Callable[[str], Path], toml: str, expected: list[str]
) -> None:
    path = write_config(toml)

    with pytest.raises(ConfigError) as exc:
        load(path)

    assert exc.value.path == path
    assert exc.value.messages == expected


def test_find_config_uses_given_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    assert find_config(Path("~/custom.toml")) == tmp_path / "custom.toml"


def test_find_config_defaults_to_home_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    assert find_config() == tmp_path / ".config/mctl/config.toml"


def test_optional_sections_load(
    write_config: Callable[[str], Path], minimal_toml: str
) -> None:
    settings = load(
        write_config(
            minimal_toml
            + """
[mca]
jar = "/opt/mca/mcaselector.jar"
jvm_args = ["-Xmx2G"]

[packwiz]
bootstrap_jar = "/opt/packwiz/bootstrap.jar"
pack_url = "https://example.com/pack.toml"

[restic]
repository = "s3:s3.amazonaws.com/bucket/mc"
password_file = "/etc/mctl/restic-password"
"""
        )
    )

    assert settings.mca is not None
    assert settings.mca.jar == Path("/opt/mca/mcaselector.jar")
    assert settings.mca.jvm_args == ["-Xmx2G"]
    assert settings.packwiz is not None
    assert settings.packwiz.pack_url == "https://example.com/pack.toml"
    assert settings.restic is not None
    assert settings.restic.password_file == Path("/etc/mctl/restic-password")


def test_relative_paths_resolve_against_config_dir(
    write_config: Callable[[str], Path], tmp_path: Path
) -> None:
    settings = load(
        write_config(
            """
[server]
dir = "../server"
start_command = "./run.sh"

[mca]
jar = "mca/mcaselector.jar"
"""
        )
    )

    assert settings.server.dir == tmp_path.parent / "server"
    assert settings.mca is not None
    assert settings.mca.jar == tmp_path / "mca/mcaselector.jar"


def test_tilde_paths_expand(
    write_config: Callable[[str], Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    settings = load(write_config('[server]\ndir = "~/server"\nstart_command = "x"'))

    assert settings.server.dir == tmp_path / "home/server"


def test_relative_config_path_still_gives_absolute_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub/config.toml").write_text(
        '[server]\ndir = "server"\nstart_command = "x"'
    )
    monkeypatch.chdir(tmp_path)

    settings = load(Path("sub/config.toml"))

    assert settings.server.dir == tmp_path / "sub/server"


def test_list_position_in_error_location(
    write_config: Callable[[str], Path], minimal_toml: str
) -> None:
    path = write_config(
        minimal_toml + '[mca]\njar = "/x.jar"\njvm_args = ["-Xmx2G", 3]'
    )

    with pytest.raises(ConfigError) as exc:
        load(path)

    assert exc.value.messages == ["mca.jvm_args.1: Input should be a valid string"]


def test_all_validation_errors_reported(write_config: Callable[[str], Path]) -> None:
    path = write_config('[server]\nstart_command = "x"\nport = 1')

    with pytest.raises(ConfigError) as exc:
        load(path)

    assert exc.value.messages == [
        "server.dir: Field required",
        "server.port: Extra inputs are not permitted",
    ]


def test_unknown_section_rejected(
    write_config: Callable[[str], Path], minimal_toml: str
) -> None:
    path = write_config(minimal_toml + "[backups]\nkeep = 5")

    with pytest.raises(ConfigError) as exc:
        load(path)

    assert exc.value.messages == ["backups: Extra inputs are not permitted"]


def test_bad_toml(write_config: Callable[[str], Path]) -> None:
    path = write_config("[server\n")

    with pytest.raises(ConfigError) as exc:
        load(path)

    assert exc.value.messages == [
        "Expected ']' at the end of a table declaration (at line 1, column 8)"
    ]


def test_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "missing.toml"

    with pytest.raises(ConfigError) as exc:
        load(path)

    assert exc.value.path == path
    assert exc.value.messages == ["No such file or directory"]


@pytest.mark.skipif(os.geteuid() == 0, reason="root can read any file")
def test_unreadable_file(
    write_config: Callable[[str], Path], minimal_toml: str
) -> None:
    path = write_config(minimal_toml)
    path.chmod(0)

    with pytest.raises(ConfigError) as exc:
        load(path)

    assert exc.value.messages == ["Permission denied"]


def test_relative_path_needs_base_dir_context() -> None:
    with pytest.raises(ValidationError, match="relative path needs base_dir"):
        Settings.model_validate({"server": {"dir": "server", "start_command": "x"}})


def test_settings_are_frozen(
    write_config: Callable[[str], Path], minimal_toml: str
) -> None:
    settings = load(write_config(minimal_toml))

    with pytest.raises(ValidationError, match="frozen"):
        settings.server.dir = Path("/elsewhere")  # type: ignore[misc]


def test_config_error_message() -> None:
    error = ConfigError(Path("/etc/mctl/config.toml"), ["first", "second"])

    assert str(error) == "/etc/mctl/config.toml: first; second"
