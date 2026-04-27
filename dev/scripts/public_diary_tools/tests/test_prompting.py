import pytest
from public_diary_tools.prompting import prompt_required_value, prompt_value, prompt_yes_no, select_option


def test_prompt_value_uses_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    assert prompt_value("NAME", "default", input_fn=lambda _: "") == "default"


def test_prompt_value_accepts_input(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    assert prompt_value("NAME", "default", input_fn=lambda _: "custom") == "custom"


def test_prompt_required_value_retries_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    answers = iter(["", "custom"])
    messages: list[str] = []

    assert prompt_required_value("NAME", input_fn=lambda _: next(answers), output_fn=messages.append) == "custom"
    assert "NAME must be a non-empty value. Please try again." in messages


def test_prompt_yes_no_retries_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    answers = iter(["", "x", "y"])
    messages: list[str] = []

    assert prompt_yes_no("Use these defaults?", input_fn=lambda _: next(answers), output_fn=messages.append)
    assert "Invalid Use these defaults? selection: <empty>. Enter y or n." in messages
    assert "Invalid Use these defaults? selection: x. Enter y or n." in messages


def test_select_option_single(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    messages: list[str] = []
    answers = iter(["", "1"])
    assert select_option("thing", [("id", "Name")], input_fn=lambda _: next(answers), output_fn=messages.append) == "id"
    assert messages == [
        "Select thing:",
        "Press Ctrl+C at any prompt to exit without making changes.",
        "  1) Name (id)",
        "Invalid thing selection: <empty>. Please try again.",
    ]


def test_select_option_multiple_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    answers = iter(["", "1"])
    assert select_option("thing", [("a", "A"), ("b", "B")], input_fn=lambda _: next(answers)) == "a"


def test_select_option_blank_is_valid_when_offered(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    assert select_option("thing", [("", "None"), ("b", "B")], input_fn=lambda _: "") == ""


def test_select_option_null_is_valid_when_blank_offered(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    assert select_option("thing", [("", "None"), ("b", "B")], input_fn=lambda _: "null") == ""


def test_select_option_accepts_option_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    assert select_option("thing", [(".", "Current"), ("..", "Parent")], input_fn=lambda _: "..") == ".."


def test_select_option_does_not_duplicate_control_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    messages: list[str] = []
    selected = select_option(
        "thing",
        [(".", "Select current folder: . (obs-notes)")],
        input_fn=lambda _: "1",
        output_fn=messages.append,
    )
    assert selected == "."
    assert "  1) Select current folder: . (obs-notes)" in messages


def test_select_option_retries_invalid_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    answers = iter(["x", "2"])
    messages: list[str] = []

    selected = select_option(
        "thing",
        [("a", "A"), ("b", "B")],
        input_fn=lambda _: next(answers),
        output_fn=messages.append,
    )
    assert selected == "b"

    assert "Invalid thing selection: x. Please try again." in messages


def test_select_option_retries_out_of_range_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    answers = iter(["3", "1"])
    assert select_option("thing", [("a", "A"), ("b", "B")], input_fn=lambda _: next(answers)) == "a"


def test_select_option_no_options() -> None:
    assert select_option("thing", []) == ""
