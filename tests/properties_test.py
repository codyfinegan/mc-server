from pathlib import Path

import pytest

from mctl.properties import load_properties, parse_properties


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("motd=Hello", {"motd": "Hello"}, id="plain"),
        pytest.param("key: value", {"key": "value"}, id="colon-separator"),
        pytest.param("  key  =  value", {"key": "value"}, id="whitespace-trimmed"),
        pytest.param("empty=", {"empty": ""}, id="empty-value"),
        pytest.param("bare", {"bare": ""}, id="no-separator"),
        pytest.param("a=b=c", {"a": "b=c"}, id="separator-in-value"),
        pytest.param(r"a\=b = c:d", {"a=b": "c:d"}, id="escaped-separator-in-key"),
        pytest.param(
            r"bug-report-link=https\://discord.com/x",
            {"bug-report-link": "https://discord.com/x"},
            id="escaped-colon",
        ),
        pytest.param(
            r"level-type=minecraft\:normal",
            {"level-type": "minecraft:normal"},
            id="escaped-colon-in-id",
        ),
        pytest.param(r"prompt=pack\!", {"prompt": "pack!"}, id="escaped-bang"),
        pytest.param(r"k=caf\u00e9", {"k": "café"}, id="unicode-escape"),
        pytest.param(r"k=a\tb\nc", {"k": "a\tb\nc"}, id="special-escapes"),
        pytest.param(r"k=a\\b", {"k": "a\\b"}, id="escaped-backslash"),
    ],
)
def test_parse_line(text: str, expected: dict[str, str]) -> None:
    assert parse_properties(text) == expected


def test_parse_skips_comments_and_blank_lines() -> None:
    text = "#Minecraft server properties\n\n   \n! also a comment\n  # indented\nk=v\n"

    assert parse_properties(text) == {"k": "v"}


def test_parse_later_key_wins() -> None:
    assert parse_properties("k=1\nk=2") == {"k": "2"}


def test_load_properties_reads_utf8(tmp_path: Path) -> None:
    path = tmp_path / "server.properties"
    path.write_text("motd=Café Minecraft\nenable-rcon=true\n", encoding="utf-8")

    assert load_properties(path) == {
        "motd": "Café Minecraft",
        "enable-rcon": "true",
    }
