"""Read Java ``.properties`` files such as ``server.properties``"""

import re
from pathlib import Path

_ESCAPE = re.compile(r"\\(u[0-9a-fA-F]{4}|.)")
_SPECIAL = {"t": "\t", "n": "\n", "r": "\r", "f": "\f"}


def load_properties(path: Path) -> dict[str, str]:
    """Read ``path`` and return its keys and values, unescaped."""
    return parse_properties(path.read_text(encoding="utf-8"))


def parse_properties(text: str) -> dict[str, str]:
    """Parse properties text. Line continuations aren't supported."""
    properties = {}
    for raw in text.splitlines():
        line = raw.lstrip()
        if not line or line[0] in "#!":
            continue
        key, value = _split(line)
        properties[_unescape(key)] = _unescape(value)
    return properties


def _split(line: str) -> tuple[str, str]:
    """Split on the first ``=`` or ``:`` that isn't escaped."""
    i = 0
    while i < len(line):
        if line[i] == "\\":
            i += 2
        elif line[i] in "=:":
            return line[:i].rstrip(), line[i + 1 :].lstrip()
        else:
            i += 1
    return line.rstrip(), ""


def _unescape(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        escaped = match[1]
        if len(escaped) == 5:
            return chr(int(escaped[1:], 16))
        return _SPECIAL.get(escaped, escaped)

    return _ESCAPE.sub(replace, text)
