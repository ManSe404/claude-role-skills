from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from conftest import ROOT, run_json

SCRIPT = ROOT / "shared" / "chain_status.py"


def page(
    skill: str, title: str, tone: str | None = None, high_open: int = 0, open_items: list[str] | None = None
) -> str:
    data: dict[str, Any] = {
        "skill": skill,
        "title": title,
        "sections": [{"title": "Notes", "blocks": [{"type": "text", "text": "Plain."}]}],
    }
    if tone:
        data["verdict"] = {"text": f"{title} verdict", "tone": tone}
    if high_open:
        items = [{"severity": "high", "title": f"finding {i}"} for i in range(high_open)]
        items.append({"severity": "low", "title": "small", "status": "fixed"})
        data["sections"].append({"title": "Findings", "blocks": [{"type": "findings", "items": items}]})
    if open_items:
        data["facts"] = {"version": 1, "scope": title, "open": open_items}
    return json.dumps(data)


def write_chain(folder: Path) -> None:
    (folder / "codebase-map-2026-11-10.json").write_text(
        page("codebase-map", "Map", "warn", 1, ["the cron job"]), "utf-8"
    )
    (folder / "code-audit-2026-11-09.json").write_text(page("code-audit", "Audit, old", "ok"), "utf-8")
    (folder / "code-audit-2026-11-11.json").write_text(page("code-audit", "Audit", "bad", 2), "utf-8")
    (folder / "code-audit-2026-11-11.html").write_text("<html></html>", "utf-8")
    (folder / "test-gap-2026-11-11.json").write_text('{"skill": "test-gap", "title": "broken"}', "utf-8")
    (folder / "notes-2026-11-11.json").write_text('{"not": "a page of any step"}', "utf-8")


def test_the_newest_valid_page_of_each_step_is_read(tmp_path: Path) -> None:
    write_chain(tmp_path)
    out = run_json(SCRIPT, "--folder", str(tmp_path), "--steps", "codebase-map,code-audit,test-gap,docs-draft")
    by = {s["skill"]: s for s in out["steps"]}
    assert [s["skill"] for s in out["steps"]] == ["codebase-map", "code-audit", "test-gap", "docs-draft"]
    assert by["code-audit"]["file"] == "code-audit-2026-11-11.json" and by["code-audit"]["html"] is True
    assert by["code-audit"]["findings"] == {"high": 2, "medium": 0, "low": 1, "info": 0, "open_high": 2}
    assert by["codebase-map"]["verdict"]["tone"] == "warn" and by["codebase-map"]["open"] == ["the cron job"]
    assert by["codebase-map"]["note"] is False
    assert by["test-gap"]["valid"] is False and by["test-gap"]["problems"]
    assert by["docs-draft"]["page"] is None
    assert out["missing"] == ["test-gap", "docs-draft"]
    assert out["bad"] == ["code-audit"]
    assert out["done"] is False


def test_a_page_older_than_since_is_stale(tmp_path: Path) -> None:
    write_chain(tmp_path)
    out = run_json(SCRIPT, "--folder", str(tmp_path), "--steps", "codebase-map,code-audit", "--since", "2026-11-11")
    by = {s["skill"]: s for s in out["steps"]}
    assert by["codebase-map"]["stale"] is True and by["code-audit"]["stale"] is False
    assert out["missing"] == ["codebase-map"]


def test_a_complete_chain_is_done(tmp_path: Path) -> None:
    (tmp_path / "ds-frame-2026-11-11.json").write_text(page("ds-frame", "Frame", "ok"), "utf-8")
    out = run_json(SCRIPT, "--folder", str(tmp_path), "--steps", "ds-frame")
    assert out["done"] is True and out["missing"] == [] and out["bad"] == []


def test_a_missing_folder_is_an_error(tmp_path: Path) -> None:
    done = subprocess.run(
        [sys.executable, str(SCRIPT), "--folder", str(tmp_path / "nope"), "--steps", "x"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 2 and "not a folder" in done.stderr
