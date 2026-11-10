"""The acme-cloud-aws fixture: the made-up ticket seller on AWS, for the cloud-architect skills.

PLANTED lists the eight problems a review of it must find: (number, short name, file, regex for the flawed line).
PLANTED_AT says where each one sits in the built fixture. ONLY_IN_CODE and ONLY_IN_EXPORT are the two drift items.
RESOURCES counts the resources the inventory must see. The evals and the script tests import these, so keep them in
step with the fixture.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path

import build_fixture
import pytest
from conftest import ROOT, git

TF = "infra/terraform"
CFN = "infra/cloudformation"
APP = f"{TF}/app.tf"
DATA = f"{TF}/data.tf"
NETWORK = f"{TF}/network.tf"
REPORTS = f"{CFN}/reports.yaml"
ADMIN = f"{CFN}/admin.yaml"
ALERTS = f"{CFN}/alerts.json"
EXPORT = "exports/aws-tagging-2026-11-08.json"
PRICES = "prices/aws-price-list-2026-11-10.json"
AZURE_PRICES = "prices/azure-retail-2026-11-10.json"
BRIEF = "docs/briefs/festival-platform.md"

PLANTED: list[tuple[int, str, str, str]] = [
    (1, "database publicly accessible", DATA, r"^\s+publicly_accessible\s+= true$"),
    (2, "S3 bucket without a public access block", REPORTS, r"^  ReportsBucket:$"),
    (
        3,
        "secret in plain environment variables",
        APP,
        r'^\s+\{ name = "SMTP_PASSWORD", value = "fake-smtp-password-not-real-9Kd" \},$',
    ),
    (4, "security group open from anywhere", ADMIN, r"^\s+CidrIp: 0\.0\.0\.0/0$"),
    (5, "single zone where the brief demands two", DATA, r"^\s+multi_az\s+= false$"),
    (6, "no logging on the load balancer", APP, r'^resource "aws_lb" "web" \{$'),
    (7, "IAM policy allowing every action", REPORTS, r'^\s+Action: "\*"$'),
    (
        8,
        "unpinned image tag",
        APP,
        r'^\s+image = "000000000000\.dkr\.ecr\.eu-central-1\.amazonaws\.com/stagefront-worker:latest"$',
    ),
]

PLANTED_AT: dict[int, str] = {
    1: f"{DATA}:22",
    2: f"{REPORTS}:16",
    3: f"{APP}:55",
    4: f"{ADMIN}:27",
    5: f"{DATA}:23",
    6: f"{APP}:1",
    7: f"{REPORTS}:69",
    8: f"{APP}:104",
}

ONLY_IN_CODE: tuple[str, str] = ("aws_s3_bucket.backups", "stagefront-backups-prod")
ONLY_IN_EXPORT: tuple[str, str] = ("AWS::ElastiCache::ReplicationGroup", "stagefront-sessions-prod")
SECRET = "fake-smtp-password-not-real-9Kd"
ACCOUNT = "000000000000"

RESOURCES = 58
PUBLIC = {
    "aws_lb.web",
    "aws_db_instance.main",
    "aws_eip.nat",
    f"{ADMIN}:AdminHost",
    f"{REPORTS}:ReportsBucket",
}

HEAD = "0a7c993"
COMMITS = 5

FILES = ROOT / "fixtures" / "acme-cloud-aws" / "files"
EXTRAS = ROOT / "fixtures" / "acme-cloud-aws" / "extras"
AZURE_EXTRAS = ROOT / "fixtures" / "acme-cloud" / "extras"
ACCOUNT_ID = re.compile(r"\b\d{12}\b")
ADDRESS = re.compile(r"[\w.+-]+@([\w-]+(?:\.[\w-]+)+)")

LAYOUT = [
    ".gitignore",
    "README.md",
    BRIEF,
    ADMIN,
    ALERTS,
    REPORTS,
    APP,
    DATA,
    f"{TF}/iam.tf",
    f"{TF}/locals.tf",
    f"{TF}/messaging.tf",
    f"{TF}/modules/queue/main.tf",
    f"{TF}/monitoring.tf",
    NETWORK,
    f"{TF}/variables.tf",
    f"{TF}/versions.tf",
]


def read(repo: Path, rel: str) -> str:
    return (repo / rel).read_text(encoding="utf-8")


def tracked(repo: Path) -> list[str]:
    return git(repo, "ls-files").splitlines()


def planted_line(repo: Path, rel: str, pattern: str) -> int:
    lines = read(repo, rel).splitlines()
    hits = [number for number, line in enumerate(lines, start=1) if re.search(pattern, line)]
    assert len(hits) == 1, f"{pattern!r} matches lines {hits} of {rel}, expected exactly one"
    return hits[0]


def test_builds_deterministically_with_the_same_head(tmp_path: Path) -> None:
    heads = {build_fixture.build("acme-cloud-aws", tmp_path / name) for name in ("one", "two")}
    assert heads == {HEAD}


def test_history_has_every_commit_and_fictional_authors(aws_repo: Path) -> None:
    log = git(aws_repo, "log", "--format=%h %s").splitlines()
    assert len(log) == COMMITS
    assert log[0] == f"{HEAD} The brief for the festival platform"
    assert all(e.endswith("@example.com") for e in git(aws_repo, "log", "--format=%ae").split())
    assert any("Open the database for the load test" in line for line in log)


def test_layout_is_exact_and_the_last_commit_equals_the_stored_files(aws_repo: Path) -> None:
    assert sorted(tracked(aws_repo)) == sorted(LAYOUT)
    assert git(aws_repo, "status", "--porcelain", "--untracked-files=no") == ""
    for path in FILES.rglob("*"):
        if path.is_file():
            rel = path.relative_to(FILES).as_posix().removesuffix(".fixture")
            assert git(aws_repo, "show", f"HEAD:{rel}") == path.read_text(encoding="utf-8"), rel


def test_extras_are_on_disk_but_not_committed(aws_repo: Path) -> None:
    for rel in (EXPORT, PRICES, AZURE_PRICES):
        assert (aws_repo / rel).is_file()
        assert rel not in tracked(aws_repo)


@pytest.mark.parametrize(("number", "name", "rel", "pattern"), PLANTED, ids=[p[1] for p in PLANTED])
def test_planted_problem_sits_on_its_line(
    aws_repo: Path, record_property: Callable[[str, object], None], number: int, name: str, rel: str, pattern: str
) -> None:
    line = planted_line(aws_repo, rel, pattern)
    record_property("planted", f"{number} {name}: {rel}:{line}")
    assert f"{rel}:{line}" == PLANTED_AT[number]


def test_clean_resources_are_clean_so_a_review_can_tell_them_apart(aws_repo: Path) -> None:
    data = read(aws_repo, DATA)
    assert data.count("restrict_public_buckets = true") == 2
    assert "manage_master_user_password     = true" in data
    assert "stagefront-portal:2.6.1" in read(aws_repo, APP)
    assert "aws_lb_target_group.portal.arn" in read(aws_repo, APP)
    network = read(aws_repo, NETWORK)
    assert network.count('cidr_blocks = ["0.0.0.0/0"]') >= 2  # the 443 rule and the egress rules


def test_the_brief_states_its_facts_without_naming_a_service(aws_repo: Path) -> None:
    text = " ".join(read(aws_repo, BRIEF).split())
    for fact in ["6 services", "1 platform engineer", "survive the loss of one availability zone", "400 GB"]:
        assert fact in text, fact
    assert "at most 5,000 USD" in text and "EU" in text
    words = re.compile(r"(?i)\b(azure|aws|fargate|ecs|rds|app service|container apps|aks|eks)\b")
    assert not words.search(read(aws_repo, BRIEF))


def test_every_id_is_zeros_and_addresses_are_fake(aws_repo: Path) -> None:
    for root in (FILES, EXTRAS):
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix == ".pyc":
                continue
            text = path.read_text(encoding="utf-8")
            if "prices" not in path.parts:  # a price table is full of 12-digit tier boundaries
                assert set(ACCOUNT_ID.findall(text)) <= {ACCOUNT}, path
            assert all(d == "example.com" for d in ADDRESS.findall(text)), path


def test_the_only_secret_is_the_planted_fake_one(aws_repo: Path) -> None:
    holders = [rel for rel in tracked(aws_repo) if SECRET in read(aws_repo, rel)]
    assert holders == [APP]
    assert "fake" in SECRET and "not-real" in SECRET
    assert SECRET not in read(aws_repo, EXPORT)


def test_the_export_is_a_fake_tagging_dump_with_one_row_nothing_in_code_creates(aws_repo: Path) -> None:
    rows = json.loads(read(aws_repo, EXPORT))["ResourceTagMappingList"]
    assert len(rows) == 37
    assert all(r["ResourceARN"].startswith("arn:aws:") for r in rows)
    assert any(ONLY_IN_EXPORT[1] in r["ResourceARN"] for r in rows)
    assert not any(ONLY_IN_CODE[1] in r["ResourceARN"] for r in rows)


def test_the_price_table_is_dated_sourced_and_real(aws_repo: Path) -> None:
    table = json.loads(read(aws_repo, PRICES))
    assert table["as_of"] == "2026-11-10" and "pricing.us-east-1.amazonaws.com" in table["source"]
    assert table["cloud"] == "aws" and table["currency"] == "USD" and len(table["rows"]) >= 200
    for row in table["rows"]:
        assert set(row) >= {"service", "meter", "region", "unit", "unit_price", "tier_min", "effective_from"}
        assert row["region"] == "eu-central-1"
    assert any(r["service"] == "AmazonRDS" and "Multi-AZ" in r["sku"] for r in table["rows"])
    assert any(r["service"] == "AmazonEC2" and r["meter"] == "NatGateway-Hours" for r in table["rows"])


def test_the_azure_prices_here_are_the_azure_fixtures_table(aws_repo: Path) -> None:
    ours = read(aws_repo, AZURE_PRICES)
    assert ours == (AZURE_EXTRAS / AZURE_PRICES).read_text(encoding="utf-8")
