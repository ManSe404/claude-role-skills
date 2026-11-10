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
        "cloud-architect/cloud-design",
        "cloud-architect/cloud-map",
        "cloud-architect/cloud-review",
        "data-analyst/metric-spec",
        "data-analyst/number-moved",
        "data-analyst/number-reconcile",
        "data-analyst/report-review",
        "data-architect/data-map",
        "data-architect/data-model",
        "data-architect/data-platform",
        "data-architect/data-review",
        "data-scientist/ds-dataset",
        "data-scientist/ds-evaluate",
        "data-scientist/ds-experiment",
        "data-scientist/ds-explore",
        "data-scientist/ds-frame",
        "software-architect/arch-c4",
        "software-architect/arch-evolve",
        "software-architect/arch-review",
        "software-architect/arch-style",
        "software-engineering/bug-hunt",
        "software-engineering/codebase-map",
        "software-engineering/dependency-audit",
        "software-engineering/impact",
        "software-engineering/test-gap",
        "solutions-architect/solution-blueprint",
        "solutions-architect/solution-brief",
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


CLOUD_SKILLS = [p for p in ALL_SKILLS if p.parent.parent.name == "cloud-architect"]


@pytest.mark.parametrize("skill", CLOUD_SKILLS, ids=[p.name for p in CLOUD_SKILLS])
def test_cloud_skill_text_is_provider_neutral(skill: Path) -> None:
    body = (skill / "SKILL.md").read_text(encoding="utf-8").split("---\n", 2)[2]
    azure = ("Azure", "azurerm", "Microsoft.", " az ", "App Service", "Key Vault", "Container Apps")
    aws = (
        "AWS",
        "aws_",
        " aws ",
        "Amazon",
        "CloudFormation",
        "Fargate",
        " RDS",
        " S3 ",
        "ECS",
        "Secrets Manager",
        "IAM",
    )
    for word in (*azure, *aws):
        assert word not in body, f"{word!r} belongs in a provider file, not in {skill.name}/SKILL.md"
    assert "references/cloud/" in body


def test_cloud_core_scripts_name_no_provider() -> None:
    for name in ("shared/cloud_inventory.py", "shared/cloud_prices.py"):
        text = (ROOT / name).read_text(encoding="utf-8")
        for word in ("azurerm", "Microsoft.", "prices.azure.com", "AWS::", "aws_", "amazonaws"):
            assert word not in text, f"{word!r} belongs in a provider file, not in {name}"
    rules = (ROOT / "plugins/cloud-architect/skills/cloud-design/scripts/cloud_rules.py").read_text("utf-8").lower()
    for word in ("azure", "aws", "microsoft"):
        assert word not in rules, word


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


EVALS = sorted(p.parent for p in ROOT.glob("plugins/*/evals/*/case.yaml"))
EVAL_IDS = [f"{p.parent.parent.name}/{p.name}" for p in EVALS]
GRADERS = sorted(ROOT.glob("plugins/*/evals/*/graders/*.md"))


def test_every_skill_has_an_eval() -> None:
    tagged = {tag for case in EVALS for tag in re.findall(r"[\w-]+", (case / "case.yaml").read_text("utf-8"))}
    missing = sorted(p.name for p in ALL_SKILLS if p.name not in tagged)
    assert not missing, f"no eval for {missing}"


@pytest.mark.parametrize("case", EVALS, ids=EVAL_IDS)
def test_eval_case_files_are_well_formed(case: Path) -> None:
    """Regression: a case.yaml holding a second YAML document fails to load, and `plugin validate` does not catch it."""
    head = (case / "case.yaml").read_text("utf-8")
    assert "---" not in head, "the case's settings belong in prompt.md"
    assert head.startswith('schema_version: "1.1"')
    assert f"name: {case.name}\n" in head
    prompt = (case / "prompt.md").read_text("utf-8")
    assert prompt.startswith("---\n"), "prompt.md starts with its settings"
    assert re.search(r"^runs: 1$", prompt, re.M)
    assert (case / "graders" / "skill-fired.md").is_file()


@pytest.mark.parametrize("grader", GRADERS, ids=[f"{g.parent.parent.name}/{g.stem}" for g in GRADERS])
def test_no_grader_reads_the_whole_trace(grader: Path) -> None:
    """Regression: the trace holds the text of SKILL.md, so a pattern found there proves nothing about what was run."""
    assert "target: trace" not in grader.read_text("utf-8")
