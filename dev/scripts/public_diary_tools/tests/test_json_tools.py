from __future__ import annotations

from pathlib import Path

from public_diary_tools.json_tools import check_json_configs, format_json_configs, format_json_file, managed_json_files


def test_format_json_file_normalizes_json(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text('{"b": 1,"a": [true,false]}\n')

    assert format_json_file(path)

    assert path.read_text() == '{\n  "b": 1,\n  "a": [\n    true,\n    false\n  ]\n}\n'


def test_format_json_configs_returns_changed_paths(tmp_path: Path) -> None:
    changed = tmp_path / "changed.json"
    unchanged = tmp_path / "unchanged.json"
    changed.write_text('{"a":1}\n')
    unchanged.write_text('{\n  "a": 1\n}\n')

    assert format_json_configs([changed, unchanged]) == [changed]


def test_check_json_configs_returns_unformatted_paths(tmp_path: Path) -> None:
    changed = tmp_path / "changed.json"
    unchanged = tmp_path / "unchanged.json"
    changed.write_text('{"a":1}\n')
    unchanged.write_text('{\n  "a": 1\n}\n')

    assert check_json_configs([changed, unchanged]) == [changed]


def test_managed_json_files_uses_restricted_globs(tmp_path: Path) -> None:
    (tmp_path / ".markdownlint.json").write_text("{}\n")
    (tmp_path / "package.json").write_text("{}\n")
    (tmp_path / "package-lock.json").write_text("{}\n")
    (tmp_path / ".github/config").mkdir(parents=True)
    (tmp_path / ".github/config/repository-permissions.json").write_text("{}\n")
    (tmp_path / "config").mkdir()
    (tmp_path / "config/quartz-site.json").write_text("{}\n")
    (tmp_path / "dev").mkdir()
    (tmp_path / "dev/generated.json").write_text("{}\n")

    assert managed_json_files(tmp_path) == [
        tmp_path / ".github/config/repository-permissions.json",
        tmp_path / ".markdownlint.json",
        tmp_path / "config/quartz-site.json",
        tmp_path / "package.json",
    ]
