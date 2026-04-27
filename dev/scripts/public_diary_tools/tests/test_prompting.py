import pytest
from public_diary_tools.prompting import prompt_value, select_option


def test_prompt_value_uses_default() -> None:
    assert prompt_value("NAME", "default", input_fn=lambda _: "") == "default"


def test_prompt_value_accepts_input() -> None:
    assert prompt_value("NAME", "default", input_fn=lambda _: "custom") == "custom"


def test_select_option_single() -> None:
    messages: list[str] = []
    assert select_option("thing", [("id", "Name")], output_fn=messages.append) == "id"
    assert messages == ["Using thing: Name (id)"]


def test_select_option_multiple_default() -> None:
    assert select_option("thing", [("a", "A"), ("b", "B")], input_fn=lambda _: "") == "a"


def test_select_option_rejects_invalid_selection() -> None:
    with pytest.raises(ValueError, match="Invalid thing selection"):
        select_option("thing", [("a", "A"), ("b", "B")], input_fn=lambda _: "x")


def test_select_option_rejects_out_of_range_selection() -> None:
    with pytest.raises(ValueError, match="Invalid thing selection"):
        select_option("thing", [("a", "A"), ("b", "B")], input_fn=lambda _: "3")


def test_select_option_no_options() -> None:
    assert select_option("thing", []) == ""
