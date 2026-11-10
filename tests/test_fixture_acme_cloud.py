"""The acme-cloud fixture: the made-up ticket seller the cloud-architect skills are tested and shown on.

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
APP = f"{TF}/app.tf"
DATA = f"{TF}/data.tf"
NETWORK = f"{TF}/network.tf"
WORKER = f"{TF}/modules/worker/main.tf"
REPORTS = "infra/bicep/modules/reports.bicep"
EXPORT = "exports/az-resource-list-2026-11-08.json"
PRICES = "prices/azure-retail-2026-11-10.json"
BRIEF_SMALL = "docs/briefs/box-office.md"
BRIEF_LARGE = "docs/briefs/festival-platform.md"

PLANTED: list[tuple[int, str, str, str]] = [
    (1, "database open to the internet", DATA, r'^\s+end_ip_address\s+= "255\.255\.255\.255"$'),
    (2, "storage allows public blobs", REPORTS, r"^\s+allowBlobPublicAccess: true$"),
    (3, "secret in plain app settings", APP, r'^\s+"SMTP_PASSWORD"\s+= "fake-smtp-password-not-real-7Qw"$'),
    (4, "no diagnostic settings on the database", DATA, r'^resource "azurerm_mssql_server" "main" \{$'),
    (5, "single zone where the brief demands two", DATA, r"^\s+zone_redundant = false$"),
    (6, "NSG open from anywhere", NETWORK, r'^\s+source_address_prefix\s+= "\*"$'),
    (7, "no managed identity on the portal", APP, r'^resource "azurerm_linux_web_app" "portal" \{$'),
    (8, "unpinned image tag", REPORTS, r"^\s+image: 'acrticketsprod\.azurecr\.io/reports-api:latest'$"),
]

PLANTED_AT: dict[int, str] = {
    1: f"{DATA}:25",
    2: f"{REPORTS}:13",
    3: f"{APP}:34",
    4: f"{DATA}:1",
    5: f"{DATA}:17",
    6: f"{NETWORK}:63",
    7: f"{APP}:12",
    8: f"{REPORTS}:58",
}

ONLY_IN_CODE: tuple[str, str] = ("azurerm_storage_account.backups", "stacmebackupsprod")
ONLY_IN_EXPORT: tuple[str, str] = ("Microsoft.Cache/Redis", "redis-acme-sessions-prod")
SECRET = "fake-smtp-password-not-real-7Qw"
ZERO_GUID = "00000000-0000-0000-0000-000000000000"

RESOURCES = 39
PUBLIC = {
    "azurerm_linux_web_app.portal",
    "azurerm_mssql_server.main",
    "azurerm_servicebus_namespace.main",
    "infra/bicep/main.bicep:reports.reportsStorage",
    "infra/bicep/main.bicep:reports.reportsApi",
}

HEAD = "a509e4e"
COMMITS = 5

FILES = ROOT / "fixtures" / "acme-cloud" / "files"
EXTRAS = ROOT / "fixtures" / "acme-cloud" / "extras"
GUID = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
ADDRESS = re.compile(r"[\w.+-]+@([\w-]+(?:\.[\w-]+)+)")

LAYOUT = [
    ".gitignore",
    "README.md",
    BRIEF_SMALL,
    BRIEF_LARGE,
    "infra/arm/alerts.json",
    "infra/bicep/main.bicep",
    REPORTS,
    APP,
    DATA,
    f"{TF}/locals.tf",
    f"{TF}/main.tf",
    f"{TF}/messaging.tf",
    WORKER,
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
    heads = {build_fixture.build("acme-cloud", tmp_path / name) for name in ("one", "two")}
    assert heads == {HEAD}


def test_history_has_every_commit_and_fictional_authors(cloud_repo: Path) -> None:
    log = git(cloud_repo, "log", "--format=%h %s").splitlines()
    assert len(log) == COMMITS
    assert log[0] == f"{HEAD} Briefs: the box office and the festival platform"
    assert all(e.endswith("@example.com") for e in git(cloud_repo, "log", "--format=%ae").split())
    assert any("Open the database for the load test" in line for line in log)


def test_layout_is_exact_and_the_last_commit_equals_the_stored_files(cloud_repo: Path) -> None:
    assert sorted(tracked(cloud_repo)) == sorted(LAYOUT)
    assert git(cloud_repo, "status", "--porcelain", "--untracked-files=no") == ""
    for path in FILES.rglob("*"):
        if path.is_file():
            rel = path.relative_to(FILES).as_posix().removesuffix(".fixture")
            assert git(cloud_repo, "show", f"HEAD:{rel}") == path.read_text(encoding="utf-8"), rel


def test_extras_are_on_disk_but_not_committed(cloud_repo: Path) -> None:
    for rel in (EXPORT, PRICES):
        assert (cloud_repo / rel).is_file()
        assert rel not in tracked(cloud_repo)


@pytest.mark.parametrize(("number", "name", "rel", "pattern"), PLANTED, ids=[p[1] for p in PLANTED])
def test_planted_problem_sits_on_its_line(
    cloud_repo: Path, record_property: Callable[[str, object], None], number: int, name: str, rel: str, pattern: str
) -> None:
    line = planted_line(cloud_repo, rel, pattern)
    record_property("planted", f"{number} {name}: {rel}:{line}")
    assert f"{rel}:{line}" == PLANTED_AT[number]


def test_clean_resources_are_clean_so_a_review_can_tell_them_apart(cloud_repo: Path) -> None:
    data = read(cloud_repo, DATA)
    assert data.count("public_network_access_enabled   = false") == 2  # tickets and backups storage
    assert "public_network_access_enabled = false" in data  # the Key Vault
    worker = read(cloud_repo, WORKER)
    assert 'type = "SystemAssigned"' in worker and "var.image" in worker
    assert "tickets-worker:1.8.2" in read(cloud_repo, APP)
    monitoring = read(cloud_repo, f"{TF}/monitoring.tf")
    assert "azurerm_key_vault.main.id" in monitoring and "azurerm_linux_web_app.portal.id" in monitoring
    assert "azurerm_mssql" not in monitoring


def test_the_small_brief_states_its_facts_without_naming_a_service(cloud_repo: Path) -> None:
    text = " ".join(read(cloud_repo, BRIEF_SMALL).split())
    for fact in ["2 engineers", "no platform engineers", "one web application", "20 requests a second", "30 GB"]:
        assert fact in text, fact
    for fact in ["at most 200 USD", "EU", "Daily backups", "no events"]:
        assert fact in text, fact


def test_the_large_brief_needs_containers_zones_and_private_data_but_no_kubernetes(cloud_repo: Path) -> None:
    text = " ".join(read(cloud_repo, BRIEF_LARGE).split())
    for fact in ["6 services", "container images", "1 platform engineer", "None of them needs the Kubernetes API"]:
        assert fact in text, fact
    for fact in ["only on private addresses", "loss of one availability zone", "600 requests a second", "400 GB"]:
        assert fact in text, fact
    assert "whole region is an accepted risk" in text


def test_briefs_name_no_cloud_service(cloud_repo: Path) -> None:
    words = re.compile(r"(?i)\b(azure|aws|app service|container apps|aks|sql database|serverless)\b")
    for rel in (BRIEF_SMALL, BRIEF_LARGE):
        assert not words.search(read(cloud_repo, rel)), rel


def test_every_id_is_the_zero_guid_and_addresses_are_fake(cloud_repo: Path) -> None:
    for root in (FILES, EXTRAS):
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            assert set(GUID.findall(text)) <= {ZERO_GUID}, path
            assert all(d == "example.com" for d in ADDRESS.findall(text)), path


def test_the_only_secret_is_the_planted_fake_one(cloud_repo: Path) -> None:
    holders = [rel for rel in tracked(cloud_repo) if SECRET in read(cloud_repo, rel)]
    assert holders == [APP]
    assert "fake" in SECRET and "not-real" in SECRET
    assert SECRET not in (cloud_repo / EXPORT).read_text(encoding="utf-8")


def test_the_export_is_a_fake_az_resource_list_with_one_row_nothing_in_code_creates(cloud_repo: Path) -> None:
    rows = json.loads(read(cloud_repo, EXPORT))
    assert isinstance(rows, list) and len(rows) == 26
    assert all(r["id"].startswith(f"/subscriptions/{ZERO_GUID}/") for r in rows)
    names = {r["name"] for r in rows}
    assert ONLY_IN_EXPORT[1] in names
    assert ONLY_IN_CODE[1] not in names


def test_the_price_table_is_dated_and_sourced(cloud_repo: Path) -> None:
    table = json.loads(read(cloud_repo, PRICES))
    assert table["as_of"] == "2026-11-10"
    assert "prices.azure.com" in table["source"]
    assert table["cloud"] == "azure" and table["currency"] == "USD"
    assert len(table["rows"]) >= 100
    for row in table["rows"]:
        assert set(row) >= {"service", "sku", "meter", "region", "unit", "unit_price", "tier_min", "effective_from"}
