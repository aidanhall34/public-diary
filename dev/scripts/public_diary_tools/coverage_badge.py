from __future__ import annotations

import html
import json
from pathlib import Path

COVERAGE_JSON = Path("dev/scripts/test_out/coverage.json")
README_PATHS = (Path("README.md"), Path("docs/README.md"))
BADGE_PATHS = (Path("docs/images/coverage.svg"), Path("docs/images/coverage.svg"))
BADGE_MARKER = "![Test coverage](docs/images/coverage.svg)"


def coverage_percent(path: Path = COVERAGE_JSON) -> float:
    data = json.loads(path.read_text())
    totals = data.get("totals")
    if not isinstance(totals, dict):
        raise ValueError(f"Coverage report is missing totals: {path}")
    percent = totals.get("percent_covered")
    if not isinstance(percent, int | float):
        raise ValueError(f"Coverage report is missing numeric percent_covered: {path}")
    return float(percent)


def badge_color(percent: float) -> str:
    if percent >= 95:
        return "#2ea043"
    if percent >= 85:
        return "#bf8700"
    return "#cf222e"


def render_coverage_badge(percent: float) -> str:
    label = "coverage"
    value = f"{percent:.1f}%"
    label_width = 74
    value_width = 58
    width = label_width + value_width
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="20" '
        f'role="img" aria-label="{label}: {value}">'
        f"""
  <title>{html.escape(label)}: {html.escape(value)}</title>
  <linearGradient id="s" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <clipPath id="r">
    <rect width="{width}" height="20" rx="3" fill="#fff"/>
  </clipPath>
  <g clip-path="url(#r)">
    <rect width="{label_width}" height="20" fill="#555"/>
    <rect x="{label_width}" width="{value_width}" height="20" fill="{badge_color(percent)}"/>
    <rect width="{width}" height="20" fill="url(#s)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="11">
    <text x="37" y="15" fill="#010101" fill-opacity=".3">{html.escape(label)}</text>
    <text x="37" y="14">{html.escape(label)}</text>
    <text x="103" y="15" fill="#010101" fill-opacity=".3">{html.escape(value)}</text>
    <text x="103" y="14">{html.escape(value)}</text>
  </g>
</svg>
"""
    )


def write_coverage_badges(percent: float, paths: tuple[Path, ...] = BADGE_PATHS) -> list[Path]:
    changed = []
    badge = render_coverage_badge(percent)
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.read_text() == badge:
            continue
        path.write_text(badge)
        changed.append(path)
    return changed


def update_readme_badge(path: Path) -> bool:
    lines = path.read_text().splitlines()
    filtered = [line for line in lines if not line.startswith("![Test coverage](")]
    if filtered and filtered[0].startswith("# "):
        desired = [filtered[0], "", BADGE_MARKER, ""]
        body = filtered[1:]
        while body and body[0] == "":
            body.pop(0)
        updated = desired + body
    else:
        updated = [BADGE_MARKER, "", *filtered]
    output = "\n".join(updated).rstrip() + "\n"
    if path.read_text() == output:
        return False
    path.write_text(output)
    return True


def publish_coverage_badge(
    coverage_path: Path = COVERAGE_JSON,
    readme_paths: tuple[Path, ...] = README_PATHS,
    badge_paths: tuple[Path, ...] = BADGE_PATHS,
) -> tuple[float, list[Path]]:
    percent = coverage_percent(coverage_path)
    changed = write_coverage_badges(percent, badge_paths)
    changed.extend(path for path in readme_paths if update_readme_badge(path))
    return percent, changed
