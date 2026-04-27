from pathlib import Path

from public_diary_tools.envfiles import clean_existing, is_dummy, read_env_file, write_env_file


def test_read_write_env_file_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "vars.env"
    write_env_file(path, {"A": "one", "B": "", "C": "three"})

    assert read_env_file(path) == {"A": "one", "B": "", "C": "three"}
    assert oct(path.stat().st_mode & 0o777) == "0o600"


def test_read_env_file_ignores_comments_and_invalid_lines(tmp_path: Path) -> None:
    path = tmp_path / "vars.env"
    path.write_text("\n# ignored\nNOPE\nA=1\nB=two=three\n")

    assert read_env_file(path) == {"A": "1", "B": "two=three"}


def test_clean_existing_removes_dummy_values() -> None:
    assert is_dummy("dummy@example.iam.gserviceaccount.com")
    assert clean_existing({"A": "dummy", "B": "real"}) == {"B": "real"}
