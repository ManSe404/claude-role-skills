"""The acme-logistics fixture: the made-up parcel company the software-architect skills are tested and shown on.

PLANTED lists the eight structural problems a review of it must find: (number, short name, file, regex for the flawed
line). PLANTED_AT says where each one sits in the built fixture. MODULE_EDGES is the namespace-level dependency graph of
the C# code, COCHANGE the two files that always change together and COCHANGE_COMMITS how often, HOT_FILE the most
changed file and HOT_FILE_COMMITS how often, BILLING_AUTHOR the one person who has touched Billing, as
`git log --format=%an` prints it. The evals and the script tests import these, so keep them in step with the fixture.
"""

from __future__ import annotations

import json
import re
import tomllib
from collections import Counter
from collections.abc import Callable
from pathlib import Path

import build_fixture
import pytest
from conftest import ROOT, git

SERVICE = "src/Acme.Logistics/Shipments/ShipmentService.cs"
RULES = "src/Acme.Logistics/Shipments/PricingRules.cs"
PRICING = "web/src/app/shipments/pricing.ts"
BILLING = "src/Acme.Logistics/Billing/BillingService.cs"
PARCEL = "src/Acme.Logistics/Domain/Parcel.cs"
MONEY = "src/Acme.Logistics/Domain/Money.cs"
HELPERS = "src/Acme.Logistics/Common/Helpers.cs"
REPOSITORY = "src/Acme.Logistics/Infrastructure/ShipmentRepository.cs"
WORKER_DB = "worker/src/acme_worker/db.py"
WORKER_API = "worker/src/acme_worker/api_client.py"

PLANTED: list[tuple[int, str, str, str]] = [
    (1, "cycle between Shipments and Billing", SERVICE, r"^using Acme\.Logistics\.Billing;$"),
    (2, "domain depends on infrastructure", PARCEL, r"^using Acme\.Logistics\.Infrastructure;$"),
    (3, "dumping-ground module", HELPERS, r"^public static class Helpers$"),
    (4, "pricing rule written twice", RULES, r"^\s+private const decimal HeavySurcharge = 1\.30m;$"),
    (5, "worker writes a table the API owns", WORKER_DB, r'^\s+"UPDATE shipments SET status = %s WHERE id = %s",$'),
    (6, "hot spot", SERVICE, r"^public class ShipmentService$"),
    (
        7,
        "synchronous loop between services",
        WORKER_API,
        r'^\s+f"http://api:8080/api/shipments/\{shipment_id\}/tracking",$',
    ),
    (8, "only one person touches Billing", BILLING, r"^public class BillingService$"),
]

PLANTED_AT: dict[int, str] = {
    1: f"{SERVICE}:2",
    2: f"{PARCEL}:1",
    3: f"{HELPERS}:6",
    4: f"{RULES}:10",
    5: f"{WORKER_DB}:11",
    6: f"{SERVICE}:24",
    7: f"{WORKER_API}:8",
    8: f"{BILLING}:8",
}

MODULE_EDGES: list[tuple[str, str]] = [
    ("Acme.Logistics.Shipments", "Acme.Logistics.Billing"),
    ("Acme.Logistics.Billing", "Acme.Logistics.Shipments"),
    ("Acme.Logistics.Domain", "Acme.Logistics.Infrastructure"),
    ("Acme.Logistics.Infrastructure", "Acme.Logistics.Domain"),
    ("Acme.Api.Controllers", "Acme.Logistics.Shipments"),
    ("Acme.Api.Controllers", "Acme.Logistics.Billing"),
    ("Acme.Api.Controllers", "Acme.Logistics.Common"),
    ("Acme.Logistics.Shipments", "Acme.Logistics.Domain"),
    ("Acme.Logistics.Shipments", "Acme.Logistics.Infrastructure"),
    ("Acme.Logistics.Shipments", "Acme.Logistics.Common"),
    ("Acme.Logistics.Billing", "Acme.Logistics.Domain"),
    ("Acme.Logistics.Billing", "Acme.Logistics.Infrastructure"),
    ("Acme.Logistics.Billing", "Acme.Logistics.Common"),
    ("Acme.Logistics.Infrastructure", "Acme.Logistics.Common"),
]

COCHANGE: tuple[str, str] = (RULES, PRICING)
COCHANGE_COMMITS: int = 6
HOT_FILE: str = SERVICE
HOT_FILE_COMMITS: int = 9
BILLING_AUTHOR: str = "Dunja Petrak"
COMPOSE_SERVICES: list[str] = ["api", "web", "worker", "db", "queue"]

HEAD = "432aa50"
COMMITS = 16

FILES = ROOT / "fixtures" / "acme-logistics" / "files"
LIBRARY = "src/Acme.Logistics/"

LAYOUT = [
    ".gitignore",
    "README.md",
    "docker-compose.yml",
    "docs/briefs/fleet-platform.md",
    "docs/briefs/quick-booking.md",
    "src/Acme.Api/Acme.Api.csproj",
    "src/Acme.Api/Controllers/InvoicesController.cs",
    "src/Acme.Api/Controllers/ShipmentsController.cs",
    "src/Acme.Api/Dockerfile",
    "src/Acme.Api/Program.cs",
    "src/Acme.Logistics/Acme.Logistics.csproj",
    "src/Acme.Logistics/Billing/BillingService.cs",
    "src/Acme.Logistics/Billing/Invoice.cs",
    "src/Acme.Logistics/Common/Helpers.cs",
    "src/Acme.Logistics/Domain/Money.cs",
    "src/Acme.Logistics/Domain/Parcel.cs",
    "src/Acme.Logistics/Infrastructure/Database.cs",
    "src/Acme.Logistics/Infrastructure/MessageBus.cs",
    "src/Acme.Logistics/Infrastructure/ShipmentRepository.cs",
    "src/Acme.Logistics/Shipments/PricingRules.cs",
    "src/Acme.Logistics/Shipments/Shipment.cs",
    "src/Acme.Logistics/Shipments/ShipmentService.cs",
    "web/Dockerfile",
    "web/package.json",
    "web/src/app/api/client.ts",
    "web/src/app/app.ts",
    "web/src/app/invoices/invoices.ts",
    "web/src/app/shipments/pricing.ts",
    "web/src/app/shipments/shipments.ts",
    "worker/Dockerfile",
    "worker/pyproject.toml",
    "worker/src/acme_worker/__init__.py",
    "worker/src/acme_worker/__main__.py",
    "worker/src/acme_worker/api_client.py",
    "worker/src/acme_worker/db.py",
    "worker/src/acme_worker/notifications.py",
    "worker/src/acme_worker/tracking.py",
]

ADDRESS = re.compile(r"[\w.+-]+@([\w-]+(?:\.[\w-]+)+)")


def read(repo: Path, rel: str) -> str:
    return (repo / rel).read_text(encoding="utf-8")


def tracked(repo: Path) -> list[str]:
    return git(repo, "ls-files").splitlines()


def csharp(repo: Path) -> dict[str, str]:
    return {rel: read(repo, rel) for rel in tracked(repo) if rel.endswith(".cs")}


def namespace_of(text: str) -> str | None:
    match = re.search(r"^namespace ([\w.]+);$", text, re.MULTILINE)
    return match.group(1) if match else None


def usings(text: str) -> set[str]:
    return set(re.findall(r"^using (Acme\.[\w.]+);$", text, re.MULTILINE))


def history(repo: Path) -> list[tuple[str, list[str]]]:
    """(author name, files changed) per commit, newest first."""
    log = git(repo, "log", "--format=%x00%an", "--name-only")
    commits: list[tuple[str, list[str]]] = []
    for chunk in log.split("\0")[1:]:
        lines = [line for line in chunk.splitlines() if line]
        commits.append((lines[0], lines[1:]))
    return commits


def planted_line(repo: Path, rel: str, pattern: str) -> int:
    """The 1-based line in repo/rel that pattern matches; it must match exactly one line."""
    lines = read(repo, rel).splitlines()
    hits = [number for number, line in enumerate(lines, start=1) if re.search(pattern, line)]
    assert len(hits) == 1, f"{pattern!r} matches lines {hits} of {rel}, expected exactly one"
    return hits[0]


def compose_services(text: str) -> dict[str, str]:
    """The block of each service under `services:`, by name."""
    body = text.split("services:\n", 1)[1]
    parts = re.split(r"^  (\w+):\n", body, flags=re.MULTILINE)[1:]
    return dict(zip(parts[::2], parts[1::2], strict=True))


def depends_on(block: str) -> list[str]:
    return re.findall(r"^      - (\w+)$", block, re.MULTILINE)


def test_builds_deterministically_with_the_same_head(tmp_path: Path) -> None:
    heads = {build_fixture.build("acme-logistics", tmp_path / name) for name in ("one", "two")}
    assert heads == {HEAD}


def test_history_has_every_commit_three_authors_and_fictional_dates(logistics_repo: Path) -> None:
    log = git(logistics_repo, "log", "--format=%h %s").splitlines()
    assert len(log) == COMMITS
    assert log[0] == f"{HEAD} Briefs: a booking app for Acme Couriers and the fleet platform"
    assert log[-1].endswith(" Start the API: book, find and cancel shipments")
    emails = set(git(logistics_repo, "log", "--format=%ae").split())
    assert len(emails) == 3
    assert all(email.endswith("@example.com") for email in emails)
    days = git(logistics_repo, "log", "--format=%ad", "--date=short").split()
    assert all("2026-03-01" <= day <= "2026-10-31" for day in days)
    assert days == sorted(days, reverse=True)


def test_layout_is_exact_and_the_last_commit_equals_the_stored_files(logistics_repo: Path) -> None:
    assert sorted(tracked(logistics_repo)) == sorted(LAYOUT)
    assert git(logistics_repo, "status", "--porcelain") == ""
    for path in FILES.rglob("*"):
        if path.is_file():
            rel = path.relative_to(FILES).as_posix().removesuffix(".fixture")
            assert git(logistics_repo, "show", f"HEAD:{rel}") == path.read_text(encoding="utf-8"), rel


@pytest.mark.parametrize(("number", "name", "rel", "pattern"), PLANTED, ids=[p[1] for p in PLANTED])
def test_planted_problem_sits_on_its_line(
    logistics_repo: Path, record_property: Callable[[str, object], None], number: int, name: str, rel: str, pattern: str
) -> None:
    line = planted_line(logistics_repo, rel, pattern)
    record_property("planted", f"{number} {name}: {rel}:{line}")
    assert f"{rel}:{line}" == PLANTED_AT[number]


def test_every_project_file_has_its_manifest_and_kind(logistics_repo: Path) -> None:
    assert '<Project Sdk="Microsoft.NET.Sdk.Web">' in read(logistics_repo, "src/Acme.Api/Acme.Api.csproj")
    assert r'<ProjectReference Include="..\Acme.Logistics\Acme.Logistics.csproj" />' in read(
        logistics_repo, "src/Acme.Api/Acme.Api.csproj"
    )
    assert '<Project Sdk="Microsoft.NET.Sdk">' in read(logistics_repo, "src/Acme.Logistics/Acme.Logistics.csproj")
    assert "start" in json.loads(read(logistics_repo, "web/package.json"))["scripts"]
    project = tomllib.loads(read(logistics_repo, "worker/pyproject.toml"))["project"]
    assert project["scripts"] == {"acme-worker": "acme_worker.__main__:main"}


def test_the_namespace_dependencies_are_exactly_these(logistics_repo: Path) -> None:
    found = set()
    for text in csharp(logistics_repo).values():
        namespace = namespace_of(text)
        if namespace:
            found |= {(namespace, used) for used in usings(text) if used != namespace}
    assert found == set(MODULE_EDGES)
    assert len(MODULE_EDGES) == len(set(MODULE_EDGES))


def test_each_namespace_matches_its_folder(logistics_repo: Path) -> None:
    for rel, text in csharp(logistics_repo).items():
        if rel.endswith("Program.cs"):
            assert namespace_of(text) is None
            continue
        expected = str(Path(rel).parent.relative_to("src")).replace("/", ".")
        assert namespace_of(text) == expected, rel


def test_the_cycle_runs_both_ways(logistics_repo: Path) -> None:
    assert "using Acme.Logistics.Billing;" in read(logistics_repo, SERVICE)
    assert "using Acme.Logistics.Shipments;" in read(logistics_repo, BILLING)


def test_only_parcel_in_the_domain_imports_infrastructure_and_money_imports_nothing(logistics_repo: Path) -> None:
    importing = [
        rel
        for rel, text in csharp(logistics_repo).items()
        if rel.startswith(f"{LIBRARY}Domain/") and "using Acme.Logistics.Infrastructure;" in text
    ]
    assert importing == [PARCEL]
    assert usings(read(logistics_repo, MONEY)) == set()
    assert usings(read(logistics_repo, HELPERS)) == set()


def test_helpers_is_a_dumping_ground_imported_from_all_over(logistics_repo: Path) -> None:
    helpers = read(logistics_repo, HELPERS)
    for name in ("FormatDate", "AddVat", "CleanText", "Retry"):
        assert f" {name}(" in helpers, name
    importers = {
        rel: namespace_of(text)
        for rel, text in csharp(logistics_repo).items()
        if "using Acme.Logistics.Common;" in text and namespace_of(text) != "Acme.Logistics.Common"
    }
    assert len(importers) >= 5
    assert len(set(importers.values())) >= 4


def test_the_pricing_rule_is_written_twice_with_no_code_link(logistics_repo: Path) -> None:
    rules = read(logistics_repo, RULES)
    pricing = read(logistics_repo, PRICING)
    pairs = {
        "BasePrice = 250m": "BASE_PRICE = 250",
        "PricePerKg = 40m": "PRICE_PER_KG = 40",
        "HeavyThresholdKg = 20m": "HEAVY_THRESHOLD_KG = 20",
        "HeavySurcharge = 1.30m": "HEAVY_SURCHARGE = 1.3",
        "ExpressMultiplier = 1.50m": "EXPRESS_MULTIPLIER = 1.5",
        "RemoteZoneFee = 180m": "REMOTE_ZONE_FEE = 180",
        "FuelSurcharge = 1.06m": "FUEL_SURCHARGE = 1.06",
        "VolumetricDivisor = 5000m": "VOLUMETRIC_DIVISOR = 5000",
    }
    for in_csharp, in_typescript in pairs.items():
        assert in_csharp in rules, in_csharp
        assert in_typescript in pricing, in_typescript
    assert not re.search(r"^import ", pricing, re.MULTILINE)
    assert not re.search(r"http|/api/|fetch", pricing)
    assert "pricing.ts" not in rules
    assert "web/" not in rules


def test_the_cochange_is_true_from_git_log(logistics_repo: Path) -> None:
    first, second = COCHANGE
    commits = history(logistics_repo)
    together = [files for _, files in commits if first in files and second in files]
    assert len(together) == COCHANGE_COMMITS >= 5
    assert not [files for _, files in commits if (first in files) != (second in files)]


def test_the_hot_spot_is_true_from_git_log_and_is_the_largest_code_file(logistics_repo: Path) -> None:
    changes = Counter(path for _, files in history(logistics_repo) for path in files)
    assert changes[HOT_FILE] == HOT_FILE_COMMITS >= 8
    assert all(count < HOT_FILE_COMMITS for path, count in changes.items() if path != HOT_FILE)
    lengths = {
        rel: len(read(logistics_repo, rel).splitlines())
        for rel in tracked(logistics_repo)
        if rel.endswith((".cs", ".ts", ".py"))
    }
    assert lengths[HOT_FILE] >= 200
    assert all(length < lengths[HOT_FILE] for rel, length in lengths.items() if rel != HOT_FILE)


def test_one_person_only_ever_touched_billing(logistics_repo: Path) -> None:
    commits = history(logistics_repo)
    in_billing = [author for author, files in commits if any(f.startswith(f"{LIBRARY}Billing/") for f in files)]
    assert set(in_billing) == {BILLING_AUTHOR}
    assert len(in_billing) >= 3
    others = Counter(author for author, files in commits if not any(f.startswith(f"{LIBRARY}Billing/") for f in files))
    assert others.most_common(1)[0][0] != BILLING_AUTHOR
    assert Counter(author for author, _ in commits).most_common(1)[0][0] != BILLING_AUTHOR
    for folder in ("Shipments", "Domain", "Infrastructure", "Common"):
        authors = {author for author, files in commits if any(f.startswith(f"{LIBRARY}{folder}/") for f in files)}
        assert len(authors) > 1, folder


def test_the_worker_writes_straight_to_the_table_of_the_api(logistics_repo: Path) -> None:
    assert "UPDATE shipments SET status = %s" in read(logistics_repo, WORKER_DB)
    repository = read(logistics_repo, REPOSITORY)
    assert "INSERT INTO shipments" in repository
    assert "UPDATE shipments SET status = @status" in repository
    assert "FROM shipments s" in repository
    tracking = read(logistics_repo, "worker/src/acme_worker/tracking.py")
    assert 'set_shipment_status(shipment_id, "Delivered")' in tracking


def test_the_api_and_the_worker_call_each_other_inside_a_request(logistics_repo: Path) -> None:
    assert 'PostAsJsonAsync("http://worker:8081/track"' in read(logistics_repo, SERVICE)
    assert '[HttpGet("{id:guid}/tracking")]' in read(logistics_repo, "src/Acme.Api/Controllers/ShipmentsController.cs")
    assert 'self.path != "/track"' in read(logistics_repo, "worker/src/acme_worker/__main__.py")
    assert "http://api:8080/api/shipments/" in read(logistics_repo, WORKER_API)
    assert "report_tracking(shipment_id, status, location)" in read(
        logistics_repo, "worker/src/acme_worker/tracking.py"
    )
    assert '[HttpPost("{id:guid}/tracking")]' in read(logistics_repo, "src/Acme.Api/Controllers/ShipmentsController.cs")


def test_compose_runs_the_five_services_with_placeholders_only(logistics_repo: Path) -> None:
    text = read(logistics_repo, "docker-compose.yml")
    services = compose_services(text)
    assert sorted(services) == sorted(COMPOSE_SERVICES)
    assert "build: ./src/Acme.Api\n" in services["api"]
    assert "build: ./web\n" in services["web"]
    assert "build: ./worker\n" in services["worker"]
    assert "image: postgres:16\n" in services["db"]
    assert "image: rabbitmq:3-management\n" in services["queue"]
    assert depends_on(services["api"]) == ["db", "queue"]
    assert depends_on(services["worker"]) == ["db", "queue"]
    assert depends_on(services["web"]) == ["api"]
    assert "ACME_DATABASE_URL" in services["api"] and "ACME_DATABASE_URL" in services["worker"]
    secrets = re.findall(r"(?:Password=|PASSWORD: |PASS: |acme:)([\w-]+)", text)
    assert secrets and set(secrets) == {"change-me"}
    assert 'GetEnvironmentVariable("ACME_DATABASE_URL")' in read(logistics_repo, "src/Acme.Api/Program.cs")
    assert 'os.environ["ACME_DATABASE_URL"]' in read(logistics_repo, WORKER_DB)


def test_typescript_and_python_import_the_way_the_project_says(logistics_repo: Path) -> None:
    assert "from './pricing'" in read(logistics_repo, "web/src/app/shipments/shipments.ts")
    assert "from '../api/client'" in read(logistics_repo, "web/src/app/invoices/invoices.ts")
    assert "from acme_worker.api_client import report_tracking" in read(
        logistics_repo, "worker/src/acme_worker/tracking.py"
    )


def test_briefs_state_their_facts_without_naming_an_architecture(logistics_repo: Path) -> None:
    quick = " ".join(read(logistics_repo, "docs/briefs/quick-booking.md").split())
    fleet = " ".join(read(logistics_repo, "docs/briefs/fleet-platform.md").split())
    for fact in ["Acme Couriers", "4 engineers", "one team", "3 business areas", "booking, dispatch and invoicing"]:
        assert fact in quick, fact
    for fact in ["released together once a week", "about twice the load", "one runtime, .NET"]:
        assert fact in quick, fact
    for fact in ["saved in one transaction", "steady during business hours", "no platform engineers"]:
        assert fact in quick, fact
    for fact in ["30 engineers", "4 product teams", "2 platform engineers", "5 business areas"]:
        assert fact in fleet, fact
    for fact in ["telemetry ingestion takes about 200 times the load", "on their own schedules", "Python", ".NET"]:
        assert fact in fleet, fact
    for fact in ["react to the same vehicle events", "No transaction spans two business areas"]:
        assert fact in fleet, fact
    for fact in ["steady day and night", "up to 40 minutes"]:
        assert fact in fleet, fact
    architecture = re.compile(
        r"\b(micro-?services?|monolith\w*|modular|event[- ]driven|event sourcing|serverless|kafka|kubernetes|saga)\b",
        re.IGNORECASE,
    )
    assert not architecture.search(quick + " " + fleet)


def test_only_example_addresses(logistics_repo: Path) -> None:
    for domain in git(logistics_repo, "log", "--format=%ae%n%ce").split():
        assert domain.endswith("@example.com"), domain
    for rel in tracked(logistics_repo):
        for domain in ADDRESS.findall(read(logistics_repo, rel)):
            assert domain == "example.com", (rel, domain)
