from __future__ import annotations

import json
from pathlib import Path

JSON_CONFIG_GLOBS = (
    ".markdownlint.json",
    ".github/config/*.json",
    "package.json",
    "config/*.json",
)


def managed_json_files(root: Path = Path("."), globs: tuple[str, ...] = JSON_CONFIG_GLOBS) -> list[Path]:
    paths = {path for pattern in globs for path in root.glob(pattern) if path.is_file()}
    return sorted(paths)


def format_json_file(path: Path) -> bool:
    original = path.read_text()
    formatted = _formatted_json(original)
    if original == formatted:
        return False
    path.write_text(formatted)
    return True


def format_json_configs(paths: list[Path] | None = None) -> list[Path]:
    changed = []
    for path in paths or managed_json_files():
        if format_json_file(path):
            changed.append(path)
    return changed


def check_json_configs(paths: list[Path] | None = None) -> list[Path]:
    unformatted = []
    for path in paths or managed_json_files():
        original = path.read_text()
        if original != _formatted_json(original):
            unformatted.append(path)
    return unformatted


def _formatted_json(value: str) -> str:
    return f"{json.dumps(json.loads(value), indent=2)}\n"
