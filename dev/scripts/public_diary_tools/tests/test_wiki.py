from pathlib import Path

import pytest
from public_diary_tools.wiki import stage_wiki_docs


def test_stage_wiki_docs_copies_images_and_rewrites_docs_root_links(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    wiki = tmp_path / "wiki"
    docs.mkdir()
    wiki.mkdir()
    (wiki / ".git").mkdir()
    (wiki / "old.md").write_text("old\n")
    (docs / "images").mkdir()
    (docs / "images" / "coverage.svg").write_text("<svg />\n")
    (docs / "README.md").write_text(
        "# Project\n\n![Test coverage](docs/images/coverage.svg)\n[Setup](docs/setup.md)\n",
    )
    (docs / "setup.md").write_text("# Setup\n")

    changed = stage_wiki_docs(docs, wiki)

    assert sorted(changed) == [Path("Home.md"), Path("images/coverage.svg"), Path("setup.md")]
    assert not (wiki / "old.md").exists()
    assert (wiki / ".git").is_dir()
    assert (wiki / "images" / "coverage.svg").read_text() == "<svg />\n"
    assert (wiki / "Home.md").read_text() == (
        "# Project\n\n![Test coverage](images/coverage.svg)\n[Setup](setup.md)\n"
    )


def test_stage_wiki_docs_requires_existing_paths(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Docs source"):
        stage_wiki_docs(tmp_path / "missing", tmp_path)
    with pytest.raises(ValueError, match="Wiki destination"):
        stage_wiki_docs(tmp_path, tmp_path / "missing")
