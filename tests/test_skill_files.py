"""Every skill follows the same shape, its links resolve, and the manifests agree."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from conftest import ALL_SKILLS, ROOT, load

SECTIONS = ["## Steps", "## Output", "## Reads", "## Writes", "## Never"]
IDS = [f"{p.parent.parent.name}/{p.name}" for p in ALL_SKILLS]


def frontmatter(text: str) -> dict[str, str]:
    assert text.startswith("---\n")
    block = text.split("---\n", 2)[1]
    return dict(line.split(": ", 1) for line in block.strip().splitlines())


def test_every_pack_has_its_skills() -> None:
    assert IDS == [
        "ai-architect/ai-architecture",
        "ai-architect/ai-pattern",
        "ai-architect/ai-review",
        "ai-architect/ai-stack",
        "data-architect/data-map",
        "data-architect/data-model",
        "data-architect/data-platform",
        "data-architect/data-review",
        "software-architect/arch-c4",
        "software-architect/arch-evolve",
        "software-architect/arch-review",
        "software-architect/arch-style",
        "software-engineering/bug-hunt",
        "software-engineering/codebase-map",
        "software-engineering/dependency-audit",
        "software-engineering/impact",
        "software-engineering/test-gap",
    ]


@pytest.mark.parametrize("skill", ALL_SKILLS, ids=IDS)
def test_skill_shape(skill: Path) -> None:
    text = (skill / "SKILL.md").read_text(encoding="utf-8")
    meta = frontmatter(text)
    assert meta["name"] == skill.name
    assert re.match(r"Use (when|before) ", meta["description"])
    assert len(meta["description"]) <= 1024
    positions = [text.index(s) for s in SECTIONS]
    assert positions == sorted(positions), "sections out of order"
    assert len(text.splitlines()) < 120


@pytest.mark.parametrize("skill", ALL_SKILLS, ids=IDS)
def test_skill_links_resolve(skill: Path) -> None:
    text = (skill / "SKILL.md").read_text(encoding="utf-8")
    for rel in re.findall(r"\$\{CLAUDE_SKILL_DIR\}/([\w./-]+)", text):
        assert (skill / rel).is_file(), rel
    for rel in re.findall(r"\]\((references/[\w./-]+)\)", text):
        assert (skill / rel).is_file(), rel


def test_shared_copies_are_in_sync() -> None:
    sync = load(ROOT / "tools" / "sync_shared.py")
    assert sync.main(["--check"]) == 0


def test_marketplace_and_plugin_manifests_agree() -> None:
    market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    for entry in market["plugins"]:
        plugin_dir = ROOT / entry["source"]
        manifest = json.loads((plugin_dir / ".claude-plugin" / "plugin.json").read_text())
        assert manifest["name"] == entry["name"]
        assert manifest["version"] == entry["version"]
        skills = sorted(p.parent.name for p in plugin_dir.glob("skills/*/SKILL.md"))
        for skill in skills:
            assert skill in manifest["description"], f"{skill} missing from the {entry['name']} description"


def test_no_client_names_or_real_addresses_in_examples() -> None:
    for path in list(ROOT.glob("plugins/*/skills/*/references/example.json")) + list((ROOT / "fixtures").rglob("*.*")):
        if path.is_file() and path.suffix in {".json", ".py", ".md", ".csv", ".log", ".yml", ".fixture", ".example"}:
            text = path.read_text(encoding="utf-8", errors="replace")
            emails = re.findall(r"[\w.+-]+@([\w-]+\.[\w.]+)", text)
            assert all(d.lower().startswith("example.") for d in emails), (path, emails)
