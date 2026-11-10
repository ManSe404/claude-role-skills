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
    """The top-level keys of the frontmatter; a nested block such as `hooks:` comes back as its raw lines."""
    assert text.startswith("---\n")
    block = text.split("---\n", 2)[1]
    meta: dict[str, str] = {}
    key = ""
    for line in block.rstrip("\n").splitlines():
        if line.startswith((" ", "-")) and key:
            meta[key] += line + "\n"
            continue
        key, _, value = line.partition(":")
        meta[key] = value.strip()
    return meta


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
        "software-engineering/change-review",
        "software-engineering/code-audit",
        "software-engineering/codebase-map",
        "software-engineering/dependency-audit",
        "software-engineering/docs-draft",
        "software-engineering/impact",
        "software-engineering/incident-triage",
        "software-engineering/postmortem",
        "software-engineering/test-gap",
        "solutions-architect/solution-blueprint",
        "solutions-architect/solution-brief",
    ]


@pytest.mark.parametrize("skill", ALL_SKILLS, ids=IDS)
def test_skill_shape(skill: Path) -> None:
    text = (skill / "SKILL.md").read_text(encoding="utf-8")
    meta = frontmatter(text)
    assert meta["name"] == skill.name
    # The listing Claude chooses from shows description + when_to_use, and an account with many skills is over the
    # listing budget, so both stay short: what it does in one sentence, when to use it in one or two.
    assert not meta["description"].startswith("Use "), "description says what it does; when goes in when_to_use"
    assert re.match(r"Use (when|before) ", meta["when_to_use"])
    assert len(re.findall(r"\.(?:\s|$)", meta["when_to_use"])) <= 2, "when_to_use is one or two sentences"
    assert len(meta["description"]) + len(meta["when_to_use"]) <= 400
    for value in (meta["description"], meta["when_to_use"]):
        assert ": " not in value and "<" not in value and ">" not in value
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


@pytest.mark.parametrize("skill", ALL_SKILLS, ids=IDS)
def test_every_skill_is_guarded_by_its_own_hook(skill: Path) -> None:
    """The hook finds this skill's guard in a plugin, a project or the personal skills folder, and does nothing if
    there is none: a script that cannot be opened makes python exit 2, which would block every call."""
    hooks = frontmatter((skill / "SKILL.md").read_text("utf-8"))["hooks"]
    personal = (skill / "scripts" / "data_profile.py").is_file()
    flag = " personal" if personal else ""
    path = f'"$d/skills/{skill.name}/scripts/guard.py"'
    roots = '"$CLAUDE_PLUGIN_ROOT" "$CLAUDE_PROJECT_DIR/.claude" "$HOME/.claude"'
    for mode in ("pre", "post") if personal else ("pre",):
        command = f"for d in {roots}; do [ -f {path} ] && exec python3 {path} {mode} {skill.name}{flag}; done; true"
        assert f"command: '{command}'" in hooks
    assert '"Skill|Read|Write|Edit|MultiEdit|NotebookEdit|Bash|WebFetch|WebSearch"' in hooks
    assert ("PostToolUse" in hooks) == personal
    assert (skill / "scripts" / "guard.py").is_file()


@pytest.mark.parametrize("where", ["plugin", "project", "personal", "nowhere"])
def test_the_hook_command_finds_the_guard_or_steps_aside(tmp_path: Path, where: str) -> None:
    import subprocess

    skill = next(s for s in ALL_SKILLS if s.name == "ds-explore")
    hooks = frontmatter((skill / "SKILL.md").read_text("utf-8"))["hooks"]
    command = re.search(r"command: '(.+? pre .+?)'", hooks)
    assert command
    roots = {
        "plugin": tmp_path / "plugin",
        "project": tmp_path / "project" / ".claude",
        "personal": tmp_path / "home" / ".claude",
    }
    if where != "nowhere":
        target = roots[where] / "skills" / "ds-explore" / "scripts"
        target.mkdir(parents=True)
        (target / "guard.py").write_text("import sys; print('ran', *sys.argv[1:])")
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path / "home"),
        "CLAUDE_PROJECT_DIR": str(tmp_path / "project"),
        **({"CLAUDE_PLUGIN_ROOT": str(roots["plugin"])} if where == "plugin" else {}),
    }
    done = subprocess.run(
        ["bash", "-c", command.group(1)], capture_output=True, text=True, env=env, check=False, timeout=30
    )
    assert done.returncode == 0
    assert done.stdout.strip() == ("" if where == "nowhere" else "ran pre ds-explore personal")
