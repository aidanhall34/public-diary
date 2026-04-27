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
        if self._rendered:
            self.output.write("\n")
            self.output.flush()

    def _render(self) -> None:
        if self.total:
            percent = int((self.completed / self.total) * 100)
            summary = f"{self.completed}/{self.initiated}/{self.total} ({percent}%)"
        else:
            summary = f"{self.completed}/{self.initiated}/?"
        self.output.write(f"\rWeb requests completed/initiated/total: {summary}")
        self.output.flush()
        self._rendered = True


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
def web_request_progress(output: TextIO = sys.stderr) -> Iterator[WebRequestProgress]:
    progress = WebRequestProgress(output=output)
    token = _CURRENT_PROGRESS.set(progress)
    try:
        yield progress
    finally:
        progress.finish()
        _CURRENT_PROGRESS.reset(token)
