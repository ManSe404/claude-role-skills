"""The acme-design fixture: the design documents of a parcel booking system that is not built yet, for arch-review.

PLANTED lists the eight design flaws a review of it must find, as (id, short name, file, regex for an evidence line).
A flaw whose evidence sits in two or more places has one entry per place: D1 needs both the latency goal and the
carrier latency, D6 both the proposal and the ADR. DECOYS lists, the same way, three choices that look like flaws and
are fine. PLANTED_AT and DECOYS_AT give each id its places in the built fixture as file:line, in list order.
SERVICES are the services that keep their data in the Data Service, PARTS every part a reader can name.
The evals and the script tests import these, so keep them in step with the fixture.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

import build_fixture
import pytest
from conftest import ROOT, git

README = "README.md"
PROPOSAL = "design/proposal.md"
GOALS = "design/quality-goals.md"
ADR_SERVICES = "design/adr/0001-split-booking-into-services.md"
ADR_DATA = "design/adr/0002-central-data-service.md"
ADR_TRACKING = "design/adr/0003-tracking-polls-booking.md"
ADR_BROKER = "design/adr/0004-message-broker.md"

SYNC_CHAIN = "synchronous chain against the latency goal"
SHARED = "two services write shipments.status"
PROMISE = "a promise with no mechanism"
NO_NUMBER = "a quality goal without a number"
CARRIERS = "carrier failure not handled"
CONTRADICTION = "events in the proposal, polling in ADR-0003"
LAYER = "one Data Service for every table"
DEFERRED = "broker deferred, its ordering relied on"

PLANTED: list[tuple[str, str, str, str]] = [
    ("D1", SYNC_CHAIN, GOALS, r"^\| Fast booking \| A booking is confirmed in under 500 ms at p95\. \|"),
    ("D1", SYNC_CHAIN, PROPOSAL, r"The response time of the Carrier APIs for a live quote is 400\u2013800 ms"),
    (
        "D1",
        SYNC_CHAIN,
        PROPOSAL,
        r"^4\. The Booking service calls the Pricing service synchronously over REST and waits",
    ),
    (
        "D1",
        SYNC_CHAIN,
        PROPOSAL,
        r"^5\. The Pricing service reads the tariff and calls the Carrier Gateway synchronously for a live quote\.$",
    ),
    ("D2", SHARED, PROPOSAL, r"^\| `shipments\.status` \| Data Service \| Tracking service, Billing service \|"),
    ("D2", SHARED, PROPOSAL, r"updates `shipments\.status` to in transit or delivered\.$"),
    ("D2", SHARED, PROPOSAL, r"the Billing service sets `shipments\.status` to invoiced\.$"),
    ("D3", PROMISE, PROPOSAL, r"^A customer is never charged twice for one booking\.$"),
    ("D3", PROMISE, PROPOSAL, r"^If the charge call times out after 2 seconds, the Booking service retries the charge"),
    (
        "D4",
        NO_NUMBER,
        GOALS,
        r"^\| Availability and scale \| The platform must be highly available and scale for peak season\. \|",
    ),
    (
        "D5",
        CARRIERS,
        PROPOSAL,
        r"^The Carrier Gateway calls the Carrier APIs of Brzopak, Kolibri Kurir and Tranzit Plus over HTTPS",
    ),
    (
        "D6",
        CONTRADICTION,
        PROPOSAL,
        r"^The Tracking service receives every status change of a shipment as an event from the message broker\.$",
    ),
    ("D6", CONTRADICTION, ADR_TRACKING, r"^\* Status: accepted$"),
    (
        "D6",
        CONTRADICTION,
        ADR_TRACKING,
        r"^The Tracking service polls the REST API of the Booking service every minute",
    ),
    ("D7", LAYER, PROPOSAL, r"^The Data Service owns every table of the platform except the tariff table"),
    ("D7", LAYER, ADR_DATA, r"^Every service reads and writes its data through the REST API of the Data Service"),
    (
        "D8",
        DEFERRED,
        PROPOSAL,
        r"relies on the message broker to deliver the events of one shipment in the order they were published\.$",
    ),
    ("D8", DEFERRED, PROPOSAL, r"^Which broker product we run is to be decided later \(ADR-0004\)\.$"),
    ("D8", DEFERRED, ADR_BROKER, r"^\* Status: proposed$"),
]

DECOYS: list[tuple[str, str, str, str]] = [
    (
        "OK1",
        "tariff cache with accepted staleness",
        PROPOSAL,
        r"^The Pricing service reads tariffs through a read-through cache that keeps each tariff for 15 minutes\.$",
    ),
    ("OK1", "tariff cache with accepted staleness", PROPOSAL, r"^The commercial team accepted this on 2026-10-29"),
    (
        "OK2",
        "Pricing has its own database",
        PROPOSAL,
        r"^The Pricing service has its own database, the Pricing database, with one table, `tariffs`\.$",
    ),
    (
        "OK3",
        "Address Validator with a budget and a fallback",
        PROPOSAL,
        r"^The Booking service calls the Address Validator synchronously with a time budget of 50 ms\.$",
    ),
    (
        "OK3",
        "Address Validator with a budget and a fallback",
        PROPOSAL,
        r"^If the Address Validator has not answered within 50 ms, the Booking service accepts the address as typed",
    ),
]

PLANTED_AT: dict[str, list[str]] = {
    "D1": [f"{GOALS}:8", f"{PROPOSAL}:126", f"{PROPOSAL}:175", f"{PROPOSAL}:176"],
    "D2": [f"{PROPOSAL}:215", f"{PROPOSAL}:186", f"{PROPOSAL}:195"],
    "D3": [f"{PROPOSAL}:200", f"{PROPOSAL}:198"],
    "D4": [f"{GOALS}:9"],
    "D5": [f"{PROPOSAL}:125"],
    "D6": [f"{PROPOSAL}:134", f"{ADR_TRACKING}:3", f"{ADR_TRACKING}:20"],
    "D7": [f"{PROPOSAL}:144", f"{ADR_DATA}:18"],
    "D8": [f"{PROPOSAL}:232", f"{PROPOSAL}:234", f"{ADR_BROKER}:3"],
}

DECOYS_AT: dict[str, list[str]] = {
    "OK1": [f"{PROPOSAL}:118", f"{PROPOSAL}:120"],
    "OK2": [f"{PROPOSAL}:115"],
    "OK3": [f"{PROPOSAL}:153", f"{PROPOSAL}:154"],
}

SERVICES: list[str] = ["Booking service", "Pricing service", "Carrier Gateway", "Tracking service", "Billing service"]
PARTS: list[str] = [
    "Web app",
    "Mobile app",
    *SERVICES,
    "Data Service",
    "Address Validator",
    "Message broker",
    "Pricing database",
    "Carrier APIs",
    "Payment provider",
]
CARRIER_QUOTE = "400\u2013800 ms"
BOOKING_GOAL = "500 ms"
ADR_STATUSES: dict[int, str] = {1: "Accepted", 2: "Accepted", 3: "Accepted", 4: "Proposed"}

HEAD = "7c061c4"
COMMITS = 4

FILES = ROOT / "fixtures" / "acme-design" / "files"
LAYOUT = [README, ADR_SERVICES, ADR_DATA, ADR_TRACKING, ADR_BROKER, PROPOSAL, GOALS]

ADDRESS = re.compile(r"[\w.+-]+@([\w-]+(?:\.[\w-]+)+)")


@pytest.fixture(scope="module")
def design_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The acme-design fixture, built once for this module. Tests must not change it."""
    target = tmp_path_factory.mktemp("fixture") / "acme-design"
    build_fixture.build("acme-design", target)
    return target


def read(repo: Path, rel: str) -> str:
    return (repo / rel).read_text(encoding="utf-8")


def every_line(repo: Path) -> list[tuple[str, str]]:
    return [(rel, line) for rel in LAYOUT for line in read(repo, rel).splitlines()]


def found_at(repo: Path, rel: str, pattern: str) -> str:
    """file:line of the one line in repo/rel that pattern matches; it must match exactly one."""
    lines = read(repo, rel).splitlines()
    hits = [number for number, line in enumerate(lines, start=1) if re.search(pattern, line)]
    assert len(hits) == 1, f"{pattern!r} matches lines {hits} of {rel}, expected exactly one"
    return f"{rel}:{hits[0]}"


def places(entries: list[tuple[str, str, str, str]]) -> list[tuple[str, int, str, str, str]]:
    """(id, index among the entries of that id, name, file, pattern) for every entry."""
    seen: dict[str, int] = {}
    result = []
    for flaw, name, rel, pattern in entries:
        index = seen.get(flaw, 0)
        seen[flaw] = index + 1
        result.append((flaw, index, name, rel, pattern))
    return result


def test_builds_deterministically_with_the_same_head(tmp_path: Path) -> None:
    heads = {build_fixture.build("acme-design", tmp_path / name) for name in ("one", "two")}
    assert heads == {HEAD}


def test_history_is_a_draft_adrs_and_a_revision_by_three_people(design_repo: Path) -> None:
    log = git(design_repo, "log", "--format=%h %s").splitlines()
    assert len(log) == COMMITS
    assert log[0].startswith(f"{HEAD} Revision 2")
    assert log[-1].endswith(" Draft the Parcel booking v2 proposal and its quality goals")
    emails = set(git(design_repo, "log", "--format=%ae").split())
    assert len(emails) == 3 and all(email.endswith("@example.com") for email in emails)
    days = git(design_repo, "log", "--format=%ad", "--date=short").split()
    assert all("2026-10-01" <= day <= "2026-11-30" for day in days)
    assert days == sorted(days, reverse=True)


def test_layout_is_documents_only_and_the_last_commit_equals_the_stored_files(design_repo: Path) -> None:
    assert sorted(git(design_repo, "ls-files").split()) == sorted(LAYOUT)
    assert all(rel.endswith(".md") for rel in LAYOUT)
    assert git(design_repo, "status", "--porcelain") == ""
    for path in FILES.rglob("*"):
        if path.is_file():
            rel = path.relative_to(FILES).as_posix()
            assert git(design_repo, "show", f"HEAD:{rel}") == path.read_text(encoding="utf-8"), rel
    assert 250 <= len(read(design_repo, PROPOSAL).splitlines()) <= 400


def test_the_ids_are_the_eight_flaws_and_three_decoys() -> None:
    assert sorted({p[0] for p in PLANTED}) == [f"D{n}" for n in range(1, 9)] == sorted(PLANTED_AT)
    assert sorted({d[0] for d in DECOYS}) == ["OK1", "OK2", "OK3"] == sorted(DECOYS_AT)
    for entries, at in ((PLANTED, PLANTED_AT), (DECOYS, DECOYS_AT)):
        for key, where in at.items():
            assert len(where) == sum(entry[0] == key for entry in entries), key


@pytest.mark.parametrize(
    ("flaw", "index", "name", "rel", "pattern"), places(PLANTED), ids=[f"{p[0]}-{p[1]}" for p in places(PLANTED)]
)
def test_planted_evidence_sits_on_its_line(
    design_repo: Path,
    record_property: Callable[[str, object], None],
    flaw: str,
    index: int,
    name: str,
    rel: str,
    pattern: str,
) -> None:
    where = found_at(design_repo, rel, pattern)
    record_property("planted", f"{flaw} {name}: {where}")
    assert where == PLANTED_AT[flaw][index]


@pytest.mark.parametrize(
    ("decoy", "index", "name", "rel", "pattern"), places(DECOYS), ids=[f"{d[0]}-{d[1]}" for d in places(DECOYS)]
)
def test_decoy_sits_on_its_line(design_repo: Path, decoy: str, index: int, name: str, rel: str, pattern: str) -> None:
    assert found_at(design_repo, rel, pattern) == DECOYS_AT[decoy][index]


def test_d1_the_numbers_to_add_up_the_booking_path_are_stated(design_repo: Path) -> None:
    proposal = read(design_repo, PROPOSAL)
    goals = read(design_repo, GOALS)
    assert f"is {CARRIER_QUOTE}" in proposal and f"under {BOOKING_GOAL} at p95" in goals
    assert (
        "from the moment the Booking service receives the booking request to the moment it sends the confirmation"
        in goals
    )
    steps = re.findall(r"^(\d)\. (.+)$", proposal.split("### 7.1 Book a parcel")[1].split("###")[0], re.MULTILINE)
    texts = [text for _, text in steps]
    assert texts.index(next(t for t in texts if "calls the Pricing service synchronously" in t)) < texts.index(
        next(t for t in texts if t.startswith("The Booking service sends the confirmation"))
    )


def test_d2_only_shipments_status_has_two_writers(design_repo: Path) -> None:
    table = read(design_repo, PROPOSAL).split("## 8. Data ownership")[1].split("##")[0]
    rows = re.findall(r"^\| `([\w.]+)` \| [^|]+ \| ([^|]+) \|", table, re.MULTILINE)
    writers = {entity: [w.strip() for w in cell.split(",")] for entity, cell in rows}
    assert writers["shipments.status"] == ["Tracking service", "Billing service"]
    assert [entity for entity, names in writers.items() if len(names) > 1] == ["shipments.status"]


def test_d3_nothing_stops_a_retried_charge_from_charging_twice(design_repo: Path) -> None:
    text = "\n".join(line for _, line in every_line(design_repo))
    assert "retries the charge" in text
    assert not re.search(r"idempot|dedup|de-dup|unique|exactly.once|charge (?:id|key)|request id", text, re.I)


def test_d4_no_number_anywhere_for_availability_scale_or_peak(design_repo: Path) -> None:
    for rel, line in every_line(design_repo):
        if re.search(r"availab|uptime|scal(?:e|ing)\b|peak|throughput", line, re.I):
            assert not re.search(r"\d|%", line), f"{rel}: {line}"


def test_d5_nothing_says_what_happens_when_a_carrier_is_slow_or_down(design_repo: Path) -> None:
    handling = re.compile(
        r"time ?outs?|timed out|fallback|retr(?:y|ies)|circuit|queue|backoff|degrad|cache|slow|down|unavailable|fail",
        re.I,
    )
    carrier_lines = [(rel, line) for rel, line in every_line(design_repo) if re.search(r"carrier", line, re.I)]
    assert len(carrier_lines) >= 10
    assert [(rel, line) for rel, line in carrier_lines if handling.search(line)] == []
    assert "Brzopak, Kolibri Kurir and Tranzit Plus" in read(design_repo, PROPOSAL)


def test_d6_the_proposal_and_the_accepted_adr_disagree(design_repo: Path) -> None:
    proposal = read(design_repo, PROPOSAL)
    adr = read(design_repo, ADR_TRACKING)
    assert "MB -.->|status events| TR" in proposal and "TR -->" in proposal
    assert "TR --> BK" not in proposal and "TR -->|REST| BK" not in proposal
    assert "Chosen option: poll the REST API of the Booking service." in adr
    assert "does not depend on the event format or on a broker" in adr
    assert "/bookings/changes" not in proposal


def test_d7_every_service_goes_through_the_data_service(design_repo: Path) -> None:
    proposal = read(design_repo, PROPOSAL)
    for node in ("BK", "PR", "CG", "TR", "BL"):
        assert f"    {node} -->|REST| DS" in proposal or f"    {node} -->|REST| DS[Data Service]" in proposal, node
    assert "The data team runs the Data Service and makes every change to it." in proposal
    assert "## Status\n\nAccepted" in read(design_repo, ADR_DATA)


def test_d8_the_broker_is_open_while_the_proposal_needs_its_order(design_repo: Path) -> None:
    adr = read(design_repo, ADR_BROKER)
    assert "To be decided later" in adr
    assert "order" not in adr.lower()
    assert "## 13. Rollout" in read(design_repo, PROPOSAL)
    assert "all services go live" in read(design_repo, PROPOSAL)


def test_the_decoys_carry_what_makes_them_fine(design_repo: Path) -> None:
    proposal = read(design_repo, PROPOSAL)
    goals = read(design_repo, GOALS)
    assert "Milan Tadin" in goals and "accepted the 15 minutes" in goals
    assert "No other service reads or writes it." in proposal
    assert "| `tariffs` | Pricing database | Pricing service | Pricing service |" in proposal
    assert "never delays a booking by more than 50 ms" in proposal


def test_only_example_addresses(design_repo: Path) -> None:
    for address in git(design_repo, "log", "--format=%ae%n%ce").split():
        assert address.endswith("@example.com"), address
    for rel in LAYOUT:
        for domain in ADDRESS.findall(read(design_repo, rel)):
            assert domain == "example.com", (rel, domain)
