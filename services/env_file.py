"""Read settings from a local ``.env`` file without extra packages.

Values go into the process environment only. They are never printed, logged or returned:
the functions here only ever report the NAMES of the settings they found.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import MutableMapping

DEFAULT_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _parse_line(line: str) -> tuple[str, str] | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if line.startswith("export "):
        line = line[len("export "):].lstrip()
    name, separator, value = line.partition("=")
    name, value = name.strip(), value.strip()
    if not separator or not _NAME_RE.match(name):
        return None
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return (name, value) if value else None  # an empty value is a placeholder, not a setting


def load_env_file(path: Path | str | None = None, environ: MutableMapping | None = None) -> list[str]:
    """Copy settings from the file into ``environ`` and return the NAMES found in it.

    A variable that is already set (for example in the terminal) is never overwritten.
    A missing or unreadable file is not an error: the function just returns an empty list.
    """
    path = DEFAULT_ENV_PATH if path is None else path
    environ = os.environ if environ is None else environ
    try:
        lines = Path(path).read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeDecodeError):
        return []
    found: list[str] = []
    for line in lines:
        parsed = _parse_line(line)
        if parsed is None:
            continue
        name, value = parsed
        found.append(name)
        environ.setdefault(name, value)
    return found
