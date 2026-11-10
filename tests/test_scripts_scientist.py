"""The data-scientist scripts: small cases worked out by hand, and the acme-churn fixture."""

from __future__ import annotations

import json
import math
import random
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from conftest import ROOT, load, run_json
from test_fixture_acme_churn import (
    DRIFT,
    DUPLICATES,
    ENTITIES,
    EXPERIMENT,
    LEAK,
    MISSING,
    PREDICTIONS,
    TEST,
    TIME_LEAK,
    TRAIN,
)

SHARED = ROOT / "shared"
SKILLS = ROOT / "plugins" / "data-scientist" / "skills"
FRAME = SKILLS / "ds-frame" / "scripts" / "frame_rules.py"
AUDIT = SKILLS / "ds-dataset" / "scripts" / "dataset_audit.py"
EVALUATE = SKILLS / "ds-evaluate" / "scripts" / "model_eval.py"
AB_TEST = SKILLS / "ds-experiment" / "scripts" / "ab_test.py"
ms = load(SHARED / "model_stats.py")
model_eval = load(EVALUATE)


# ---------------------------------------------------------------------------- ranking metrics by hand


def test_roc_auc_by_hand() -> None:
    # Positives .9 .7 .6 against negatives .8 .5: .9 beats both, .7 and .6 beat .5 only -> 4 of 6 pairs.
    assert ms.roc_auc([True, False, True, True, False], [0.9, 0.8, 0.7, 0.6, 0.5]) == pytest.approx(4 / 6)


def test_roc_auc_counts_a_tie_as_half() -> None:
    # (1@.5,0@.5) tie .5, (1@.5,0@.2) win 1, (1@.2,0@.5) loss 0, (1@.2,0@.2) tie .5 -> 2 of 4.
    assert ms.roc_auc([True, False, True, False], [0.5, 0.5, 0.2, 0.2]) == pytest.approx(0.5)
    # All tied: every pair is half, no matter what.
    assert ms.roc_auc([True, False, True, False], [0.3, 0.3, 0.3, 0.3]) == pytest.approx(0.5)


def test_roc_auc_needs_both_classes() -> None:
    assert ms.roc_auc([True, True], [0.1, 0.2]) is None


def test_pr_auc_by_hand() -> None:
    # Average precision: positives at ranks 1, 3, 4 of 5 -> 1/3 x 1 + 1/3 x 2/3 + 1/3 x 3/4 = 29/36.
    assert ms.average_precision([True, False, True, True, False], [0.9, 0.8, 0.7, 0.6, 0.5]) == pytest.approx(29 / 36)


def test_pr_auc_keeps_ties_as_one_group() -> None:
    # The tie at .5 is one point: tp 1, fp 1, precision 1/2 and recall 1/2. Then precision 2/3 at recall 1.
    labels = [True, False, True]
    assert ms.average_precision(labels, [0.5, 0.5, 0.2]) == pytest.approx(0.5 * 0.5 + 0.5 * (2 / 3))
    # The order of the tied rows cannot matter.
    assert ms.average_precision([False, True, True], [0.5, 0.5, 0.2]) == pytest.approx(0.5 * 0.5 + 0.5 * (2 / 3))


def test_brier_and_log_loss_by_hand() -> None:
    labels = [True, False, True]
    probabilities = [0.8, 0.3, 0.6]
    assert ms.brier(labels, probabilities) == pytest.approx((0.04 + 0.09 + 0.16) / 3)
    assert ms.log_loss(labels, probabilities) == pytest.approx(-(math.log(0.8) + math.log(0.7) + math.log(0.6)) / 3)


def test_log_loss_does_not_blow_up_on_certainty() -> None:
    assert math.isfinite(ms.log_loss([True, False], [0.0, 1.0]))


def test_a_bootstrap_weight_vector_sums_to_the_rows() -> None:
    rng = random.Random(1)
    weights = ms.bootstrap_weights(rng, [0, 1, 2, 3, 4], 5)
    assert sum(weights) == 5.0 and all(w == int(w) for w in weights)


def test_a_cluster_moves_together() -> None:
    weights = ms.bootstrap_weights(random.Random(5), [0, 0, 0, 1], 2)
    assert weights[0] == weights[1] == weights[2]


def test_the_weighted_sweep_matches_a_repeated_list() -> None:
    labels = [True, False, True, False, True]
    scores = [0.9, 0.8, 0.8, 0.4, 0.2]
    weights = [2.0, 1.0, 1.0, 3.0, 1.0]
    repeated_labels = [y for y, w in zip(labels, weights, strict=True) for _ in range(int(w))]
    repeated_scores = [s for s, w in zip(scores, weights, strict=True) for _ in range(int(w))]
    swept = ms.rank_sweep(ms.order_scores(scores), labels, weights)
    assert swept.auc == pytest.approx(ms.roc_auc(repeated_labels, repeated_scores))
    assert swept.ap == pytest.approx(ms.average_precision(repeated_labels, repeated_scores))


# ---------------------------------------------------------------------------- proportions, tests, plans


def test_two_proportions_textbook() -> None:
    # Agresti, physicians' aspirin study: 104/11037 aspirin against 189/11034 placebo; Pearson X^2 is 25.0.
    result = ms.two_proportions(189, 11034, 104, 11037)
    assert result.difference == pytest.approx(104 / 11037 - 189 / 11034, abs=1e-9)
    assert result.z**2 == pytest.approx(25.01, abs=0.01)
    assert result.p_value == pytest.approx(5.7e-7, rel=0.05)
    # The unpooled interval Agresti gives for the same study, in absolute value (0.0047, 0.0107).
    assert -result.high == pytest.approx(0.0047, abs=1e-4) and -result.low == pytest.approx(0.0107, abs=1e-4)


def test_two_proportions_textbook_second_case() -> None:
    # R: prop.test(c(150, 120), c(1000, 1000), correct = FALSE) gives X-squared = 3.8537, p-value = 0.04964.
    result = ms.two_proportions(120, 1000, 150, 1000)
    assert result.z**2 == pytest.approx(3.8537, abs=1e-3)
    assert result.p_value == pytest.approx(0.04964, abs=1e-4)


def test_wilson_textbook() -> None:
    low, high = ms.wilson(8, 10)
    assert low == pytest.approx(0.4902, abs=1e-4) and high == pytest.approx(0.9433, abs=1e-4)
    assert ms.wilson(0, 10)[0] == pytest.approx(0.0, abs=1e-9) and ms.wilson(10, 10)[1] == pytest.approx(1.0)


def test_welch_by_hand() -> None:
    # 10 and 12, variances 4 and 9, n = 100 each: se = sqrt(13/100), z = 2 / se.
    result = ms.welch(10.0, 4.0, 100, 12.0, 9.0, 100)
    assert result.z == pytest.approx(2 / math.sqrt(0.13))
    assert result.low == pytest.approx(2 - ms.z_for(0.95) * math.sqrt(0.13))


def test_sample_size_textbook() -> None:
    # R: power.prop.test(p1 = .5, p2 = .75, power = .9) gives n = 76.7; p1 .1, p2 .12, power .8 gives 3841.
    assert ms.sample_size_proportions(0.5, 0.75, 0.05, 0.9) == (77, 77)
    assert ms.sample_size_proportions(0.1, 0.12, 0.05, 0.8) == (3841, 3841)
    # Means, normal approximation: 2 x (1.96 + 0.8416)^2 x 1 / 0.25 = 62.8.
    assert ms.sample_size_means(1.0, 0.5, 0.05, 0.8) == (63, 63)


def test_sample_size_unequal_ratio_needs_more_in_total() -> None:
    n_c, n_t = ms.sample_size_proportions(0.1, 0.12, 0.05, 0.8, ratio=4.0)
    equal_c, equal_t = ms.sample_size_proportions(0.1, 0.12)
    assert n_t == pytest.approx(4 * n_c, abs=1)
    assert n_c + n_t > equal_c + equal_t


def test_mde_round_trips_through_sample_size() -> None:
    mde = ms.mde_proportions(0.1, 3841, 0.05, 0.8)
    assert mde == pytest.approx(0.02, abs=1e-3)
    assert ms.sample_size_proportions(0.1, 0.1 + mde, 0.05, 0.8)[0] <= 3841
    assert ms.mde_means(1.0, 63, 0.05, 0.8) == pytest.approx(0.5, abs=0.005)


def test_chi_square_tail_known_values() -> None:
    assert ms.chi_square_sf(3.841459, 1) == pytest.approx(0.05, abs=1e-5)
    assert ms.chi_square_sf(5.991465, 2) == pytest.approx(0.05, abs=1e-5)
    assert ms.chi_square_sf(7.814728, 3) == pytest.approx(0.05, abs=1e-5)
    assert ms.chi_square_sf(0, 1) == 1.0


def test_holm_by_hand() -> None:
    adjusted = ms.holm([0.01, 0.04, 0.03, 0.005])
    # Sorted: .005x4=.02, .01x3=.03, .03x2=.06, .04x1=.04 -> forced up to .06.
    assert adjusted == pytest.approx([0.03, 0.06, 0.06, 0.02])


def test_psi_known_value() -> None:
    # Sum of (a-e)ln(a/e) over bins .25 against .1,.2,.3,.4; worked out by hand: 0.2282.
    assert ms.psi([0.25, 0.25, 0.25, 0.25], [0.1, 0.2, 0.3, 0.4]) == pytest.approx(0.22822, abs=1e-5)
    assert ms.psi_band(0.05) == "stable" and ms.psi_band(0.12) == "moderate" and ms.psi_band(0.3) == "major"
    assert ms.psi([0.5, 0.5], [0.5, 0.5]) == 0.0


def test_peeking_table_matches_a_simulation() -> None:
    # Five equally spaced looks of a two-sided 5% test under the null: Armitage's 14.2%, checked by Monte Carlo.
    rng = random.Random(11)
    z = ms.z_for(0.95)
    hits = 0
    for _ in range(20000):
        total = 0.0
        for k in range(1, 6):
            total += ms.NORMAL.inv_cdf(min(max(rng.random(), 1e-12), 1 - 1e-12))
            if abs(total) / math.sqrt(k) > z:
                hits += 1
                break
    assert hits / 20000 == pytest.approx(ms.peeking_false_positive(5), abs=0.012)


def test_peeking_rate_rises_with_looks_and_interpolates() -> None:
    assert ms.peeking_false_positive(1) == 0.05
    assert ms.peeking_false_positive(5) == 0.142
    assert 0.142 < ms.peeking_false_positive(7) < 0.193


# ---------------------------------------------------------------------------- model_eval, by hand


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_calibration_table_keeps_tied_scores_in_one_bin() -> None:
    labels = [False] * 8 + [True, True]
    probabilities = [0.1] * 6 + [0.5] * 4
    table = model_eval.calibration_table(labels, probabilities, 2, 0.95)
    assert [row["rows"] for row in table["bins"]] == [6, 4]
    assert table["bins"][0]["mean_predicted"] == pytest.approx(0.1)
    assert table["bins"][1]["observed"] == pytest.approx(0.5)


def test_threshold_treats_ties_as_one_and_prefers_the_cheapest() -> None:
    labels = [True, False, True]
    ordered = ms.order_scores([0.9, 0.9, 0.2])
    rows = model_eval.threshold_rows(ordered, labels, cost_fp=1.0, cost_fn=5.0)
    # Nobody: 2 x 5 = 10. At .9 (both tied rows): fp 1, fn 1: 1 + 5 = 6. At .2 (all): fp 1, fn 0: 1.
    assert [r["cost"] for r in rows] == [10.0, 6.0, 1.0]
    assert model_eval.best_on([0, 1, 2], [0.9, 0.9, 0.2], labels, 1.0, 5.0) == pytest.approx(0.2)


def test_regression_metrics_by_hand(tmp_path: Path) -> None:
    data = write(tmp_path / "p.csv", "id,y,base,model\n1,1,2,1\n2,2,2,2\n3,3,2,4\n4,4,2,6\n")
    result = run_json(
        EVALUATE,
        str(data),
        "--id",
        "id",
        "--label",
        "y",
        "--models",
        "base,model",
        "--baseline",
        "base",
        "--task",
        "regression",
        "--resamples",
        "50",
    )
    assert result["task"] == "regression"
    metrics = {m["model"]: m["metrics"] for m in result["models"]}
    assert metrics["base"]["mae"]["value"] == pytest.approx(1.0)
    assert metrics["base"]["rmse"]["value"] == pytest.approx(math.sqrt(6 / 4))
    assert metrics["base"]["bias"]["value"] == pytest.approx(-0.5)
    assert metrics["model"]["bias"]["value"] == pytest.approx(0.75)


def test_scientific_notation_scores_are_read(tmp_path: Path) -> None:
    data = write(tmp_path / "p.csv", "id,y,base\n1,1,9.9e-01\n2,0,1e-05\n3,1,0.7\n4,0,0.2\n")
    result = run_json(
        EVALUATE, str(data), "--id", "id", "--label", "y", "--models", "base", "--baseline", "base", "--resamples", "50"
    )
    assert result["read"]["rows_used"] == 4
    assert result["models"][0]["metrics"]["roc_auc"]["value"] == pytest.approx(1.0)


def test_two_files_are_joined_and_must_agree_on_the_label(tmp_path: Path) -> None:
    a = write(tmp_path / "a.csv", "id,y,base\n1,1,0.9\n2,0,0.2\n3,1,0.7\n4,0,0.3\n")
    b = write(tmp_path / "b.csv", "id,y,model\n1,1,0.8\n2,0,0.1\n3,1,0.6\n5,0,0.2\n")
    result = run_json(
        EVALUATE,
        str(a),
        str(b),
        "--id",
        "id",
        "--label",
        "y",
        "--models",
        "base,model",
        "--baseline",
        "base",
        "--resamples",
        "30",
    )
    # Id 4 is only in the first file, id 5 only in the second: models are compared on the 3 shared rows.
    assert result["read"]["rows_used"] == 3 and result["read"]["rows_dropped_not_in_every_file"] == 1
    bad = write(tmp_path / "c.csv", "id,y,model\n1,0,0.8\n2,0,0.1\n3,1,0.6\n4,0,0.2\n")
    done = subprocess.run(
        [
            sys.executable,
            str(EVALUATE),
            str(a),
            str(bad),
            "--id",
            "id",
            "--label",
            "y",
            "--models",
            "base,model",
            "--baseline",
            "base",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert done.returncode != 0 and "different label" in done.stderr


def test_a_personal_column_cannot_be_a_slice(tmp_path: Path) -> None:
    data = write(
        tmp_path / "p.csv",
        "id,y,base,email\n" + "\n".join(f"{i},{i % 2},0.{i},x{i}@example.com" for i in range(1, 9)) + "\n",
    )
    done = subprocess.run(
        [
            sys.executable,
            str(EVALUATE),
            str(data),
            "--id",
            "id",
            "--label",
            "y",
            "--models",
            "base",
            "--baseline",
            "base",
            "--slice",
            "email",
            "--resamples",
            "20",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert done.returncode != 0 and "personal" in done.stderr and "example.com" not in done.stdout + done.stderr


# ---------------------------------------------------------------------------- model_eval, on the fixture


def fixture_eval(repo: Path, *extra: str) -> dict[str, Any]:
    return run_json(  # type: ignore[no-any-return]
        EVALUATE,
        str(repo / "data" / "predictions.csv"),
        "--id",
        "prediction_id",
        "--label",
        "churned_60d",
        "--models",
        "baseline_score,logreg_v2,gbt_v7",
        "--baseline",
        "baseline_score",
        "--resamples",
        "1000",
        "--slice",
        "plan",
        "--slice",
        "region",
        "--cost-fp",
        str(PREDICTIONS["costs"]["false_positive"]),
        "--cost-fn",
        str(PREDICTIONS["costs"]["false_negative"]),
        *extra,
    )


@pytest.fixture(scope="module")
def evaluated(churn_repo: Path) -> dict[str, Any]:
    return fixture_eval(churn_repo)


def comparison(result: dict[str, Any], model: str, metric: str) -> dict[str, Any]:
    found: dict[str, Any] = next(c for c in result["comparisons"] if c["model"] == model and c["metric"] == metric)
    return found


def test_evaluate_matches_the_independent_numbers(evaluated: dict[str, Any]) -> None:
    assert evaluated["read"]["rows_used"] == PREDICTIONS["rows"]
    metrics = {m["model"]: m["metrics"] for m in evaluated["models"]}
    for model, value in PREDICTIONS["roc_auc"].items():
        assert metrics[model]["roc_auc"]["value"] == pytest.approx(value, abs=1e-6)
    for model, value in PREDICTIONS["pr_auc"].items():
        assert metrics[model]["pr_auc"]["value"] == pytest.approx(value, abs=1e-6)


def test_one_win_is_inside_the_noise_and_the_other_is_real(evaluated: dict[str, Any]) -> None:
    noise = comparison(evaluated, PREDICTIONS["noise_model"], "roc_auc")
    assert noise["improvement"] > 0 and noise["low"] < 0 < noise["high"] and noise["reading"] == "inside the noise"
    real = comparison(evaluated, PREDICTIONS["real_model"], "roc_auc")
    assert real["low"] > 0 and real["reading"] == "better"


def test_the_best_ranker_is_miscalibrated_and_says_so(evaluated: dict[str, Any]) -> None:
    calibration = evaluated["calibration"]
    assert calibration["gbt_v7"]["reading"] == "miscalibrated"
    assert calibration["gbt_v7"]["ece"] > 0.1
    assert calibration["baseline_score"]["ece"] < 0.04
    assert calibration["baseline_score"]["reading"] == "consistent with its probabilities"
    assert calibration["logreg_v2"]["reading"] == "consistent with its probabilities"


def test_the_threshold_comes_from_the_costs(evaluated: dict[str, Any]) -> None:
    gbt = evaluated["thresholds"]["gbt_v7"]
    assert gbt["best"]["cost_per_1000"] < gbt["act_on_nobody"]["cost_per_1000"]
    assert gbt["out_of_sample_cost_per_1000"] >= gbt["best"]["cost_per_1000"]
    # At the break-even probability this model flags too many, because its probabilities are too high.
    assert gbt["cost_per_1000_at_break_even"] > gbt["best"]["cost_per_1000"]
    assert len(gbt["curve"]) >= 5


def test_the_bad_slice_is_found_and_the_small_are_not_ranked(evaluated: dict[str, Any]) -> None:
    worst = evaluated["slices"]["worst"]["gbt_v7"][0]
    assert (worst["column"], worst["value"]) == PREDICTIONS["bad_slice"]
    assert worst["clearly_worse"] is True and worst["shortfall"] > 0.1
    legacy = next(e for e in evaluated["slices"]["by_column"]["plan"] if e["value"] == "legacy")
    assert legacy["models"]["baseline_score"]["clearly_worse_than_whole_file"] is False


def test_too_small_a_slice_is_listed_but_not_ranked(tmp_path: Path) -> None:
    rows = "\n".join(f"{i},{i % 2},0.{i % 9 + 1},a" for i in range(1, 200))
    rows += "\n" + "\n".join(f"{i},{i % 2},0.5,b" for i in range(200, 215))
    data = write(tmp_path / "p.csv", "id,y,base,kind\n" + rows + "\n")
    result = run_json(
        EVALUATE,
        str(data),
        "--id",
        "id",
        "--label",
        "y",
        "--models",
        "base",
        "--baseline",
        "base",
        "--slice",
        "kind",
        "--resamples",
        "30",
    )
    by_value = {e["value"]: e for e in result["slices"]["by_column"]["kind"]}
    assert by_value["b"]["too_small"] is True and "models" not in by_value["b"]
    assert by_value["a"]["too_small"] is False


def test_the_same_seed_gives_the_same_output(churn_repo: Path) -> None:
    args = [
        str(churn_repo / "data" / "predictions.csv"),
        "--id",
        "prediction_id",
        "--label",
        "churned_60d",
        "--models",
        "baseline_score,gbt_v7",
        "--baseline",
        "baseline_score",
        "--resamples",
        "100",
        "--seed",
        "3",
    ]
    first = subprocess.run([sys.executable, str(EVALUATE), *args], capture_output=True, check=True, timeout=120)
    second = subprocess.run([sys.executable, str(EVALUATE), *args], capture_output=True, check=True, timeout=120)
    assert first.stdout == second.stdout
    other = subprocess.run(
        [sys.executable, str(EVALUATE), *args[:-1], "4"], capture_output=True, check=True, timeout=120
    )
    assert other.stdout != first.stdout


def test_evaluate_never_prints_a_personal_value(churn_repo: Path, evaluated: dict[str, Any]) -> None:
    assert evaluated["read"]["personal_columns_in_file"] == ["email"]
    output = json.dumps(evaluated)
    assert "example.com" not in output
    assert "P000001" not in output


# ---------------------------------------------------------------------------- dataset_audit


def audit(repo: Path, *extra: str) -> dict[str, Any]:
    return run_json(  # type: ignore[no-any-return]
        AUDIT,
        "--train",
        str(repo / "data" / "train.csv"),
        "--test",
        str(repo / "data" / "test.csv"),
        "--label",
        "churned_60d",
        "--id",
        "row_id",
        "--entity",
        "customer_id",
        "--time",
        "snapshot_date",
        "--horizon-days",
        "60",
        *extra,
    )


@pytest.fixture(scope="module")
def audited(churn_repo: Path) -> dict[str, Any]:
    return audit(churn_repo)


def test_audit_finds_the_target_leak(audited: dict[str, Any]) -> None:
    top = audited["target_leakage"][0]
    assert top["feature"] == LEAK["column"] and top["strength"] >= LEAK["single_feature_strength_at_least"]
    assert top["flag"] == "almost perfect"
    assert all(row["flag"] is None for row in audited["target_leakage"][1:])


def test_audit_finds_the_timestamp_leak(audited: dict[str, Any]) -> None:
    rows = {(r["column"], r["split"]): r["rows"] for r in audited["time_leakage"]["after_prediction_moment"]}
    assert rows == {
        (TIME_LEAK["column"], "train"): TIME_LEAK["train_rows"],
        (TIME_LEAK["column"], "test"): TIME_LEAK["test_rows"],
    }


def test_audit_finds_entities_and_duplicates(audited: dict[str, Any]) -> None:
    overlap = audited["entity_overlap"][0]
    assert overlap["shared_entities"] == ENTITIES["customers_on_both_sides"]
    assert overlap["rows_of_second_with_a_shared_entity"] == ENTITIES["test_rows_with_a_train_customer"]
    assert audited["duplicates"]["across"][0]["rows_of_second_also_in_first"] == DUPLICATES


def test_audit_reports_split_order(audited: dict[str, Any]) -> None:
    order = audited["time_leakage"]["split_order"]
    # The exact copies are the only test rows from the training period.
    assert order["test_rows_on_or_before_train_last"] == DUPLICATES
    assert order["test_start_for_labels"] == "2026-04-01"
    # Every snapshot from February and March has a 60-day label that ends after 1 April.
    assert order["train_rows_with_labels_after_test_start"] > 0


def test_audit_finds_missingness_by_class(audited: dict[str, Any]) -> None:
    row = next(r for r in audited["missing_by_class"] if r["feature"] == MISSING["column"])
    assert row["missing_share_positive"] == pytest.approx(MISSING["positive_share"], abs=1e-3)
    assert row["missing_share_negative"] == pytest.approx(MISSING["negative_share"], abs=1e-3)
    assert row["differs"] is True


def test_audit_finds_the_drifting_feature_with_its_psi(audited: dict[str, Any]) -> None:
    worst = audited["drift"][0]
    assert worst["feature"] == DRIFT["column"] and DRIFT["psi_low"] <= worst["psi"] <= DRIFT["psi_high"]
    assert worst["band"] == "major"
    assert all(r["psi"] < DRIFT["stable_below"] for r in audited["drift"][1:])


def test_audit_counts_classes_and_finds_the_personal_columns(audited: dict[str, Any]) -> None:
    balance = audited["class_balance"]["by_split"]
    assert balance["train"]["positives"] == TRAIN["positives"] and balance["test"]["positives"] == TEST["positives"]
    assert {c["column"] for c in audited["personal_columns"]} == {"email", "full_name", "phone"}


def test_audit_says_do_not_trust(audited: dict[str, Any]) -> None:
    assert audited["verdict"] == "do not trust yet"
    assert [p["severity"] for p in audited["problems"]][:3] == ["high", "high", "high"]


def test_audit_prints_no_personal_value_and_no_row(churn_repo: Path, audited: dict[str, Any]) -> None:
    output = json.dumps(audited)
    assert "example.com" not in output
    for token in ("Borović", "Ana ", "+381"):
        assert token not in output


def test_audit_on_clean_data_finds_nothing(tmp_path: Path) -> None:
    train = ["id,customer,day,x,y"]
    test = ["id,customer,day,x,y"]
    rng = random.Random(1)
    for i in range(600):
        x = rng.random()
        train.append(f"{i},c{i},2026-01-{(i % 28) + 1:02d},{x:.4f},{int(rng.random() < 0.3)}")
    for i in range(600, 800):
        x = rng.random()
        test.append(f"{i},c{i},2026-03-{(i % 28) + 1:02d},{x:.4f},{int(rng.random() < 0.3)}")
    tr = write(tmp_path / "tr.csv", "\n".join(train) + "\n")
    te = write(tmp_path / "te.csv", "\n".join(test) + "\n")
    result = run_json(
        AUDIT,
        "--train",
        str(tr),
        "--test",
        str(te),
        "--label",
        "y",
        "--id",
        "id",
        "--entity",
        "customer",
        "--time",
        "day",
    )
    assert result["verdict"] == "no blocking problem found"
    assert result["duplicates"]["across"][0]["rows_of_second_also_in_first"] == 0


def test_audit_finds_a_numeric_leak_and_a_near_unique_column_is_left_out(tmp_path: Path) -> None:
    lines = ["id,y,leak_amount,ref"]
    for i in range(200):
        y = i % 2
        lines.append(f"{i},{y},{(i * 13) % 97 + 1000 * y},r{i}")
    tr = write(tmp_path / "t.csv", "\n".join(lines) + "\n")
    te = write(tmp_path / "e.csv", "\n".join(lines[:1] + lines[1:60]) + "\n")
    result = run_json(AUDIT, "--train", str(tr), "--test", str(te), "--label", "y", "--id", "id")
    assert result["target_leakage"][0]["feature"] == "leak_amount"
    assert result["target_leakage"][0]["strength"] == pytest.approx(1.0)
    assert "ref" in result["features"]["id_like_not_checked"]


def test_audit_reads_a_single_file_with_a_split_column(tmp_path: Path) -> None:
    rows = "\n".join(f"{i},{'train' if i < 150 else 'test'},{i % 3},{i % 2}" for i in range(200))
    data = write(tmp_path / "d.csv", "id,split,x,y\n" + rows + "\n")
    result = run_json(AUDIT, "--data", str(data), "--split-column", "split", "--label", "y", "--id", "id")
    assert result["splits"]["train"]["rows_read"] == 150 and result["splits"]["test"]["rows_read"] == 50


def test_audit_refuses_a_personal_label(tmp_path: Path) -> None:
    data = write(tmp_path / "t.csv", "id,email\n1,a@example.com\n2,b@example.com\n")
    other = write(tmp_path / "u.csv", "id,email\n3,c@example.com\n")
    done = subprocess.run(
        [sys.executable, str(AUDIT), "--train", str(data), "--test", str(other), "--label", "email", "--id", "id"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert done.returncode != 0 and "example.com" not in done.stderr


# ---------------------------------------------------------------------------- ab_test


def clean_read(repo: Path, *extra: str) -> dict[str, Any]:
    guardrails = []
    for name, margin in EXPERIMENT["guardrails"].items():
        guardrails += ["--guardrail", f"{name}:{margin}"]
    return run_json(  # type: ignore[no-any-return]
        AB_TEST,
        "read",
        str(repo / "data" / "experiment_clean.csv"),
        "--variant",
        "variant",
        "--control",
        "control",
        "--treatment",
        "treatment",
        "--unit",
        "subscriber_id",
        "--primary",
        "renewed",
        "--metrics",
        "upgraded,app_open_7d,arpu_eur",
        *guardrails,
        "--lower-is-better",
        ",".join(EXPERIMENT["lower_is_better"]),
        "--min-effect",
        str(EXPERIMENT["min_effect"]),
        "--looks",
        str(EXPERIMENT["looks"]),
        "--planned-n",
        str(EXPERIMENT["planned_n_per_arm"]),
        "--time",
        "assigned_at",
        *extra,
    )


def metric(result: dict[str, Any], name: str) -> dict[str, Any]:
    found: dict[str, Any] = next(m for m in result["metrics"] if m["metric"] == name)
    return found


def test_srm_chi_square_matches_the_hand_value(churn_repo: Path) -> None:
    result = clean_read(churn_repo)
    assert result["sample_ratio"]["chi_square"] == pytest.approx(EXPERIMENT["clean_chi_square"], abs=1e-6)
    assert result["sample_ratio"]["mismatch"] is False


def test_a_broken_split_stops_the_read_and_prints_no_metric(churn_repo: Path) -> None:
    result = run_json(
        AB_TEST,
        "read",
        str(churn_repo / "data" / "experiment_broken.csv"),
        "--variant",
        "variant",
        "--control",
        "control",
        "--treatment",
        "treatment",
        "--unit",
        "subscriber_id",
        "--primary",
        "renewed",
        "--metrics",
        "arpu_eur",
        "--guardrail",
        "support_contact:0.02",
    )
    assert result["sample_ratio"]["chi_square"] == pytest.approx(EXPERIMENT["broken_chi_square"], abs=1e-6)
    assert result["sample_ratio"]["mismatch"] is True
    assert result["stopped"] and "sample ratio mismatch" in result["stopped"]
    assert result["metrics"] is None and result["guardrails"] is None
    assert result["decision"]["call"] == "inconclusive"


def test_the_primary_is_significant_before_correction_and_not_after(churn_repo: Path) -> None:
    result = clean_read(churn_repo)
    renewed = metric(result, "renewed")
    assert renewed["p_value"] == pytest.approx(EXPERIMENT["renewed_p"], abs=1e-4)
    assert renewed["adjusted_p"] == pytest.approx(EXPERIMENT["renewed_holm_p"], abs=1e-4)
    assert renewed["significant_uncorrected"] is True and renewed["significant_corrected"] is False
    assert renewed["corrected_low"] < 0 < renewed["corrected_high"]
    assert result["decision"]["call"] == "inconclusive"


def test_means_use_the_welch_formula(churn_repo: Path) -> None:
    arpu = metric(clean_read(churn_repo), "arpu_eur")
    assert arpu["kind"] == "mean"
    n_c, n_t = arpu["control"]["n"], arpu["treatment"]["n"]
    se = math.sqrt(arpu["control"]["sd"] ** 2 / n_c + arpu["treatment"]["sd"] ** 2 / n_t)
    assert arpu["difference"] == pytest.approx(arpu["treatment"]["mean"] - arpu["control"]["mean"], abs=2e-6)
    assert arpu["z"] == pytest.approx(arpu["difference"] / se, abs=1e-3)


def test_guardrails_hold_and_peeking_is_reported(churn_repo: Path) -> None:
    result = clean_read(churn_repo)
    status = {g["metric"]: g["status"] for g in result["guardrails"]}
    assert status == {"support_contact": "held", "refund_requested": "held"}
    peeking = result["peeking"]
    assert peeking["true_false_positive_rate_at_nominal_5_percent"] == pytest.approx(0.193)
    assert peeking["reached_plan"] is True
    assert len(peeking["running_view"]["days"]) == 14


def test_ab_test_prints_no_personal_value(churn_repo: Path) -> None:
    output = json.dumps(clean_read(churn_repo))
    assert "example.com" not in output
    assert "S000001" not in output


def small_experiment(tmp_path: Path, control: tuple[int, int], treatment: tuple[int, int]) -> Path:
    rows = []
    unit = 0
    for arm, (n, successes) in (("control", control), ("treatment", treatment)):
        for i in range(n):
            unit += 1
            rows.append(f"u{unit},{arm},{1 if i < successes else 0},{1 if i < n * 0.02 else 0}")
    return write(tmp_path / "e.csv", "unit,arm,win,harm\n" + "\n".join(rows) + "\n")


READ_ARGS = [
    "--variant",
    "arm",
    "--control",
    "control",
    "--treatment",
    "treatment",
    "--unit",
    "unit",
    "--primary",
    "win",
]


def test_a_clear_win_with_held_guardrails_ships(tmp_path: Path) -> None:
    data = small_experiment(tmp_path, (5000, 2000), (5000, 2300))
    result = run_json(AB_TEST, "read", str(data), *READ_ARGS, "--guardrail", "harm:0.02", "--lower-is-better", "harm")
    assert result["decision"]["call"] == "ship"


def test_a_breached_guardrail_stops_a_win(tmp_path: Path) -> None:
    rows = []
    for arm, wins, harms, n in (("control", 2000, 100, 5000), ("treatment", 2300, 500, 5000)):
        for i in range(n):
            rows.append(f"{arm}{i},{arm},{1 if i < wins else 0},{1 if i < harms else 0}")
    data = write(tmp_path / "e.csv", "unit,arm,win,harm\n" + "\n".join(rows) + "\n")
    result = run_json(AB_TEST, "read", str(data), *READ_ARGS, "--guardrail", "harm:0.02", "--lower-is-better", "harm")
    assert result["decision"]["call"] == "do not ship"
    assert "guardrail" in result["decision"]["because"][0]


def test_a_significant_loss_is_do_not_ship(tmp_path: Path) -> None:
    data = small_experiment(tmp_path, (5000, 2300), (5000, 2000))
    result = run_json(AB_TEST, "read", str(data), *READ_ARGS)
    assert result["decision"]["call"] == "do not ship"


def test_an_underpowered_null_is_inconclusive_and_a_powered_null_is_do_not_ship(tmp_path: Path) -> None:
    data = small_experiment(tmp_path, (20000, 8000), (20000, 8040))
    # The whole interval sits under a minimum effect of three points: a real answer, not "we do not know".
    powered = run_json(AB_TEST, "read", str(data), *READ_ARGS, "--min-effect", "0.03")
    assert powered["decision"]["call"] == "do not ship"
    small = small_experiment(tmp_path, (200, 80), (200, 84))
    underpowered = run_json(AB_TEST, "read", str(small), *READ_ARGS, "--min-effect", "0.03")
    assert underpowered["decision"]["call"] == "inconclusive"


def test_a_unit_in_both_arms_or_repeated_stops_the_read(tmp_path: Path) -> None:
    rows = ["unit,arm,win,harm"]
    for i in range(300):
        arm = "control" if i % 2 else "treatment"
        rows.append(f"u{i},{arm},{i % 3 == 0:d},0")
    for i in range(300, 310):
        rows.append(f"u{i - 300},treatment,1,0")
    data = write(tmp_path / "e.csv", "\n".join(rows) + "\n")
    result = run_json(AB_TEST, "read", str(data), *READ_ARGS)
    assert result["stopped"] and "units" in result["stopped"] and result["metrics"] is None


def test_a_personal_column_cannot_be_a_metric(tmp_path: Path) -> None:
    data = write(tmp_path / "e.csv", "unit,arm,win,email\nu1,control,1,a@example.com\nu2,treatment,0,b@example.com\n")
    done = subprocess.run(
        [sys.executable, str(AB_TEST), "read", str(data), *READ_ARGS, "--metrics", "email"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert done.returncode != 0 and "personal" in done.stderr and "example.com" not in done.stdout + done.stderr


def test_a_guardrail_needs_a_margin(tmp_path: Path) -> None:
    data = small_experiment(tmp_path, (100, 50), (100, 50))
    done = subprocess.run(
        [sys.executable, str(AB_TEST), "read", str(data), *READ_ARGS, "--guardrail", "harm"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert done.returncode != 0 and "MARGIN" in done.stderr


def test_plan_sample_size_and_mde() -> None:
    planned = run_json(AB_TEST, "plan", "--baseline", "0.1", "--mde", "0.02", "--daily-units", "1000")
    assert planned["sample"]["n_control"] == 3841
    assert planned["days_at_daily_units"] == pytest.approx(7.7, abs=0.05)
    planned = run_json(AB_TEST, "plan", "--baseline", "0.1", "--mde", "0.2", "--relative", "--metrics", "4")
    assert planned["alpha_per_metric"] == pytest.approx(0.0125)
    assert planned["sample"]["absolute_difference"] == pytest.approx(0.02)
    mde = run_json(AB_TEST, "plan", "--baseline", "0.1", "--n-per-arm", "3841")
    assert mde["mde"]["absolute"] == pytest.approx(0.02, abs=1e-3)
    means = run_json(AB_TEST, "plan", "--kind", "mean", "--baseline", "30", "--sd", "1", "--mde", "0.5")
    assert means["sample"]["n_control"] == 63


# ---------------------------------------------------------------------------- frame_rules


def frame(**facts: Any) -> dict[str, Any]:
    done = subprocess.run(
        [sys.executable, str(FRAME), "-"],
        input=json.dumps(facts),
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    return json.loads(done.stdout)  # type: ignore[no-any-return]


AUTO_RENEW = {
    "decision_named": True,
    "is_language_task": False,
    "task": "classification",
    "label_exists": True,
    "label_delay_days": 30,
    "feedback_budget_days": 60,
    "signals_known_at_decision": True,
    "rule_meets_bar": True,
    "input_kind": "tabular",
    "decisions_per_year": 9000,
    "base_rate": 0.098,
    "cost_false_positive": 0.05,
    "cost_false_negative": 8.0,
    "learned_model_cost_per_year": 60000,
}
RETENTION = {
    "decision_named": True,
    "is_language_task": False,
    "task": "classification",
    "label_exists": True,
    "label_delay_days": 60,
    "feedback_budget_days": 90,
    "signals_known_at_decision": True,
    "rule_meets_bar": False,
    "input_kind": "tabular",
    "labelled_rows": 3400,
    "minority_rows": 580,
    "candidate_features": 11,
    "must_recompute_by_hand": False,
    "serving_can_call_model": True,
    "decisions_per_year": 480000,
    "base_rate": 0.165,
    "cost_false_positive": 25.0,
    "cost_false_negative": 90.0,
    "learned_model_cost_per_year": 60000,
}


def eliminated(result: dict[str, Any]) -> set[str]:
    return {o["id"] for o in result["options"] if o["status"] == "eliminated"}


def test_a_rule_that_meets_the_bar_ends_the_ladder() -> None:
    result = frame(**AUTO_RENEW)
    assert result["lowest_open"] == "lookup_rule"
    assert result["open"] == ["lookup_rule"]
    # The perfect model would save 9000 x min(0.098 x 8, 0.902 x 0.05) = about EUR 406 a year.
    assert result["economics"]["ceiling_per_year"] == pytest.approx(405.9, abs=0.1)
    rules = {r["rule"] for o in result["options"] for r in o["eliminated_by"]}
    assert "ceiling-below-cost" in rules and "rule-meets-bar" in rules


def test_a_real_model_stays_open_when_the_brief_needs_one() -> None:
    result = frame(**RETENTION)
    assert result["lowest_open"] == "simple_score"
    assert "linear" in result["open"] and "gbt" in result["open"] and "deep" not in result["open"]
    economics = result["economics"]
    # 90 x .165 = 14.85 per case to act on nobody, 25 x .835 = 20.875 to act on everyone.
    assert economics["cheapest_trivial_policy"] == "act on nobody"
    assert economics["cheapest_trivial_cost_per_case"] == pytest.approx(14.85)
    assert economics["break_even_probability"] == pytest.approx(25 / 115, abs=1e-5)


def test_a_language_task_goes_to_ai_pattern() -> None:
    result = frame(is_language_task=True)
    assert result["use_instead"]["skill"] == "ai-pattern"
    assert result["open"] == []


def test_no_decision_means_no_model() -> None:
    assert frame(decision_named=False)["open"] == []


def test_no_label_keeps_only_the_rule_and_the_score() -> None:
    result = frame(label_exists=False)
    assert eliminated(result) == {"linear", "gbt", "deep"}


def test_a_label_that_comes_too_late_is_a_rule() -> None:
    result = frame(label_delay_days=120, feedback_budget_days=30)
    assert {"linear", "gbt", "deep"} <= eliminated(result)


def test_too_few_positive_cases_for_the_features_rules_out_linear_and_trees() -> None:
    result = frame(minority_rows=90, candidate_features=20)
    assert {"linear", "gbt"} <= eliminated(result)


def test_unstructured_input_leaves_only_deep_learning_and_trees() -> None:
    assert eliminated(frame(input_kind="unstructured")) == {"lookup_rule", "simple_score", "linear"}


def test_open_facts_list_what_would_decide() -> None:
    result = frame()
    assert result["open"] == [
        o for o, _ in [("lookup_rule", 0), ("simple_score", 0), ("linear", 0), ("gbt", 0), ("deep", 0)]
    ]
    assert any(f["fact"] == "label_exists" for f in result["open_facts"])


def test_an_unknown_fact_is_an_error() -> None:
    done = subprocess.run(
        [sys.executable, str(FRAME), "-"], input='{"nonsense": true}', capture_output=True, text=True, timeout=30
    )
    assert done.returncode == 1 and "unknown fact" in done.stderr
