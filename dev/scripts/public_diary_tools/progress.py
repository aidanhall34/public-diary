from __future__ import annotations

import contextlib
import contextvars
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from typing import TextIO

_CURRENT_PROGRESS: contextvars.ContextVar[WebRequestProgress | None] = contextvars.ContextVar(
    "_CURRENT_PROGRESS",
    default=None,
)


@dataclass
class WebRequestProgress:
    output: TextIO = sys.stderr
    completed: int = 0
    initiated: int = 0
    total: int = 0
    _rendered: bool = False
    _line_open: bool = False

    def add_total(self, count: int) -> None:
        if count <= 0:
            return
        self.total += count
        self._render()

    @contextlib.contextmanager
    def request(self, *, planned: bool = True) -> Iterator[None]:
        if planned:
            self.add_total(1)
        self.initiated += 1
        self._render()
        try:
            yield
        finally:
            self.completed += 1
            self._render()

    def finish(self) -> None:
        if self._line_open:
            self.output.write("\n")
            self.output.flush()
            self._line_open = False

    def start_output_line(self) -> None:
        self.finish()

    def _render(self) -> None:
        if self.total:
            percent = int((self.completed / self.total) * 100)
            summary = f"{self.completed}/{self.initiated}/{self.total} ({percent}%)"
        else:
            summary = f"{self.completed}/{self.initiated}/?"
        if not self._rendered:
            self.output.write("\n\n")
        self.output.write(f"\rWeb requests completed/initiated/total: {summary}")
        self.output.flush()
        self._rendered = True
        self._line_open = True


class ProgressAwareOutput:
    def __init__(self, output: TextIO, progress: WebRequestProgress) -> None:
        self._output = output
        self._progress = progress

    def write(self, value: str) -> int:
        if value:
            self._progress.start_output_line()
        return self._output.write(value)

    def flush(self) -> None:
        self._output.flush()

    def isatty(self) -> bool:
        return self._output.isatty()

    def __getattr__(self, name: str) -> object:
        return getattr(self._output, name)


def current_progress() -> WebRequestProgress | None:
    return _CURRENT_PROGRESS.get()


def add_web_requests(count: int) -> None:
    progress = current_progress()
    if progress:
        progress.add_total(count)


@contextlib.contextmanager
def track_web_request(*, planned: bool = True) -> Iterator[None]:
    progress = current_progress()
    if not progress:
        yield
        return
    with progress.request(planned=planned):
        yield


@contextlib.contextmanager
def web_request_progress(output: TextIO | None = None) -> Iterator[WebRequestProgress]:
    output = output or sys.stderr
    progress = WebRequestProgress(output=output)
    token = _CURRENT_PROGRESS.set(progress)
    try:
        with (
            contextlib.redirect_stdout(ProgressAwareOutput(sys.stdout, progress)),
            contextlib.redirect_stderr(ProgressAwareOutput(sys.stderr, progress)),
        ):
            yield progress
    finally:
        progress.finish()
        _CURRENT_PROGRESS.reset(token)
