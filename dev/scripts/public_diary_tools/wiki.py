from __future__ import annotations

import re
import shutil
from pathlib import Path

DOCS_ROOT_PREFIX_RE = re.compile(r"(?P<prefix>!?\[[^\]]*]\()docs/(?P<target>[^)\s]+)(?P<suffix>(?:\s+\"[^\"]*\")?\))")


def _remove_existing_wiki_files(destination: Path) -> None:
    for path in destination.iterdir():
        if path.name == ".git":
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()


def _rewrite_wiki_markdown(markdown: str) -> str:
    return DOCS_ROOT_PREFIX_RE.sub(r"\g<prefix>\g<target>\g<suffix>", markdown)


def _wiki_relative_path(source_relative_path: Path) -> Path:
    if source_relative_path == Path("README.md"):
        return Path("Home.md")
    return source_relative_path


def stage_wiki_docs(source: Path = Path("docs"), destination: Path = Path("wiki")) -> list[Path]:
    """Copy docs into a wiki checkout and rewrite docs-root links."""
    if not source.is_dir():
        raise ValueError(f"Docs source does not exist: {source}")
    if not destination.is_dir():
        raise ValueError(f"Wiki destination does not exist: {destination}")

    _remove_existing_wiki_files(destination)
    changed: list[Path] = []
    for source_path in source.rglob("*"):
        if source_path.is_dir():
            continue
        relative_path = source_path.relative_to(source)
        wiki_path = _wiki_relative_path(relative_path)
        destination_path = destination / wiki_path
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        if source_path.suffix == ".md":
            destination_path.write_text(_rewrite_wiki_markdown(source_path.read_text()))
        else:
            shutil.copy2(source_path, destination_path)
        changed.append(wiki_path)
    return changed
