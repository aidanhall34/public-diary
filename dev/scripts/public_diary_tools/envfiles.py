from __future__ import annotations

from pathlib import Path

DUMMY_VALUES = {"dummy", "dummy@example.com", "dummy@example.iam.gserviceaccount.com"}


def is_dummy(value: str) -> bool:
    return value in DUMMY_VALUES or value.startswith("dummy")


def read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        values[name] = value
    return values


def write_env_file(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "".join(f"{name}={value}\n" for name, value in values.items())
    path.write_text(content)
    path.chmod(0o600)


def clean_existing(values: dict[str, str]) -> dict[str, str]:
    return {key: value for key, value in values.items() if value and not is_dummy(value)}

