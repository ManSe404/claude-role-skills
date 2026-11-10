"""The incident timeline script, on the acme-orders log and on logs written for one case each."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from conftest import SKILLS, load, run_json

TIMELINE = SKILLS / "incident-triage" / "scripts" / "incident_timeline.py"
timeline = load(TIMELINE)


@pytest.fixture(scope="module")
def orders(acme: Path) -> dict[str, Any]:
    result: dict[str, Any] = run_json(
        TIMELINE,
        str(acme / "logs" / "acme-orders.log"),
        "--repo",
        str(acme),
        "--detected",
        "2026-10-02T09:30:00+02:00",
        "--mitigated",
        "2026-10-03T10:00:00+02:00",
    )
    return result


def test_first_error_and_its_trace(orders: dict[str, Any]) -> None:
    assert orders["entries"] == 13 and orders["levels"] == {"INFO": 11, "ERROR": 2}
    first = orders["first_error"]
    assert first["time"] == "2026-10-02T06:00:01+02:00" and first["where"] == "acme-orders.log:10"
    assert first["signature"] == "cron acme-orders import exited with N" and first["component"] == "cron"
    assert first["traceback_tail"][-1] == {
        "file": "/srv/acme-orders/src/acme_orders/importer.py",
        "line": 28,
        "function": "parse_amount",
    }
    assert orders["last_normal_before"]["time"] == "2026-10-01T18:05:44+02:00"


def test_runs_deploys_and_version_changes(orders: dict[str, Any]) -> None:
    assert [r["outcome"] for r in orders["runs"]] == ["ok", "ok", "error", "error"]
    assert [(d["kind"], d["ref"]) for d in orders["deploys"]] == [("deploy", "c376ea1")]
    (change,) = orders["version_changes"]
    assert (change["from"], change["to"], change["time"]) == ("d22ee8f", "c376ea1", "2026-10-02T06:00:01+02:00")


def test_changes_before_the_first_error_name_commits_without_authors(orders: dict[str, Any]) -> None:
    changes = orders["changes_before_first_error"]
    assert changes["window_hours"] == 72
    assert [c["hash"] for c in changes["commits"]] == ["c376ea1", "49bc16d"]
    assert all(set(c) == {"hash", "date", "message"} for c in changes["commits"])
    assert [d["ref"] for d in changes["deploys"]] == ["c376ea1"]


def test_errors_are_counted_by_signature_and_day(orders: dict[str, Any]) -> None:
    errors = orders["errors"]
    assert errors["total"] == 2 and errors["by_component"] == {"cron": 2}
    (sig,) = errors["by_signature"]
    assert sig["count"] == 2 and sig["first"] < sig["last"]
    assert [(d["day"], d["errors"]) for d in errors["per_day"]] == [
        ("2026-09-30", 0),
        ("2026-10-01", 0),
        ("2026-10-02", 1),
        ("2026-10-03", 1),
    ]
    assert errors["per_minute_before"] == 0.0 and errors["per_minute_after"] > 0
    assert orders["ids"] == {"emails": 0, "order_like_ids": 0, "ip_addresses": 0}


def test_phases_and_the_timeline(orders: dict[str, Any]) -> None:
    phases = orders["phases"]
    assert (
        phases["minutes_to_detect"] == 210.0
        and phases["minutes_to_mitigate"] == 1470.0
        and phases["minutes_to_resolve"] is None
    )
    assert phases["errors_before_detection"] == 1 and phases["errors_after_mitigation"] == 0
    kinds = [t["kind"] for t in orders["timeline"]]
    assert kinds == ["deploy", "version_change", "first_error", "detected", "mitigated"]
    assert orders["timeline"][0]["time"] <= orders["timeline"][1]["time"]


def test_signature_hides_values() -> None:
    sig = timeline.signature(
        "order A-1045 for mia.k@example.com failed at /srv/data/x.csv: 'bad' id 3f2c1aa7 ip 10.0.0.7"
    )
    assert "@" not in sig and "A-1045" not in sig and "10.0.0.7" not in sig and "3f2c1aa7" not in sig
    assert sig == "order <id> for <email> failed at <path>: <text> id <hex> ip <ip>"


def test_personal_values_in_errors_are_counts_not_text(tmp_path: Path) -> None:
    log = tmp_path / "app.log"
    log.write_text(
        "2026-11-01T10:00:00Z INFO api started\n"
        "2026-11-01T10:05:00Z ERROR api receipt for ana.k@example.com failed, order A-77, from 10.1.2.3\n"
        "2026-11-01T10:06:00Z ERROR api receipt for bo.l@example.com failed, order A-78, from 10.1.2.3\n"
    )
    out = run_json(TIMELINE, str(log))
    text = json.dumps(out)
    assert "ana.k" not in text and "A-77" not in text and "10.1.2.3" not in text
    assert out["ids"] == {"emails": 2, "order_like_ids": 2, "ip_addresses": 1}
    assert out["errors"]["by_signature"][0]["count"] == 2


def test_syslog_lines_and_a_python_exception_without_a_level(tmp_path: Path) -> None:
    log = tmp_path / "worker.log"
    log.write_text(
        "Oct  2 06:00:01 host worker[12]: start job 7\n"
        "Oct  2 06:00:02 host worker[12]: Traceback (most recent call last):\n"
        '  File "/srv/w.py", line 9, in run\n'
        "    boom()\n"
        "ValueError: no good\n"
        "Oct  2 06:10:00 host worker[12]: start job 8\n"
        "Oct  2 06:10:01 host worker[12]: done job 8\n"
    )
    out = run_json(TIMELINE, str(log))
    assert out["first_error"]["exception"] == "ValueError: no good"
    assert out["first_error"]["traceback_tail"] == [{"file": "/srv/w.py", "line": 9, "function": "run"}]
    assert [r["outcome"] for r in out["runs"]] == ["error", "ok"]
    assert [t["kind"] for t in out["timeline"]] == ["first_error", "working_again"]


def test_no_error_in_the_window_is_said_plainly(tmp_path: Path) -> None:
    log = tmp_path / "quiet.log"
    log.write_text("2026-11-01T10:00:00Z INFO api started\n2026-11-01T10:05:00Z INFO api deploy 1.4.2\n")
    out = run_json(TIMELINE, str(log))
    assert out["first_error"] is None and out["errors"] == {"total": 0} and "No entry at ERROR" in out["note"]
    assert [t["text"] for t in out["timeline"]] == ["deploy 1.4.2"]


def test_since_and_until_cut_the_window(acme: Path) -> None:
    log = str(acme / "logs" / "acme-orders.log")
    out = run_json(TIMELINE, log, "--since", "2026-10-03T00:00:00+02:00")
    assert out["entries"] == 3 and out["first_error"]["time"] == "2026-10-03T06:00:01+02:00"
    out = run_json(TIMELINE, log, "--until", "2026-10-01T23:59:59+02:00")
    assert out["first_error"] is None


def test_a_folder_of_logs_is_read_in_order(tmp_path: Path) -> None:
    folder = tmp_path / "logs"
    folder.mkdir()
    (folder / "b.log").write_text("2026-11-01T11:00:00Z ERROR api second\n")
    (folder / "a.log").write_text("2026-11-01T10:00:00Z ERROR api first\n")
    out = run_json(TIMELINE, str(folder))
    assert [f["path"] for f in out["files"]] == ["a.log", "b.log"] and out["first_error"]["where"] == "a.log:1"


def test_a_bad_time_or_a_missing_file_exits_2(tmp_path: Path) -> None:
    log = tmp_path / "x.log"
    log.write_text("2026-11-01T10:00:00Z INFO ok\n")
    done = subprocess.run(
        ["python3", str(TIMELINE), str(log), "--detected", "yesterday"], capture_output=True, text=True, check=False
    )
    assert done.returncode == 2 and "--detected" in done.stderr
    done = subprocess.run(
        ["python3", str(TIMELINE), str(tmp_path / "missing.log")], capture_output=True, text=True, check=False
    )
    assert done.returncode == 2
