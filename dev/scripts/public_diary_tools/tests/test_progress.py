from __future__ import annotations

from io import StringIO

import pytest
from public_diary_tools.progress import add_web_requests, track_web_request, web_request_progress


def test_web_request_progress_tracks_dynamic_totals() -> None:
    output = StringIO()

    with web_request_progress(output):
        add_web_requests(10)
        for _ in range(5):
            with track_web_request(planned=False):
                pass
        add_web_requests(10)

    assert "Web requests completed/initiated/total: 5/5/20 (25%)" in output.getvalue()
    assert output.getvalue().startswith("\n\n")
    assert output.getvalue().endswith("\n")


def test_web_request_progress_terminates_before_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    progress_output = StringIO()

    with web_request_progress(progress_output):
        with track_web_request():
            pass
        print("done")

    assert progress_output.getvalue().endswith("\n")
    assert capsys.readouterr().out == "done\n"


def test_track_web_request_without_active_progress_is_noop() -> None:
    with track_web_request():
        pass
