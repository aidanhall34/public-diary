from __future__ import annotations

from collections.abc import Callable, Sequence

InputFn = Callable[[str], str]
OutputFn = Callable[[str], None]


def prompt_value(name: str, default: str = "", input_fn: InputFn = input) -> str:
    if default:
        value = input_fn(f"{name} [{default}]: ")
        return value or default
    return input_fn(f"{name}: ")


def select_option(
    label: str,
    options: Sequence[tuple[str, str]],
    input_fn: InputFn = input,
    output_fn: OutputFn = print,
) -> str:
    if not options:
        return ""
    if len(options) == 1:
        value, name = options[0]
        output_fn(f"Using {label}: {name} ({value})")
        return value

    output_fn(f"Select {label}:")
    for index, (value, name) in enumerate(options, start=1):
        output_fn(f"  {index}) {name} ({value})")

    selection = input_fn(f"{label} [1]: ") or "1"
    if not selection.isdigit():
        raise ValueError(f"Invalid {label} selection: {selection}")

    selected_index = int(selection)
    if selected_index < 1 or selected_index > len(options):
        raise ValueError(f"Invalid {label} selection: {selection}")
    return options[selected_index - 1][0]

