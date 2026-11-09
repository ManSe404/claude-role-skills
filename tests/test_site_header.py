from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from conftest import ROOT, load

render = load(ROOT / "shared" / "render_page.py")


def page(title: str) -> dict[str, Any]:
    return {
        "skill": "impact",
        "title": title,
        "sections": [{"title": "Notes", "blocks": [{"type": "text", "text": "Plain."}]}],
    }


def write_set(tmp_path: Path, **extra: Any) -> Path:
    """An overview and two pages in sibling folders, one with a space in its name, listed in one site file."""
    for name, title in (("home/map.json", "Overview"), ("alpha/map.json", "Alpha"), ("beta dir/map.json", "Beta")):
        path = tmp_path / name
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(page(title)), encoding="utf-8")
    site: dict[str, Any] = {
        "title": "Acme",
        "pages": [
            {"label": "Overview", "page": "map.json"},
            {"label": "Alpha", "group": "Apps", "page": "../alpha/map.json"},
            {"label": "Beta", "group": "Apps", "page": "../beta dir/map.json"},
        ],
    }
    site.update(extra)
    path = tmp_path / "home" / "site.json"
    path.write_text(json.dumps(site), encoding="utf-8")
    return path


def html_of(tmp_path: Path, folder: str) -> str:
    return (tmp_path / folder / "map.html").read_text(encoding="utf-8")


def test_every_page_links_the_whole_set_from_where_it_stands(tmp_path: Path) -> None:
    assert render.main(["--site", str(write_set(tmp_path))]) == 0
    alpha = html_of(tmp_path, "alpha")
    assert '<a href="../home/map.html">Overview</a>' in alpha
    assert '<a href="map.html" aria-current="page">Alpha</a>' in alpha
    assert '<a href="../beta%20dir/map.html">Beta</a>' in alpha


def test_only_the_current_page_is_marked(tmp_path: Path) -> None:
    assert render.main(["--site", str(write_set(tmp_path))]) == 0
    home = html_of(tmp_path, "home")
    assert home.count('aria-current="page"') == 1
    assert '<a href="map.html" aria-current="page">Overview</a>' in home


def test_the_set_name_leads_to_the_first_page(tmp_path: Path) -> None:
    assert render.main(["--site", str(write_set(tmp_path))]) == 0
    assert '<a class="home" href="../home/map.html" title="Acme">Acme</a>' in html_of(tmp_path, "beta dir")


def test_neighbours_in_a_group_share_one_caption(tmp_path: Path) -> None:
    assert render.main(["--site", str(write_set(tmp_path))]) == 0
    assert html_of(tmp_path, "home").count('<span class="g">Apps</span>') == 1


def test_labels_are_escaped(tmp_path: Path) -> None:
    site = write_set(tmp_path, title="<b>Acme</b>")
    assert render.main(["--site", str(site)]) == 0
    home = html_of(tmp_path, "home")
    assert "&lt;b&gt;Acme&lt;/b&gt;" in home
    assert "<b>Acme</b>" not in home


def test_a_lone_page_has_no_header() -> None:
    html = render.render(page("Alone"))
    assert '<header class="site"' not in html
    assert "header.site" not in html


def test_one_invalid_page_writes_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    site = write_set(tmp_path)
    (tmp_path / "beta dir" / "map.json").write_text(json.dumps({"skill": "impact"}), encoding="utf-8")
    assert render.main(["--site", str(site)]) == 1
    assert "beta dir" in capsys.readouterr().err
    assert not list(tmp_path.rglob("*.html"))


def test_a_missing_page_writes_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    site = write_set(tmp_path)
    (tmp_path / "alpha" / "map.json").unlink()
    assert render.main(["--site", str(site)]) == 1
    assert "cannot read" in capsys.readouterr().err
    assert not list(tmp_path.rglob("*.html"))


def test_check_writes_nothing(tmp_path: Path) -> None:
    assert render.main(["--site", str(write_set(tmp_path)), "--check"]) == 0
    assert not list(tmp_path.rglob("*.html"))


@pytest.mark.parametrize(
    ("site", "expected"),
    [
        ([], "site: must be a JSON object"),
        ({"pages": [{"label": "A", "page": "a.json"}]}, "site.title: missing"),
        ({"title": "T", "pages": []}, "site.pages: at least one page"),
        ({"title": "T", "pages": [{"page": "a.json"}]}, "site.pages[0].label: missing"),
        ({"title": "T", "pages": [{"label": "A"}]}, "site.pages[0].page: missing"),
        ({"title": "T", "pages": [{"label": "A", "page": "a.html"}]}, "site.pages[0].page: must be a page JSON"),
        (
            {"title": "T", "pages": [{"label": "A", "page": "a.json"}, {"label": "B", "page": "a.json"}]},
            "site.pages[1].page: listed twice",
        ),
    ],
)
def test_a_wrong_site_file_is_reported(site: Any, expected: str) -> None:
    assert any(expected in problem for problem in render.validate_site(site))


@pytest.mark.parametrize("argv", [[], ["page.json", "--site", "site.json"], ["--site", "site.json", "-o", "x.html"]])
def test_a_wrong_command_line_is_refused(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as stopped:
        render.main(argv)
    assert stopped.value.code == 2
