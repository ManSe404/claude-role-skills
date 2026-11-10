"""The acme-churn fixture: the made-up churn project the data-scientist skills are tested and shown on.

Every constant below is checked here against the fixture itself, recomputed from the CSVs with code of this file, not
with the skills' scripts. The evals and the script tests import them, so keep them in step with the data (make_data.py
builds it).

TRAIN, TEST: rows, positives and the planted problems of the training set.
LEAK: a feature filled only for customers who churned. TIME_LEAK: a timestamp from after the snapshot.
ENTITIES, DUPLICATES: the same customers on both sides, and exact copies.
MISSING: missingness that differs by class. DRIFT: the PSI of the one feature that moved.
PREDICTIONS: ranking metrics, the calibration of each model and the slice where one model collapses.
EXPERIMENT: exact counts of both runs, and what the correction for four metrics does.
SNAPSHOTS: the table before any split, with what exploring it should find.
"""

from __future__ import annotations

import csv
import filecmp
import math
import subprocess
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import build_fixture
import pytest
from conftest import ROOT

MAKE_DATA = ROOT / "fixtures" / "acme-churn" / "make_data.py"
FILES = ROOT / "fixtures" / "acme-churn" / "files"
CSV_FILES = [
    "experiment_broken.csv",
    "experiment_clean.csv",
    "predictions.csv",
    "snapshots.csv",
    "test.csv",
    "train.csv",
]
PERSONAL_COLUMNS = ("full_name", "email", "phone")

TRAIN: dict[str, int] = {"rows": 2400, "positives": 411}
TEST: dict[str, int] = {"rows": 1000, "positives": 166}
LEAK: dict[str, Any] = {
    "column": "cancellation_reason",
    "filled_among_positives_train": 389,
    "filled_among_negatives_train": 0,
    "single_feature_strength_at_least": 0.95,
}
TIME_LEAK: dict[str, Any] = {"column": "last_login_at", "train_rows": 96, "test_rows": 40}
ENTITIES: dict[str, int] = {"customers_on_both_sides": 150, "test_rows_with_a_train_customer": 150}
DUPLICATES = 40
MISSING: dict[str, Any] = {
    "column": "nps_last",
    "missing_positive_train": 229,
    "missing_negative_train": 208,
    "positive_share": 229 / 411,
    "negative_share": 208 / (2400 - 411),
}
SNAPSHOTS: dict[str, Any] = {
    "rows": 6000,
    "positives": 665,
    "customers": 4500,
    "customers_with_several_rows": 1500,
    "before_jump_rows": 3246,
    "before_jump_positives": 332,
    "after_jump_known_rows": 1167,
    "after_jump_known_positives": 213,
    "unfinished_rows": 1587,
    "unfinished_positives": 120,
    "just_before_rows": 389,
    "just_before_positives": 74,
    "unknown_tenure_rows": 180,
    "unknown_tenure_positives": 22,
    "legacy_rows": 668,
    "legacy_positives": 113,
    "campaign_levels": 400,
    "nps_missing_rows": 928,
    "nps_missing_positives": 344,
    "highest_real_tenure": 63,
}
DRIFT: dict[str, Any] = {"column": "monthly_fee_eur", "psi_low": 0.35, "psi_high": 0.55, "stable_below": 0.1}
PREDICTIONS: dict[str, Any] = {
    "rows": 3000,
    "positives": 572,
    "baseline": "baseline_score",
    "noise_model": "logreg_v2",
    "real_model": "gbt_v7",
    "roc_auc": {"baseline_score": 0.649904, "logreg_v2": 0.660422, "gbt_v7": 0.736337},
    "pr_auc": {"baseline_score": 0.313579, "logreg_v2": 0.317451, "gbt_v7": 0.4038},
    "mean_predicted": {"baseline_score": 0.189203, "logreg_v2": 0.18972, "gbt_v7": 0.375894},
    "observed_rate": 572 / 3000,
    "bad_slice": ("plan", "legacy"),
    "bad_slice_rows": 353,
    "gbt_auc_on_bad_slice": 0.573089,
    "costs": {"false_positive": 25.0, "false_negative": 90.0},
}
EXPERIMENT: dict[str, Any] = {
    "clean_control": 3012,
    "clean_treatment": 2988,
    "clean_chi_square": 0.096,
    "broken_control": 2640,
    "broken_treatment": 2360,
    "broken_chi_square": 15.68,
    "primary": "renewed",
    "renewed_control": 1499,
    "renewed_treatment": 1570,
    "renewed_p": 0.031495,
    "renewed_holm_p": 0.12598,
    "family": ["renewed", "upgraded", "app_open_7d", "arpu_eur"],
    "guardrails": {"support_contact": 0.02, "refund_requested": 0.0075},
    "lower_is_better": ["support_contact", "refund_requested"],
    "min_effect": 0.02,
    "looks": 10,
    "planned_n_per_arm": 2900,
}


def read_csv(repo: Path, name: str) -> list[dict[str, str]]:
    with (repo / "data" / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def pairs_auc(labels: Sequence[bool], scores: Sequence[float]) -> float:
    """Every positive against every negative: slow and independent of the scripts' sweep."""
    positives = [s for s, y in zip(scores, labels, strict=True) if y]
    negatives = [s for s, y in zip(scores, labels, strict=True) if not y]
    wins = sum(1.0 if p > n else 0.5 if p == n else 0.0 for p in positives for n in negatives)
    return wins / (len(positives) * len(negatives))


def average_precision(labels: Sequence[bool], scores: Sequence[float]) -> float:
    """Average precision by walking the sorted rows, tied scores taken together; again not the scripts' code."""
    order = sorted(zip(scores, labels, strict=True), key=lambda item: -item[0])
    positives = sum(labels)
    area = 0.0
    tp = fp = 0
    index = 0
    while index < len(order):
        same = index
        new_tp = 0
        while same < len(order) and order[same][0] == order[index][0]:
            new_tp += 1 if order[same][1] else 0
            fp += 0 if order[same][1] else 1
            same += 1
        tp += new_tp
        if new_tp:
            area += new_tp * tp / (tp + fp)
        index = same
    return area / positives


def psi_of(train_values: Iterable[float], test_values: Iterable[float]) -> float:
    train = sorted(train_values)
    test = sorted(test_values)
    n = len(train)
    edges = sorted({train[min(n - 1, math.ceil(n * i / 10) - 1)] for i in range(1, 10)})

    def shares(values: list[float]) -> list[float]:
        counts = [0] * (len(edges) + 1)
        for value in values:
            position = next((i for i, edge in enumerate(edges) if value <= edge), len(edges))
            counts[position] += 1
        return [c / len(values) for c in counts]

    expected, actual = shares(train), shares(test)
    return sum(
        (max(a, 1e-4) - max(e, 1e-4)) * math.log(max(a, 1e-4) / max(e, 1e-4))
        for e, a in zip(expected, actual, strict=True)
    )


def z_two_sided(z: float) -> float:
    return math.erfc(abs(z) / math.sqrt(2))


def test_builds_deterministically(tmp_path: Path) -> None:
    heads = {build_fixture.build("acme-churn", tmp_path / name) for name in ("one", "two")}
    assert len(heads) == 1


def test_the_generator_makes_the_same_data_from_the_same_seed(tmp_path: Path) -> None:
    data = tmp_path / "data"
    subprocess.run([sys.executable, str(MAKE_DATA), str(data)], check=True, timeout=120)
    stored = ROOT / "fixtures" / "acme-churn" / "extras" / "data"
    assert sorted(p.name for p in stored.iterdir()) == CSV_FILES
    for name in CSV_FILES:
        assert filecmp.cmp(data / name, stored / name, shallow=False), name


def test_layout(churn_repo: Path) -> None:
    assert (churn_repo / "model" / "features.py").is_file()
    assert (churn_repo / "docs" / "briefs" / "retention-offers.md").is_file()
    assert (churn_repo / "docs" / "briefs" / "auto-renew-reminders.md").is_file()
    assert sorted(p.name for p in (churn_repo / "data").iterdir()) == CSV_FILES
    for rel in ("data/train.csv", "data/test.csv"):
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", rel], cwd=churn_repo, capture_output=True, check=False
        )
        assert tracked.returncode != 0, f"{rel} should not be committed"


@pytest.fixture(scope="module")
def train(churn_repo: Path) -> list[dict[str, str]]:
    return read_csv(churn_repo, "train.csv")


@pytest.fixture(scope="module")
def test_rows(churn_repo: Path) -> list[dict[str, str]]:
    return read_csv(churn_repo, "test.csv")


def churned(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [r for r in rows if r["churned_60d"] == "1"]


def test_counts_and_positive_rates(train: list[dict[str, str]], test_rows: list[dict[str, str]]) -> None:
    assert len(train) == TRAIN["rows"] and len(churned(train)) == TRAIN["positives"]
    assert len(test_rows) == TEST["rows"] and len(churned(test_rows)) == TEST["positives"]


def test_target_leak_is_only_filled_for_churners(train: list[dict[str, str]]) -> None:
    positives = churned(train)
    negatives = [r for r in train if r["churned_60d"] == "0"]
    assert sum(1 for r in positives if r[LEAK["column"]]) == LEAK["filled_among_positives_train"]
    assert sum(1 for r in negatives if r[LEAK["column"]]) == LEAK["filled_among_negatives_train"]


def test_timestamp_leak_is_after_the_snapshot(train: list[dict[str, str]], test_rows: list[dict[str, str]]) -> None:
    def later(rows: list[dict[str, str]]) -> int:
        return sum(1 for r in rows if r[TIME_LEAK["column"]][:10] > r["snapshot_date"])

    assert later(train) == TIME_LEAK["train_rows"]
    assert later(test_rows) == TIME_LEAK["test_rows"]


def test_same_customers_and_exact_copies_across_the_splits(
    train: list[dict[str, str]], test_rows: list[dict[str, str]]
) -> None:
    train_customers = {r["customer_id"] for r in train}
    test_customers = {r["customer_id"] for r in test_rows}
    assert len(train_customers & test_customers) == ENTITIES["customers_on_both_sides"]
    assert (
        sum(1 for r in test_rows if r["customer_id"] in train_customers) == ENTITIES["test_rows_with_a_train_customer"]
    )
    key = [c for c in train[0] if c != "row_id"]
    seen = {tuple(r[c] for c in key) for r in train}
    assert sum(1 for r in test_rows if tuple(r[c] for c in key) in seen) == DUPLICATES


def test_missingness_differs_by_class(train: list[dict[str, str]]) -> None:
    positives = churned(train)
    negatives = [r for r in train if r["churned_60d"] == "0"]
    assert sum(1 for r in positives if not r[MISSING["column"]]) == MISSING["missing_positive_train"]
    assert sum(1 for r in negatives if not r[MISSING["column"]]) == MISSING["missing_negative_train"]
    assert MISSING["positive_share"] - MISSING["negative_share"] > 0.4


def test_only_the_price_rise_shifts_a_feature(train: list[dict[str, str]], test_rows: list[dict[str, str]]) -> None:
    fee = psi_of((float(r[DRIFT["column"]]) for r in train), (float(r[DRIFT["column"]]) for r in test_rows))
    assert DRIFT["psi_low"] <= fee <= DRIFT["psi_high"]
    for column in ("logins_30d", "tenure_months"):
        assert psi_of((float(r[column]) for r in train), (float(r[column]) for r in test_rows)) < DRIFT["stable_below"]


@pytest.fixture(scope="module")
def predictions(churn_repo: Path) -> list[dict[str, str]]:
    return read_csv(churn_repo, "predictions.csv")


def label_list(rows: list[dict[str, str]]) -> list[bool]:
    return [r["churned_60d"] == "1" for r in rows]


def test_prediction_metrics_are_what_the_constants_say(predictions: list[dict[str, str]]) -> None:
    assert len(predictions) == PREDICTIONS["rows"]
    labels = label_list(predictions)
    assert sum(labels) == PREDICTIONS["positives"]
    for model, expected in PREDICTIONS["roc_auc"].items():
        assert pairs_auc(labels, [float(r[model]) for r in predictions]) == pytest.approx(expected, abs=1e-6)
    for model, expected in PREDICTIONS["pr_auc"].items():
        assert average_precision(labels, [float(r[model]) for r in predictions]) == pytest.approx(expected, abs=1e-6)


def test_one_model_is_badly_calibrated_and_the_others_are_not(predictions: list[dict[str, str]]) -> None:
    observed = sum(label_list(predictions)) / len(predictions)
    assert observed == pytest.approx(PREDICTIONS["observed_rate"])
    for model, expected in PREDICTIONS["mean_predicted"].items():
        mean = sum(float(r[model]) for r in predictions) / len(predictions)
        assert mean == pytest.approx(expected, abs=2e-6)
    assert PREDICTIONS["mean_predicted"]["gbt_v7"] > 1.9 * observed
    assert abs(PREDICTIONS["mean_predicted"]["baseline_score"] - observed) < 0.01


def test_one_slice_is_much_worse_for_the_real_model(predictions: list[dict[str, str]]) -> None:
    column, value = PREDICTIONS["bad_slice"]
    rows = [r for r in predictions if r[column] == value]
    assert len(rows) == PREDICTIONS["bad_slice_rows"]
    labels = label_list(rows)
    assert pairs_auc(labels, [float(r["gbt_v7"]) for r in rows]) == pytest.approx(
        PREDICTIONS["gbt_auc_on_bad_slice"], abs=1e-6
    )
    assert PREDICTIONS["gbt_auc_on_bad_slice"] < PREDICTIONS["roc_auc"]["gbt_v7"] - 0.15


@pytest.fixture(scope="module")
def clean(churn_repo: Path) -> list[dict[str, str]]:
    return read_csv(churn_repo, "experiment_clean.csv")


@pytest.fixture(scope="module")
def broken(churn_repo: Path) -> list[dict[str, str]]:
    return read_csv(churn_repo, "experiment_broken.csv")


def arm(rows: list[dict[str, str]], name: str) -> list[dict[str, str]]:
    return [r for r in rows if r["variant"] == name]


def chi_square(counts: Sequence[int]) -> float:
    half = sum(counts) / 2
    return sum((c - half) ** 2 / half for c in counts)


def test_sample_ratios(clean: list[dict[str, str]], broken: list[dict[str, str]]) -> None:
    assert len(arm(clean, "control")) == EXPERIMENT["clean_control"]
    assert len(arm(clean, "treatment")) == EXPERIMENT["clean_treatment"]
    assert chi_square((3012, 2988)) == pytest.approx(EXPERIMENT["clean_chi_square"])
    assert len(arm(broken, "control")) == EXPERIMENT["broken_control"]
    assert len(arm(broken, "treatment")) == EXPERIMENT["broken_treatment"]
    assert chi_square((2640, 2360)) == pytest.approx(EXPERIMENT["broken_chi_square"])


def test_the_primary_metric_loses_significance_after_correction(clean: list[dict[str, str]]) -> None:
    control = arm(clean, "control")
    treatment = arm(clean, "treatment")
    x_c = sum(1 for r in control if r["renewed"] == "1")
    x_t = sum(1 for r in treatment if r["renewed"] == "1")
    assert (x_c, x_t) == (EXPERIMENT["renewed_control"], EXPERIMENT["renewed_treatment"])
    p_c, p_t = x_c / len(control), x_t / len(treatment)
    pooled = (x_c + x_t) / (len(control) + len(treatment))
    z = (p_t - p_c) / math.sqrt(pooled * (1 - pooled) * (1 / len(control) + 1 / len(treatment)))
    assert z_two_sided(z) == pytest.approx(EXPERIMENT["renewed_p"], abs=1e-4)
    assert z_two_sided(z) * 4 == pytest.approx(EXPERIMENT["renewed_holm_p"], abs=4e-4)


def test_personal_columns_are_present_and_fictional(churn_repo: Path, train: list[dict[str, str]]) -> None:
    for column in PERSONAL_COLUMNS:
        assert column in train[0]
    assert all(r["email"].endswith("@example.com") for r in train)
    assert all("555" in r["phone"] for r in train)
    all_text = "\n".join(p.read_text("utf-8") for p in FILES.rglob("*") if p.is_file())
    for row in train[:50]:
        assert row["email"] not in all_text and row["full_name"] not in all_text


# ---------------------------------------------------------------------------- snapshots.csv, before any split


@pytest.fixture(scope="module")
def snapshots(churn_repo: Path) -> list[dict[str, str]]:
    return read_csv(churn_repo, "snapshots.csv")


def count(rows: list[dict[str, str]]) -> tuple[int, int]:
    return len(rows), sum(1 for r in rows if r["churned_60d"] == "1")


def test_snapshot_counts_and_customers(snapshots: list[dict[str, str]]) -> None:
    assert count(snapshots) == (SNAPSHOTS["rows"], SNAPSHOTS["positives"])
    per_customer: dict[str, int] = {}
    for row in snapshots:
        per_customer[row["customer_id"]] = per_customer.get(row["customer_id"], 0) + 1
    assert len(per_customer) == SNAPSHOTS["customers"]
    assert sum(1 for n in per_customer.values() if n > 1) == SNAPSHOTS["customers_with_several_rows"]


def test_snapshot_rate_jumps_and_the_newest_labels_are_not_in(snapshots: list[dict[str, str]]) -> None:
    before = [r for r in snapshots if r["snapshot_date"] < "2025-11-01"]
    after = [r for r in snapshots if "2025-11-01" <= r["snapshot_date"] <= "2026-01-31"]
    newest = [r for r in snapshots if r["snapshot_date"] > "2026-01-31"]
    just_before = [r for r in snapshots if "2025-12-02" <= r["snapshot_date"] <= "2026-01-31"]
    assert count(before) == (SNAPSHOTS["before_jump_rows"], SNAPSHOTS["before_jump_positives"])
    assert count(after) == (SNAPSHOTS["after_jump_known_rows"], SNAPSHOTS["after_jump_known_positives"])
    assert count(newest) == (SNAPSHOTS["unfinished_rows"], SNAPSHOTS["unfinished_positives"])
    assert count(just_before) == (SNAPSHOTS["just_before_rows"], SNAPSHOTS["just_before_positives"])


def test_snapshot_unknown_tenure_is_a_code(snapshots: list[dict[str, str]]) -> None:
    coded = [r for r in snapshots if r["tenure_months"] == "999"]
    assert count(coded) == (SNAPSHOTS["unknown_tenure_rows"], SNAPSHOTS["unknown_tenure_positives"])
    assert (
        max(int(r["tenure_months"]) for r in snapshots if r["tenure_months"] != "999")
        == SNAPSHOTS["highest_real_tenure"]
    )


def test_snapshot_session_length_relates_to_churn_in_a_u(snapshots: list[dict[str, str]]) -> None:
    known = [r for r in snapshots if r["snapshot_date"] <= "2026-01-31"]
    ordered = sorted(known, key=lambda r: float(r["avg_session_min"]))
    fifth = len(ordered) // 5

    def rate(part: list[dict[str, str]]) -> float:
        return sum(1 for r in part if r["churned_60d"] == "1") / len(part)

    middle = rate(ordered[2 * fifth : 3 * fifth])
    assert rate(ordered[:fifth]) > 2 * middle
    assert rate(ordered[-fifth:]) > 2 * middle


def test_snapshot_leak_filled_only_for_churners(snapshots: list[dict[str, str]]) -> None:
    filled = [r for r in snapshots if r["retention_call_outcome"]]
    assert count(filled) == (SNAPSHOTS["positives"], SNAPSHOTS["positives"])


def test_snapshot_a_repeat_customer_is_the_same_customer_later(snapshots: list[dict[str, str]]) -> None:
    by_customer: dict[str, list[dict[str, str]]] = {}
    for row in snapshots:
        by_customer.setdefault(row["customer_id"], []).append(row)
    repeats = [sorted(rows, key=lambda r: r["snapshot_date"]) for rows in by_customer.values() if len(rows) > 1]
    assert len(repeats) == SNAPSHOTS["customers_with_several_rows"]
    for first, second in repeats:
        assert first["snapshot_date"] < second["snapshot_date"]
        assert (first["plan"], first["region"], first["email"]) == (second["plan"], second["region"], second["email"])
        assert first["churned_60d"] == "0", "nobody is seen again after churning"


def test_snapshot_annual_fee_repeats_the_monthly_fee(snapshots: list[dict[str, str]]) -> None:
    for row in snapshots:
        assert float(row["annual_fee_eur"]) == pytest.approx(float(row["monthly_fee_eur"]) * 12, abs=0.01)


def test_snapshot_segments_levels_and_missing(snapshots: list[dict[str, str]]) -> None:
    legacy = [r for r in snapshots if r["plan"] == "legacy"]
    assert count(legacy) == (SNAPSHOTS["legacy_rows"], SNAPSHOTS["legacy_positives"])
    assert len({r["campaign_code"] for r in snapshots}) == SNAPSHOTS["campaign_levels"]
    missing = [r for r in snapshots if not r["nps_last"]]
    assert count(missing) == (SNAPSHOTS["nps_missing_rows"], SNAPSHOTS["nps_missing_positives"])
