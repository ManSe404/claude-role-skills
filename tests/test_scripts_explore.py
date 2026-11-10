"""ds-explore: small cases worked out by hand, and what the script finds in the acme-churn snapshots."""

from __future__ import annotations

import csv
import json
import random
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from conftest import ROOT, load, run_json
from test_fixture_acme_churn import PERSONAL_COLUMNS, SNAPSHOTS, read_csv

SCRIPT = ROOT / "plugins" / "data-scientist" / "skills" / "ds-explore" / "scripts" / "explore_target.py"
explore = load(SCRIPT)
FULL = ["--label", "churned_60d", "--id", "snapshot_id", "--entity", "customer_id"]
TIMED = [*FULL, "--time", "snapshot_date", "--horizon-days", "60"]


def write(path: Path, rows: list[dict[str, Any]]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def explore_rows(tmp_path: Path, rows: list[dict[str, Any]], *args: str) -> dict[str, Any]:
    result: dict[str, Any] = run_json(SCRIPT, "--data", str(write(tmp_path / "t.csv", rows)), "--label", "y", *args)
    return result


def feature(result: dict[str, Any], name: str) -> dict[str, Any]:
    found: dict[str, Any] = next(f for f in result["features"] if f["feature"] == name)
    return found


# ---------------------------------------------------------------------------- statistics by hand


def test_chi_square_by_hand() -> None:
    # 2x2: a=10 b=90 c=30 d=70, n=200 -> n(ad-bc)^2 / (r1 r2 c1 c2) = 200 * 2000^2 / (100 * 100 * 40 * 160) = 12.5.
    statistic, degrees, p_value = explore.chi_square([(10, 100), (30, 100)])
    assert statistic == pytest.approx(12.5)
    assert degrees == 1
    assert p_value == pytest.approx(0.000406, abs=1e-6)


def test_chi_square_needs_two_groups_and_two_classes() -> None:
    assert explore.chi_square([(10, 100)])[2] is None
    assert explore.chi_square([(0, 100), (0, 50)])[2] is None


def test_merge_small_pools_groups_that_cannot_be_tested() -> None:
    # At a base rate of 0.1 a group needs 50 rows for an expected count of 5.
    assert explore.merge_small([(10, 100), (1, 30), (2, 30)], 0.1) == [(10, 100), (3, 60)]
    # A pool still too small joins the smallest group that can be tested.
    assert explore.merge_small([(10, 100), (20, 200), (1, 10)], 0.1) == [(11, 110), (20, 200)]
    assert explore.merge_small([(1, 10), (1, 10)], 0.1) == [(2, 20)]


def test_rank_test_by_hand() -> None:
    # Perfect separation of 3 and 3: U - mean = 4.5, variance 3*3/12*7 = 5.25, z = 1.96396, p = 0.04953.
    assert explore.rank_test([True] * 3 + [False] * 3, [4.0, 5.0, 6.0, 1.0, 2.0, 3.0], 1.0) == pytest.approx(
        0.049535, abs=1e-5
    )


def test_rank_test_with_ties_shrinks_the_variance() -> None:
    labels = [True, True, False, False]
    # All values tied: no information at all.
    assert explore.rank_test(labels, [1.0, 1.0, 1.0, 1.0], 0.5) is None
    # Ties (1,1) (2,2): sum(t^3-t) = 12; variance 4/12 * (5 - 12/12) = 4/3; AUC 1, U-mean = 2; z = 1.732, p = 0.08326.
    assert explore.rank_test(labels, [2.0, 2.0, 1.0, 1.0], 1.0) == pytest.approx(0.08326, abs=1e-4)


def test_average_ranks_share_ties() -> None:
    assert explore.average_ranks([10.0, 20.0, 20.0, 30.0]) == [1.0, 2.5, 2.5, 4.0]


def test_spearman_by_hand() -> None:
    # d = 0,1,1,0: 1 - 6*2 / (4*15) = 0.8.
    assert explore.spearman([1.0, 2.0, 3.0, 4.0], [1.0, 3.0, 2.0, 4.0]) == pytest.approx(0.8)


def test_spearman_uses_only_rows_where_both_are_present() -> None:
    assert explore.spearman([1.0, None, 3.0, 4.0], [1.0, 9.0, 3.0, 4.0]) == pytest.approx(1.0)


def test_cramers_v_by_hand() -> None:
    # [[30,10],[10,30]]: chi-square 80 * 800^2 / 40^4 = 20; V = sqrt(20 / 80) = 0.5.
    a = ["x"] * 40 + ["y"] * 40
    b = ["p"] * 30 + ["q"] * 10 + ["p"] * 10 + ["q"] * 30
    assert explore.cramers_v(a, b) == pytest.approx(0.5)
    assert explore.cramers_v(["x", "x", "y", "y"], ["p", "p", "q", "q"]) == pytest.approx(1.0)


def test_correlation_ratio_by_hand() -> None:
    assert explore.correlation_ratio(["a", "a", "b", "b"], [1.0, 1.0, 3.0, 3.0]) == pytest.approx(1.0)
    # Ranks of 1, 2, 3, 4 in groups (1,2) and (3,4): means 1.5 and 3.5 around 2.5; between 4, total 5; eta = sqrt(.8).
    assert explore.correlation_ratio(["a", "a", "b", "b"], [1.0, 2.0, 3.0, 4.0]) == pytest.approx(0.8**0.5)


def test_skewness_by_hand() -> None:
    # 0,0,0,4: mean 1, m2 = 3, m3 = 6, skew = 6 / 3^1.5 = 1.1547.
    assert explore.skewness([0.0, 0.0, 0.0, 4.0]) == pytest.approx(1.1547, abs=1e-4)


# ---------------------------------------------------------------------------- codes for unknown


def test_a_spike_far_above_the_rest_is_a_code() -> None:
    assert explore.find_sentinels([float(v % 60 + 1) for v in range(1000)] + [999.0] * 30) == [999.0]


def test_the_only_negative_value_is_a_code() -> None:
    assert explore.find_sentinels([float(v % 60) for v in range(1000)] + [-1.0] * 30) == [-1.0]


def test_a_cap_is_not_a_code() -> None:
    # Many rows at the maximum, but no gap below it.
    assert explore.find_sentinels([float(v % 100) for v in range(1000)] + [100.0] * 200) == []


def test_a_natural_tail_is_not_a_code() -> None:
    assert explore.find_sentinels([1.0] * 500 + [2.0] * 200 + [3.0] * 100 + [50.0]) == []


def test_ordinary_negative_values_are_not_a_code() -> None:
    assert explore.find_sentinels([float(v % 21 - 10) for v in range(1000)]) == []


def test_a_code_is_taken_out_of_the_distribution_and_reported(tmp_path: Path) -> None:
    rows = [{"y": int(i % 5 == 0), "x": 999 if i % 25 == 0 else (i % 50) + 1} for i in range(2500)]
    found = feature(explore_rows(tmp_path, rows), "x")
    assert found["sentinels"][0]["value"] == 999
    assert found["sentinels"][0]["rows"] == 100
    assert found["summary"]["max"] == 50, "the code must not set the distribution"
    assert "(code 999)" in [b["from"] for b in found["bins"]]


# ---------------------------------------------------------------------------- shapes and signal


def shaped_rows(rate_of: Any, n: int = 3000) -> list[dict[str, Any]]:
    """x runs 0 to 99; y is 1 in exactly the share `rate_of(x)` of each x's rows, so chance plays no part."""
    rows: list[dict[str, Any]] = []
    for x in range(100):
        members = n // 100
        positives = round(rate_of(x) * members)
        rows += [{"y": int(i < positives), "x": x} for i in range(members)]
    return rows


def test_a_rising_relation(tmp_path: Path) -> None:
    found = feature(explore_rows(tmp_path, shaped_rows(lambda x: 0.05 + 0.5 * x / 100)), "x")
    assert found["shape"] == "rising"
    assert found["higher_means_more_positive"] is True
    assert found["signal"] is True
    assert found["via"] == "rank of the values"


def test_a_falling_relation(tmp_path: Path) -> None:
    assert feature(explore_rows(tmp_path, shaped_rows(lambda x: 0.55 - 0.5 * x / 100)), "x")["shape"] == "falling"


def test_a_u_shape_is_not_monotone_and_ranks_do_not_see_it(tmp_path: Path) -> None:
    found = feature(explore_rows(tmp_path, shaped_rows(lambda x: 0.05 + 0.5 * ((x - 49.5) / 49.5) ** 2)), "x")
    assert found["shape"] == "not monotone"
    assert found["signal"] is True
    assert found["rank_strength"] < 0.52
    assert found["binned_strength"] > 0.6
    assert "not monotone" in found["flags"]


def test_no_relation_has_no_signal_and_no_shape(tmp_path: Path) -> None:
    found = feature(explore_rows(tmp_path, shaped_rows(lambda _: 0.2)), "x")
    assert found["signal"] is False
    assert found["shape"] == "flat"


def test_presence_alone_can_be_the_relation(tmp_path: Path) -> None:
    rows = [{"y": int(i % 2 == 0), "x": "" if i % 2 == 0 and i % 8 else (i * 37) % 91} for i in range(2000)]
    found = feature(explore_rows(tmp_path, rows), "x")
    assert found["via"] == "whether the value is present at all"
    assert found["signal"] is True


def test_correction_counts_every_feature(tmp_path: Path) -> None:
    """A modest p-value survives alone and does not survive among ten columns of noise."""
    rows = [{"y": int(i < 116), "x0": "a"} for i in range(400)] + [{"y": int(i < 84), "x0": "b"} for i in range(400)]
    alone = feature(explore_rows(tmp_path, rows), "x0")
    # a=116 b=284 c=84 d=316, n=800: 800 * 12800^2 / (400 * 400 * 200 * 600) = 6.8267.
    assert alone["chi_square"] == pytest.approx(6.8267, abs=1e-3)
    assert alone["signal"] is True
    rng = random.Random(5)
    wider = [{**row, **{f"n{k}": int(rng.random() * 2) for k in range(10)}} for row in rows]
    found = feature(explore_rows(tmp_path, wider), "x0")
    assert found["p_value"] == alone["p_value"]
    assert found["adjusted_p"] > 0.05
    assert found["signal"] is False


def test_the_same_seed_gives_the_same_output(tmp_path: Path) -> None:
    rows = shaped_rows(lambda x: 0.1 + x / 300)
    assert explore_rows(tmp_path, rows, "--seed", "3") == explore_rows(tmp_path, rows, "--seed", "3")


def test_resampling_moves_a_whole_entity(tmp_path: Path) -> None:
    """The same rows repeated for each entity carry less information, so the interval must widen."""
    base = [{"y": int(i % 3 == 0), "x": (i % 3 == 0) * 2 + (i % 7), "c": i} for i in range(300)]
    repeated = [{**row, "c": row["c"]} for row in base for _ in range(10)]
    by_row = feature(explore_rows(tmp_path, repeated), "x")["interval"]
    by_entity = feature(explore_rows(tmp_path, repeated, "--entity", "c"), "x")["interval"]
    assert by_entity[1] - by_entity[0] > 2 * (by_row[1] - by_row[0])


# ---------------------------------------------------------------------------- the target and the time


def test_unfinished_labels_are_flagged_and_left_out_of_whether_the_rate_moves(tmp_path: Path) -> None:
    rows: list[dict[str, Any]] = []
    for month in range(1, 7):
        for i in range(400):
            rate = 0.02 if month >= 5 else 0.2
            rows.append({"y": int(i < 400 * rate), "when": f"2026-0{month}-01", "x": i % 9})
    result = explore_rows(tmp_path, rows, "--time", "when", "--horizon-days", "60")
    labels = result["over_time"]["labels"]
    assert labels["assumes_extract_on"] == "2026-06-01"
    assert labels["last_fully_known_date"] == "2026-04-02"
    assert labels["looks_unfinished"] is True
    assert labels["rows_not_yet_known"] == 800
    assert result["over_time"]["moves"] is False, "unfinished months are not a change in the rate"
    assert any(p["check"] == "labels not known yet" for p in result["problems"])


def test_a_real_change_in_the_rate_is_reported(tmp_path: Path) -> None:
    rows = [
        {"y": int(i < (40 if month <= 3 else 160)), "when": f"2026-0{month}-01", "x": i % 9}
        for month in range(1, 7)
        for i in range(400)
    ]
    time = explore_rows(tmp_path, rows, "--time", "when")["over_time"]
    assert time["moves"] is True
    assert (time["lowest_rate"], time["highest_rate"]) == (0.1, 0.4)


def test_periods_can_be_weeks(tmp_path: Path) -> None:
    rows = [{"y": i % 2, "when": "2026-01-05", "x": i % 9} for i in range(50)]
    assert explore_rows(tmp_path, rows, "--time", "when", "--period", "week")["over_time"]["periods"][0]["period"] == (
        "2026-W02"
    )


def test_horizon_needs_a_time_column(tmp_path: Path) -> None:
    path = write(tmp_path / "t.csv", [{"y": 1, "x": 1}, {"y": 0, "x": 2}])
    done = subprocess.run(
        [sys.executable, str(SCRIPT), "--data", str(path), "--label", "y", "--horizon-days", "30"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode != 0
    assert "--horizon-days needs --time" in done.stderr


def refused(tmp_path: Path, rows: list[dict[str, Any]], *args: str) -> str:
    path = write(tmp_path / "t.csv", rows)
    done = subprocess.run(
        [sys.executable, str(SCRIPT), "--data", str(path), "--label", "y", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode != 0
    return done.stderr


def test_a_numeric_target_is_refused_with_a_reason(tmp_path: Path) -> None:
    assert "does not read as yes/no" in refused(tmp_path, [{"y": 3.5 + i, "x": i} for i in range(20)])


def test_a_target_with_one_class_is_refused(tmp_path: Path) -> None:
    assert "only one class" in refused(tmp_path, [{"y": 1, "x": i} for i in range(20)])


def test_a_named_positive_value_is_read(tmp_path: Path) -> None:
    rows = [{"y": "left" if i % 4 == 0 else "stayed", "x": i % 9} for i in range(100)]
    assert explore_rows(tmp_path, rows, "--positive", "left")["target"]["positives"] == 25


# ---------------------------------------------------------------------------- what is printed and what is not


def test_personal_columns_are_named_and_never_used(tmp_path: Path) -> None:
    rows = [{"y": i % 2, "email": f"person{i}@example.com", "full_name": f"Name {i}", "x": i % 9} for i in range(60)]
    result = explore_rows(tmp_path, rows)
    assert set(result["personal_columns"]) == {"email", "full_name"}
    text = json.dumps(result)
    assert "example.com" not in text
    assert "Name 3" not in text
    assert [f["feature"] for f in result["features"]] == ["x"]


def test_levels_of_a_column_about_people_are_numbered(tmp_path: Path) -> None:
    rows = [{"y": int(i % 3 == 0), "account_manager": ["Zora Zoric", "Ilija Ilic"][i % 2]} for i in range(120)]
    result = explore_rows(tmp_path, rows)
    assert "Zora" not in json.dumps(result)
    assert "Ilija" not in json.dumps(result)
    assert feature(result, "account_manager")["levels"][0]["level"] == "level 1"
    assert "level_names_hidden" in feature(result, "account_manager")


def test_levels_of_a_column_with_many_values_are_not_printed(tmp_path: Path) -> None:
    rows = [{"y": i % 2, "note": f"free text {i % 40}"} for i in range(800)]
    found = feature(explore_rows(tmp_path, rows), "note")
    assert found["levels"] == []
    assert "high cardinality" in found["flags"]


def test_an_id_like_column_is_not_analysed(tmp_path: Path) -> None:
    rows = [{"y": i % 2, "ref": f"ref-{i}", "x": i % 9} for i in range(400)]
    result = explore_rows(tmp_path, rows)
    assert {"column": "ref", "why": "id-like"} in result["not_used"]


def test_excluded_and_role_columns_are_not_features(tmp_path: Path) -> None:
    rows = [{"y": i % 2, "a": i % 7, "b": i % 5, "k": i, "when": "2026-01-01"} for i in range(100)]
    result = explore_rows(tmp_path, rows, "--exclude", "b", "--id", "k", "--time", "when")
    assert [f["feature"] for f in result["features"]] == ["a"]


# ---------------------------------------------------------------------------- flags


def test_a_level_with_one_class_only_is_flagged_for_few_levels(tmp_path: Path) -> None:
    rows = [{"y": int(i % 4 == 0), "c": "a" if i % 4 == 0 else ("b" if i % 2 else "d")} for i in range(400)]
    assert "a level with one class only" in feature(explore_rows(tmp_path, rows), "c")["flags"]


def test_near_constant_and_rare_levels(tmp_path: Path) -> None:
    rows = [{"y": i % 2, "flag": int(i == 7)} for i in range(500)]
    assert "near constant" in feature(explore_rows(tmp_path, rows), "flag")["flags"]


def test_redundant_numbers_and_a_number_fixed_by_a_category(tmp_path: Path) -> None:
    rows = [
        {
            "y": i % 2,
            "monthly": (i % 40) + 1,
            "yearly": ((i % 40) + 1) * 12,
            "tier": ["a", "b", "c"][(i % 40) // 14],
            "other": (i * 17) % 23,
        }
        for i in range(1200)
    ]
    pairs = {(p["a"], p["b"]) for p in explore_rows(tmp_path, rows)["redundant"]}
    assert {tuple(sorted(pair)) for pair in pairs} >= {("monthly", "yearly")}
    assert not any("other" in pair for pair in pairs)


def test_a_segment_must_survive_correction_and_be_large_enough(tmp_path: Path) -> None:
    rows = [
        {
            "y": int((i % 10 < 4) if i % 4 == 0 else (i % 10 == 0)),
            "plan": "old" if i % 4 == 0 else ("x" if i % 2 else "z"),
        }
        for i in range(2000)
    ]
    segments = explore_rows(tmp_path, rows)["segments"]
    old = next(s for s in segments if s["level"] == "old")
    assert old["differs"] is True
    assert old["rate"] == 0.4
    small = [{"y": int(i < 5), "c": "tiny" if i < 5 else "big"} for i in range(400)]
    assert not any(s["level"] == "tiny" for s in explore_rows(tmp_path, small)["segments"])


def test_a_column_filled_for_one_class_is_a_leak_suspect_and_reported_once(tmp_path: Path) -> None:
    rows = [{"y": int(i % 4 == 0), "reason": "too dear" if i % 4 == 0 else "", "x": i % 9} for i in range(400)]
    result = explore_rows(tmp_path, rows)
    suspect = next(s for s in result["leak_suspects"] if s["feature"] == "reason")
    assert any(r.startswith("filled only when the target is yes") for r in suspect["reasons"])
    about = [p for p in result["problems"] if "reason" in p["columns"]]
    assert [p["check"] for p in about] == ["check for leakage"]
    assert not any(s["feature"] == "reason" for s in result["segments"])


def test_a_column_with_one_value_and_blanks_is_not_constant(tmp_path: Path) -> None:
    """Regression: a single value filled for one class looked constant and the leak was never reported."""
    rows = [{"y": int(i % 4 == 0), "called": "Y" if i % 4 == 0 else ""} for i in range(400)]
    result = explore_rows(tmp_path, rows)
    assert feature(result, "called")["strength"] == 1.0
    assert result["not_used"] == []
    full = [{"y": i % 2, "called": "Y"} for i in range(40)]
    assert explore_rows(tmp_path, full)["not_used"] == [{"column": "called", "why": "constant"}]


def test_a_date_after_the_prediction_moment_is_a_leak_suspect(tmp_path: Path) -> None:
    rows = [
        {"y": i % 2, "seen": "2026-02-10" if i % 5 == 0 else "2026-01-20", "when": "2026-02-01"} for i in range(200)
    ]
    suspect = explore_rows(tmp_path, rows, "--time", "when")["leak_suspects"][0]
    assert suspect["feature"] == "seen"
    assert suspect["reasons"] == ["dated after the prediction moment on 40 rows"]


def test_entities_with_several_rows_are_counted(tmp_path: Path) -> None:
    rows = [{"y": i % 2, "who": i % 30, "x": i % 9} for i in range(45)]
    entities = explore_rows(tmp_path, rows, "--entity", "who")["entities"]
    assert entities["entities"] == 30
    assert entities["entities_with_several_rows"] == 15
    assert entities["rows_of_those_entities"] == 30
    assert entities["most_rows_for_one_entity"] == 2


# ---------------------------------------------------------------------------- the acme-churn snapshots


@pytest.fixture(scope="module")
def snapshots(churn_repo: Path) -> dict[str, Any]:
    result: dict[str, Any] = run_json(SCRIPT, "--data", str(churn_repo / "data" / "snapshots.csv"), *TIMED)
    return result


def problem_columns(result: dict[str, Any], check: str) -> set[str]:
    return {c for p in result["problems"] if p["check"] == check for c in p["columns"]}


def test_snapshot_counts(snapshots: dict[str, Any]) -> None:
    assert snapshots["target"]["rows"] == SNAPSHOTS["rows"]
    assert snapshots["target"]["positives"] == SNAPSHOTS["positives"]
    assert snapshots["entities"]["entities"] == SNAPSHOTS["customers"]
    assert snapshots["entities"]["entities_with_several_rows"] == SNAPSHOTS["customers_with_several_rows"]


def test_snapshot_rate_jump_and_unfinished_labels(snapshots: dict[str, Any]) -> None:
    time = snapshots["over_time"]
    assert time["moves"] is True
    labels = time["labels"]
    assert labels["rows_not_yet_known"] == SNAPSHOTS["unfinished_rows"]
    assert labels["rate_not_yet_known"] == pytest.approx(
        SNAPSHOTS["unfinished_positives"] / SNAPSHOTS["unfinished_rows"], abs=1e-4
    )
    assert labels["rows_just_before"] == SNAPSHOTS["just_before_rows"]
    assert labels["looks_unfinished"] is True


def test_snapshot_code_for_unknown(snapshots: dict[str, Any]) -> None:
    code = feature(snapshots, "tenure_months")["sentinels"][0]
    assert (code["value"], code["rows"], code["positives"]) == (
        999,
        SNAPSHOTS["unknown_tenure_rows"],
        SNAPSHOTS["unknown_tenure_positives"],
    )


def test_snapshot_u_shape(snapshots: dict[str, Any]) -> None:
    found = feature(snapshots, "avg_session_min")
    assert found["shape"] == "not monotone"
    assert found["rank_strength"] < 0.53
    assert found["binned_strength"] > 0.62


def test_snapshot_real_features_and_noise(snapshots: dict[str, Any]) -> None:
    assert feature(snapshots, "logins_30d")["shape"] == "falling"
    assert feature(snapshots, "tickets_90d")["shape"] == "rising"
    for name in ("region", "account_manager", "discount_pct"):
        assert feature(snapshots, name)["signal"] is False, name


def test_snapshot_leak_is_named(snapshots: dict[str, Any]) -> None:
    suspect = next(s for s in snapshots["leak_suspects"] if s["feature"] == "retention_call_outcome")
    assert any(f"({SNAPSHOTS['positives']} rows)" in r for r in suspect["reasons"])
    assert snapshots["features"][0]["feature"] == "retention_call_outcome"


def test_snapshot_redundant_and_cardinality(snapshots: dict[str, Any]) -> None:
    pairs = {frozenset((p["a"], p["b"])) for p in snapshots["redundant"]}
    assert frozenset(("monthly_fee_eur", "annual_fee_eur")) in pairs
    assert "high cardinality" in feature(snapshots, "campaign_code")["flags"]
    assert feature(snapshots, "campaign_code")["summary"]["distinct"] == SNAPSHOTS["campaign_levels"]
    assert "near constant" in feature(snapshots, "is_internal_account")["flags"]


def test_snapshot_segment_and_missing_signal(snapshots: dict[str, Any]) -> None:
    legacy = next(s for s in snapshots["segments"] if s["feature"] == "plan" and s["level"] == "legacy")
    assert legacy["differs"] is True
    assert legacy["rate"] == pytest.approx(SNAPSHOTS["legacy_positives"] / SNAPSHOTS["legacy_rows"], abs=1e-4)
    nps = next(m for m in snapshots["missingness"] if m["feature"] == "nps_last")
    assert nps["carries_signal"] is True


def test_snapshot_prints_no_personal_value(churn_repo: Path, snapshots: dict[str, Any]) -> None:
    text = json.dumps(snapshots, ensure_ascii=False)
    rows = read_csv(churn_repo, "snapshots.csv")
    for column in (*PERSONAL_COLUMNS, "account_manager"):
        values = {r[column] for r in rows}
        assert not any(v in text for v in values), column
    assert set(snapshots["personal_columns"]) == set(PERSONAL_COLUMNS)
