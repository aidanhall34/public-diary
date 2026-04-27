from __future__ import annotations

import json
from pathlib import Path

import pytest
from public_diary_tools.coverage_badge import (
    badge_color,
    coverage_percent,
    publish_coverage_badge,
    render_coverage_badge,
    update_readme_badge,
)


def test_coverage_percent_reads_totals(tmp_path: Path) -> None:
    coverage = tmp_path / "coverage.json"
    coverage.write_text(json.dumps({"totals": {"percent_covered": 96.731}}))

    assert coverage_percent(coverage) == pytest.approx(96.731)


def test_coverage_percent_requires_totals(tmp_path: Path) -> None:
    coverage = tmp_path / "coverage.json"
    coverage.write_text("{}")

    with pytest.raises(ValueError, match="missing totals"):
        coverage_percent(coverage)


def test_coverage_percent_requires_numeric_value(tmp_path: Path) -> None:
    coverage = tmp_path / "coverage.json"
    coverage.write_text(json.dumps({"totals": {"percent_covered": "97"}}))

    with pytest.raises(ValueError, match="numeric"):
        coverage_percent(coverage)


def test_badge_color_thresholds() -> None:
    assert badge_color(95) == "#2ea043"
    assert badge_color(85) == "#bf8700"
    assert badge_color(84.9) == "#cf222e"


def test_render_coverage_badge_escapes_text() -> None:
    badge = render_coverage_badge(96.731)

    assert "96.7%" in badge
    assert "coverage" in badge
    assert badge.endswith("</svg>\n")


def test_update_readme_badge_inserts_after_title(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("# Project\n\nBody\n")

    assert update_readme_badge(readme)
    assert readme.read_text() == "# Project\n\n![Test coverage](docs/images/coverage.svg)\n\nBody\n"


def test_update_readme_badge_replaces_existing_badge(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("# Project\n\n![Test coverage](old.svg)\n\nBody\n")

    assert update_readme_badge(readme)
    assert readme.read_text() == "# Project\n\n![Test coverage](docs/images/coverage.svg)\n\nBody\n"


def test_publish_coverage_badge_updates_badges_and_readmes(tmp_path: Path) -> None:
    coverage = tmp_path / "coverage.json"
    readme = tmp_path / "README.md"
    docs_readme = tmp_path / "docs" / "README.md"
    badge = tmp_path / "docs/images/coverage.svg"
    docs_badge = tmp_path / "docs" / "docs/images/coverage.svg"
    coverage.write_text(json.dumps({"totals": {"percent_covered": 96.731}}))
    readme.write_text("# Project\n\nBody\n")
    docs_readme.parent.mkdir()
    docs_readme.write_text("# Project\n\nBody\n")

    percent, changed = publish_coverage_badge(
        coverage_path=coverage,
        readme_paths=(readme, docs_readme),
        badge_paths=(badge, docs_badge),
    )

    assert percent == pytest.approx(96.731)
    assert changed == [badge, docs_badge, readme, docs_readme]
    assert "96.7%" in badge.read_text()
    assert "![Test coverage](docs/images/coverage.svg)" in docs_readme.read_text()
