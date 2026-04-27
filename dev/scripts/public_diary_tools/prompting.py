from __future__ import annotations

import os
import sys
from collections.abc import Callable, Sequence

try:
    import readline
except ImportError:  # pragma: no cover - platform dependent.
    readline = None  # type: ignore[assignment]

InputFn = Callable[[str], str]
OutputFn = Callable[[str], None]

BOLD = "\033[1m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RESET = "\033[0m"


if readline is not None:  # pragma: no cover - depends on interactive terminal support.
    readline.parse_and_bind("set editing-mode emacs")


def color(value: str, code: str) -> str:
    if os.environ.get("NO_COLOR") or os.environ.get("MAKELEVEL") or not sys.stdout.isatty():
        return value
    return f"{code}{value}{RESET}"


def info(message: str, output_fn: OutputFn = print) -> None:
    output_fn(color(message, CYAN))


def success(message: str, output_fn: OutputFn = print) -> None:
    output_fn(color(message, GREEN))


def bail_note(output_fn: OutputFn = print) -> None:
    output_fn(color("Press Ctrl+C at any prompt to exit without making changes.", YELLOW))


def prompt_value(name: str, default: str = "", input_fn: InputFn = input) -> str:
    if default:
        value = input_fn(f"{color(name, BOLD)} [{default}]: ")
        return value or default
    return input_fn(f"{color(name, BOLD)}: ")


def prompt_required_value(name: str, input_fn: InputFn = input, output_fn: OutputFn = print) -> str:
    while True:
        value = prompt_value(name, input_fn=input_fn)
        if value:
            return value
        output_fn(color(f"{name} must be a non-empty value. Please try again.", YELLOW))


def prompt_yes_no(label: str, input_fn: InputFn = input, output_fn: OutputFn = print) -> bool:
    while True:
        selection = input_fn(f"{color(label, BOLD)} [y/n]: ")
        if selection == "y":
            return True
        if selection == "n":
            return False
        output_fn(color(f"Invalid {label} selection: {selection or '<empty>'}. Enter y or n.", YELLOW))


def _render_option(index: int, value: str, name: str) -> str:
    if not value or value in {".", ".."} or name.endswith(f"({value})"):
        return f"  {color(str(index), BOLD)}) {name}"
    return f"  {color(str(index), BOLD)}) {name} ({value})"


def select_option(
    label: str,
    options: Sequence[tuple[str, str]],
    input_fn: InputFn = input,
    output_fn: OutputFn = print,
) -> str:
    if not options:
        return ""

    info(f"Select {label}:", output_fn=output_fn)
    bail_note(output_fn=output_fn)
    for index, (value, name) in enumerate(options, start=1):
        output_fn(_render_option(index, value, name))

    option_values = {value for value, _ in options}
    null_values = {"", "null", "none"}
    while True:
        selection = input_fn(f"{color(label, BOLD)}: ")
        if selection.lower() in null_values and "" in option_values:
            return ""
        if not selection:
            output_fn(color(f"Invalid {label} selection: <empty>. Please try again.", YELLOW))
            continue
        if selection in option_values:
            return selection
        if selection.isdigit():
            selected_index = int(selection)
            if 1 <= selected_index <= len(options):
                return options[selected_index - 1][0]
        output_fn(color(f"Invalid {label} selection: {selection}. Please try again.", YELLOW))


def prompt_setting(
    name: str,
    current: str = "",
    suggestions: Sequence[tuple[str, str]] = (),
    input_fn: InputFn = input,
    output_fn: OutputFn = print,
    required: bool = False,
    custom_label: str = "Custom value",
) -> str:
    if current:
        success(f"Using {name}: {current}", output_fn=output_fn)
        return current

    value = ""
    if suggestions:
        selected = select_option(
            name,
            [*suggestions, ("__custom__", custom_label)],
            input_fn=input_fn,
            output_fn=output_fn,
        )
        if selected != "__custom__":
            if required and not selected:
                raise RuntimeError(f"{name} is required.")
            return selected
    else:
        info(f"No suggestions found for {name}.", output_fn=output_fn)
        bail_note(output_fn=output_fn)

    if not value:
        value = prompt_required_value(name, input_fn=input_fn, output_fn=output_fn)
    if required and not value:
        raise RuntimeError(f"{name} is required.")
    return value
