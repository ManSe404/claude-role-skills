#!/usr/bin/env python3
"""Compare trained models from files of predictions, so that a difference inside the noise is called that.

Usage: python3 model_eval.py PRED.csv [PRED2.csv ...] --id ID --label LABEL --models MODEL[,MODEL] --baseline MODEL
                             [--task auto|classification|regression] [--positive VALUE] [--primary METRIC]
                             [--cost-fp X --cost-fn Y] [--slice COLUMN ...] [--slice-file FILE]
                             [--resamples N] [--seed N] [--confidence 0.95] [--bins N] [--worst N]

Files are CSV or JSON Lines with an id, the label and one score column per model. A row must be scored by every
model, or it is dropped for all of them: models are never compared on different rows. Several files are joined on the
id and must agree on the label. If an id repeats inside the one file, its rows are resampled together.

Classification: ROC-AUC and PR-AUC (average precision) for ranking, log loss and Brier score when the scores are
probabilities, a calibration table in equal-count bins with a Wilson interval on the observed rate, and with both
costs the threshold that minimises what the errors cost. The threshold is checked out of sample: chosen on one random
half and costed on the other, and the other way round. Regression: MAE, RMSE and bias (mean of prediction - label).

A percentile bootstrap gives the interval of each metric; the same resample is used for every model, so the difference
to the baseline is paired. A difference whose interval holds zero reads "inside the noise". A slice with too few rows
or too few of a class is listed, but never ranked. `worst` is the largest shortfall against the whole file.

`--seed` decides every draw: the same seed gives the same bytes. It prints columns and counts, and each slice value,
so a personal column is refused as a slice. Read-only, standard library only, JSON on stdout.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from dataclasses import dataclass
from operator import mul
from pathlib import Path
from typing import Any

# The other scripts of this pack are copies in the same folder.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import data_profile
import measure
import model_stats as ms

HIGHER = 1
LOWER = -1
CLOSER_TO_ZERO = 0
MAX_SLICE_VALUES = 40
MIN_SLICE_ROWS = 100
MIN_SLICE_CLASS = 10
MIN_RESAMPLES_DEFINED = 0.5
SLICE_RESAMPLES = 500
CURVE_POINTS = 21


@dataclass
class Data:
    task: str
    labels: list[bool]
    values: list[float]
    scores: dict[str, list[float]]
    slices: dict[str, list[str]]
    clusters: list[int]
    n_clusters: int
    read: dict[str, Any]


def read_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare trained models from files of predictions.")
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--id", dest="row_id", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--models", required=True, help="score columns, comma separated")
    parser.add_argument("--baseline", required=True, help="one of the models")
    parser.add_argument("--task", choices=("auto", "classification", "regression"), default="auto")
    parser.add_argument("--positive")
    parser.add_argument("--primary")
    parser.add_argument("--cost-fp", type=float)
    parser.add_argument("--cost-fn", type=float)
    parser.add_argument("--slice", action="append", default=[], dest="slices")
    parser.add_argument("--slice-file", type=Path)
    parser.add_argument("--resamples", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--confidence", type=float, default=0.95)
    parser.add_argument("--bins", type=int, default=10)
    parser.add_argument("--worst", type=int, default=5)
    parser.add_argument("--max-rows", type=int, default=data_profile.MAX_ROWS)
    args = parser.parse_args(argv)
    args.model_list = [m.strip() for m in args.models.split(",") if m.strip()]
    if args.baseline not in args.model_list:
        parser.error(f"--baseline {args.baseline} is not in --models")
    if (args.cost_fp is None) != (args.cost_fn is None):
        parser.error("give both --cost-fp and --cost-fn, or neither")
    return args


def by_id(table: measure.Table, id_column: str) -> dict[str | None, measure.Row]:
    rows: dict[str | None, measure.Row] = {}
    for row in table.rows:
        key = row[id_column]
        if key in rows:
            raise SystemExit(f"{table.name}: id column {id_column!r} repeats, so it cannot be joined on it")
        rows[key] = row
    return rows


def load(args: argparse.Namespace) -> Data:
    tables = [measure.load(p, args.max_rows) for p in args.paths]
    for table in tables:
        measure.check_columns(table, [args.row_id])
    base = tables[0]
    measure.check_columns(base, [args.label])
    measure.check_public(base, [args.label], "the label")
    joined: list[measure.Row] = [dict(r) for r in base.rows]
    not_in_all = 0
    for table in tables[1:]:
        lookup = by_id(table, args.row_id)
        kept: list[measure.Row] = []
        disagreements = 0
        for row in joined:
            other = lookup.get(row[args.row_id])
            if other is None:
                not_in_all += 1
                continue
            if args.label in other and other[args.label] != row[args.label]:
                disagreements += 1
            for column, value in other.items():
                row.setdefault(column, value)
            kept.append(row)
        if disagreements:
            raise SystemExit(f"{table.name}: {disagreements} rows have a different label than in {base.name}")
        joined = kept
    columns = {c for t in tables for c in t.header}
    missing_models = [m for m in args.model_list if m not in columns]
    if missing_models:
        raise SystemExit(f"no column for model(s): {', '.join(missing_models)}")
    personal: dict[str, str] = {}
    for table in tables:
        personal.update(table.personal)
    for model in args.model_list:
        if model in personal:
            raise SystemExit(f"{model} holds personal data ({personal[model]}), so it cannot be a score column")
    slice_values: dict[str, list[str]] = {}
    extra = None
    if args.slice_file is not None:
        extra = measure.load(args.slice_file, args.max_rows)
        measure.check_columns(extra, [args.row_id])
        personal.update(extra.personal)
    lookup_extra = by_id(extra, args.row_id) if extra is not None else {}
    for column in args.slices:
        if column in personal:
            raise SystemExit(f"{column} holds personal data ({personal[column]}): it cannot be used as a slice")
        if column in columns:
            slice_values[column] = [row[column] or "(missing)" for row in joined]
        elif extra is not None and column in extra.header:
            slice_values[column] = [
                (lookup_extra.get(row[args.row_id]) or {}).get(column) or "(missing)" for row in joined
            ]
        else:
            raise SystemExit(f"no column {column!r} for a slice")
        if len(set(slice_values[column])) > MAX_SLICE_VALUES:
            raise SystemExit(
                f"{column} has {len(set(slice_values[column]))} values, too many to slice on (max {MAX_SLICE_VALUES})"
            )
    return prepare(args, joined, slice_values, personal, not_in_all, base)


def detect_task(cells: list[str | None], positive: str | None) -> str:
    present = [c for c in cells if c is not None]
    if present and all(ms.parse_binary(c, positive) is not None for c in present):
        return "classification"
    return "regression"


def prepare(
    args: argparse.Namespace,
    joined: list[measure.Row],
    slice_values: dict[str, list[str]],
    personal: dict[str, str],
    not_in_all: int,
    base: measure.Table,
) -> Data:
    cells = [r[args.label] for r in joined]
    task = detect_task(cells, args.positive) if args.task == "auto" else args.task
    labels: list[bool] = []
    values: list[float] = []
    scores: dict[str, list[float]] = {m: [] for m in args.model_list}
    kept_slices: dict[str, list[str]] = {c: [] for c in slice_values}
    no_label = 0
    missing_scores = dict.fromkeys(args.model_list, 0)
    cluster_of: dict[str | None, int] = {}
    clusters: list[int] = []
    for i, row in enumerate(joined):
        label: bool | float | None
        if task == "classification":
            label = ms.parse_binary(row[args.label], args.positive)
        else:
            label = ms.to_float(row[args.label])
        if label is None:
            no_label += 1
            continue
        row_scores = {m: ms.to_float(row.get(m)) for m in args.model_list}
        if any(s is None for s in row_scores.values()):
            for model, score in row_scores.items():
                if score is None:
                    missing_scores[model] += 1
            continue
        if task == "classification":
            labels.append(bool(label))
        else:
            values.append(float(label))
        for model, score in row_scores.items():
            assert score is not None
            scores[model].append(score)
        for column, column_values in slice_values.items():
            kept_slices[column].append(column_values[i])
        clusters.append(cluster_of.setdefault(row[args.row_id], len(cluster_of)))
    rows = len(labels) if task == "classification" else len(values)
    if rows == 0:
        raise SystemExit("no rows left after reading the labels and scores")
    read: dict[str, Any] = {
        "rows_in_file": len(base.rows),
        "rows_used": rows,
        "rows_without_a_label": no_label,
        "rows_dropped_not_in_every_file": not_in_all,
        "rows_dropped_missing_score": missing_scores,
        "repeated_ids": rows - len(cluster_of),
        "personal_columns_in_file": sorted(personal),
    }
    if task == "classification":
        read["positives"] = sum(labels)
        read["base_rate"] = round(sum(labels) / rows, 6)
    return Data(task, labels, values, scores, kept_slices, clusters, len(cluster_of), read)


METRICS = {
    "classification": {"roc_auc": HIGHER, "pr_auc": HIGHER, "log_loss": LOWER, "brier": LOWER},
    "regression": {"mae": LOWER, "rmse": LOWER, "bias": CLOSER_TO_ZERO},
}


@dataclass
class Model:
    """Everything precomputed once per model so a resample only multiplies weights."""

    name: str
    probabilities: bool
    ordered: ms.Ordered | None
    losses: list[float] | None
    briers: list[float] | None
    residuals: list[float] | None


def build_model(name: str, data: Data) -> Model:
    if data.task == "classification":
        scores = data.scores[name]
        probabilities = all(0.0 <= s <= 1.0 for s in scores)
        return Model(
            name,
            probabilities,
            ms.order_scores(scores),
            [ms.log_loss_row(y, p) for y, p in zip(data.labels, scores, strict=True)] if probabilities else None,
            [ms.brier_row(y, p) for y, p in zip(data.labels, scores, strict=True)] if probabilities else None,
            None,
        )
    residuals = [p - v for p, v in zip(data.scores[name], data.values, strict=True)]
    return Model(name, True, None, None, None, residuals)


def metric_row(
    model: Model,
    data: Data,
    weights: list[float] | None,
    cost_fp: float | None,
    cost_fn: float | None,
) -> dict[str, float | None]:
    if data.task == "classification":
        assert model.ordered is not None
        ranks = ms.rank_sweep(model.ordered, data.labels, weights, cost_fp, cost_fn)
        total = sum(weights) if weights is not None else float(len(data.labels))
        out: dict[str, float | None] = {"roc_auc": ranks.auc, "pr_auc": ranks.ap}
        if model.losses is not None and model.briers is not None:
            if weights is None:
                out["log_loss"] = sum(model.losses) / total
                out["brier"] = sum(model.briers) / total
            else:
                out["log_loss"] = sum(map(mul, weights, model.losses)) / total
                out["brier"] = sum(map(mul, weights, model.briers)) / total
        if ranks.min_cost is not None:
            out["cost_per_1000"] = ranks.min_cost * 1000
        return out
    assert model.residuals is not None
    residuals = model.residuals
    if weights is None:
        total = float(len(residuals))
        mae = sum(abs(e) for e in residuals) / total
        mse = sum(e * e for e in residuals) / total
        bias = sum(residuals) / total
    else:
        total = sum(weights)
        mae = sum(w * abs(e) for w, e in zip(weights, residuals, strict=True)) / total
        mse = sum(w * e * e for w, e in zip(weights, residuals, strict=True)) / total
        bias = sum(map(mul, weights, residuals)) / total
    return {"mae": mae, "rmse": math.sqrt(mse), "bias": bias}


def direction_of(metric: str) -> int:
    if metric == "cost_per_1000":
        return LOWER
    for table in METRICS.values():
        if metric in table:
            return table[metric]
    raise SystemExit(f"unknown metric {metric}")


def improvement(metric: str, model_value: float, baseline_value: float) -> float:
    """Positive when the model is better than the baseline, in the metric's own units."""
    direction = direction_of(metric)
    if direction == HIGHER:
        return model_value - baseline_value
    if direction == LOWER:
        return baseline_value - model_value
    return abs(baseline_value) - abs(model_value)


def interval(values: list[float], confidence: float) -> tuple[float | None, float | None]:
    if not values:
        return (None, None)
    ordered = sorted(values)
    tail = (1 - confidence) / 2
    return (ms.percentile(ordered, tail), ms.percentile(ordered, 1 - tail))


def rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 6)


def bootstrap(
    models: dict[str, Model],
    data: Data,
    args: argparse.Namespace,
) -> dict[str, dict[str, list[float | None]]]:
    rng = random.Random(f"{args.seed}:overall")
    samples: dict[str, dict[str, list[float | None]]] = {name: {} for name in models}
    for _ in range(args.resamples):
        weights = ms.bootstrap_weights(rng, data.clusters, data.n_clusters)
        for name, model in models.items():
            for metric, value in metric_row(model, data, weights, args.cost_fp, args.cost_fn).items():
                samples[name].setdefault(metric, []).append(value)
    return samples


def overall_report(
    models: dict[str, Model],
    data: Data,
    args: argparse.Namespace,
    samples: dict[str, dict[str, list[float | None]]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, float | None]]]:
    points = {name: metric_row(model, data, None, args.cost_fp, args.cost_fn) for name, model in models.items()}
    report = []
    for name, model in models.items():
        metrics: dict[str, Any] = {}
        for metric, value in points[name].items():
            defined = [v for v in samples[name][metric] if v is not None]
            enough = len(defined) >= MIN_RESAMPLES_DEFINED * args.resamples
            low, high = interval(defined, args.confidence) if enough else (None, None)
            metrics[metric] = {"value": rounded(value), "low": rounded(low), "high": rounded(high)}
        report.append(
            {
                "model": name,
                "is_baseline": name == args.baseline,
                "probabilities": model.probabilities,
                "metrics": metrics,
            }
        )
    comparisons = []
    for name in models:
        if name == args.baseline:
            continue
        for metric in points[name]:
            if metric not in points[args.baseline]:
                continue
            base_value = points[args.baseline][metric]
            model_value = points[name][metric]
            if base_value is None or model_value is None:
                continue
            diffs = [
                improvement(metric, m, b)
                for m, b in zip(samples[name][metric], samples[args.baseline][metric], strict=True)
                if m is not None and b is not None
            ]
            low, high = interval(diffs, args.confidence)
            reading = "inside the noise"
            if low is not None and low > 0:
                reading = "better"
            elif high is not None and high < 0:
                reading = "worse"
            comparisons.append(
                {
                    "model": name,
                    "against": args.baseline,
                    "metric": metric,
                    "difference": round(model_value - base_value, 6),
                    "improvement": round(improvement(metric, model_value, base_value), 6),
                    "low": rounded(low),
                    "high": rounded(high),
                    "share_of_resamples_better": round(sum(1 for d in diffs if d > 0) / max(1, len(diffs)), 4),
                    "reading": reading,
                }
            )
    return report, comparisons, points


# ---------------------------------------------------------------------------- calibration


def calibration_table(labels: list[bool], probabilities: list[float], bins: int, confidence: float) -> dict[str, Any]:
    """Equal-count bins, ties kept together, with a Wilson interval on the observed rate of each bin."""
    ordered = sorted(range(len(labels)), key=lambda i: probabilities[i])
    n = len(ordered)
    target = n / bins
    groups: list[list[int]] = []
    current: list[int] = []
    for position, row in enumerate(ordered):
        current.append(row)
        tied = position + 1 < n and probabilities[ordered[position + 1]] == probabilities[row]
        if not tied and len(current) >= target and len(groups) < bins - 1:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    rows = []
    weighted_gap = 0.0
    outside = 0
    for index, members in enumerate(groups, start=1):
        predicted = sum(probabilities[i] for i in members) / len(members)
        positives = sum(1 for i in members if labels[i])
        observed = positives / len(members)
        low, high = ms.wilson(positives, len(members), confidence)
        inside = low <= predicted <= high
        outside += not inside
        weighted_gap += abs(predicted - observed) * len(members)
        rows.append(
            {
                "bin": index,
                "rows": len(members),
                "mean_predicted": round(predicted, 6),
                "observed": round(observed, 6),
                "observed_low": round(low, 6),
                "observed_high": round(high, 6),
                "gap": round(predicted - observed, 6),
                "inside_interval": inside,
            }
        )
    mean_predicted = sum(probabilities) / n
    base_rate = sum(labels) / n
    limit = max(2, math.ceil(0.25 * len(groups)))
    return {
        "bins": rows,
        "ece": round(weighted_gap / n, 6),
        "bins_outside_interval": outside,
        "mean_predicted": round(mean_predicted, 6),
        "observed_rate": round(base_rate, 6),
        "reading": "miscalibrated" if outside >= limit else "consistent with its probabilities",
        "rule": f"miscalibrated when {limit} or more of {len(groups)} bins have the mean prediction outside the "
        f"{confidence:.0%} interval of the observed rate",
    }


# ---------------------------------------------------------------------------- thresholds


def threshold_rows(ordered: ms.Ordered, labels: list[bool], cost_fp: float, cost_fn: float) -> list[dict[str, Any]]:
    """One row per possible threshold, from acting on nobody to acting on everyone. Act when score >= threshold."""
    positives = sum(labels)
    negatives = len(labels) - positives
    rows = [{"threshold": None, "tp": 0, "fp": 0, "fn": positives, "tn": negatives, "cost": positives * cost_fn}]
    tp = fp = 0
    for position, row in enumerate(ordered.rows):
        if labels[row]:
            tp += 1
        else:
            fp += 1
        if ordered.ends[position]:
            rows.append(
                {
                    "threshold": row,
                    "tp": tp,
                    "fp": fp,
                    "fn": positives - tp,
                    "tn": negatives - fp,
                    "cost": fp * cost_fp + (positives - tp) * cost_fn,
                }
            )
    return rows


def best_on(
    indices: list[int], scores: list[float], labels: list[bool], cost_fp: float, cost_fn: float
) -> float | None:
    """The cheapest threshold on these rows. None means acting on nobody."""
    sub_scores = [scores[i] for i in indices]
    sub_labels = [labels[i] for i in indices]
    rows = threshold_rows(ms.order_scores(sub_scores), sub_labels, cost_fp, cost_fn)
    best = min(rows, key=lambda r: r["cost"])
    return None if best["threshold"] is None else sub_scores[best["threshold"]]


def cost_at(
    indices: list[int], scores: list[float], labels: list[bool], threshold: float | None, cost_fp: float, cost_fn: float
) -> float:
    cost = 0.0
    for i in indices:
        acted = threshold is not None and scores[i] >= threshold
        if acted and not labels[i]:
            cost += cost_fp
        elif not acted and labels[i]:
            cost += cost_fn
    return cost


def threshold_report(model: Model, data: Data, args: argparse.Namespace) -> dict[str, Any]:
    assert model.ordered is not None
    scores = data.scores[model.name]
    n = len(scores)
    cost_fp, cost_fn = args.cost_fp, args.cost_fn
    rows = threshold_rows(model.ordered, data.labels, cost_fp, cost_fn)
    best_index = min(range(len(rows)), key=lambda i: rows[i]["cost"])

    def public(row: dict[str, Any]) -> dict[str, Any]:
        value = None if row["threshold"] is None else scores[row["threshold"]]
        acted = row["tp"] + row["fp"]
        return {
            "threshold": rounded(value),
            "acted_on_share": round(acted / n, 4),
            "tp": row["tp"],
            "fp": row["fp"],
            "fn": row["fn"],
            "tn": row["tn"],
            "precision": round(row["tp"] / acted, 4) if acted else None,
            "recall": round(row["tp"] / (row["tp"] + row["fn"]), 4) if row["tp"] + row["fn"] else None,
            "cost": round(row["cost"], 2),
            "cost_per_1000": round(row["cost"] * 1000 / n, 2),
        }

    rng = random.Random(f"{args.seed}:threshold:{model.name}")
    order = list(range(n))
    for i in range(n - 1, 0, -1):
        j = int(rng.random() * (i + 1))
        order[i], order[j] = order[j], order[i]
    half = n // 2
    first, second = order[:half], order[half:]
    picked_first = best_on(first, scores, data.labels, cost_fp, cost_fn)
    picked_second = best_on(second, scores, data.labels, cost_fp, cost_fn)
    held_out = cost_at(second, scores, data.labels, picked_first, cost_fp, cost_fn) + cost_at(
        first, scores, data.labels, picked_second, cost_fp, cost_fn
    )
    report: dict[str, Any] = {
        "best": public(rows[best_index]),
        "act_on_nobody": public(rows[0]),
        "act_on_everyone": public(rows[-1]),
        "out_of_sample_cost_per_1000": round(held_out * 1000 / n, 2),
    }
    if model.probabilities:
        break_even = cost_fp / (cost_fp + cost_fn)
        at_break_even = cost_at(list(range(n)), scores, data.labels, break_even, cost_fp, cost_fn)
        report["break_even_probability"] = round(break_even, 6)
        report["cost_per_1000_at_break_even"] = round(at_break_even * 1000 / n, 2)
    step = max(1, (len(rows) - 1) // (CURVE_POINTS - 1))
    picks = sorted({*range(0, len(rows), step), len(rows) - 1, best_index})
    report["curve"] = [
        {
            "threshold": rounded(None if rows[i]["threshold"] is None else scores[rows[i]["threshold"]]),
            "acted_on_share": public(rows[i])["acted_on_share"],
            "cost_per_1000": public(rows[i])["cost_per_1000"],
        }
        for i in picks
    ]
    return report


# ---------------------------------------------------------------------------- slices


def slice_metric(data: Data, members: list[int], scores: list[float], weights: list[float] | None) -> float | None:
    if data.task == "classification":
        labels = [data.labels[i] for i in members]
        return ms.rank_sweep(ms.order_scores([scores[i] for i in members]), labels, weights).auc
    residuals = [abs(scores[i] - data.values[i]) for i in members]
    if weights is None:
        return sum(residuals) / len(residuals)
    return float(sum(map(mul, weights, residuals))) / sum(weights)


def slice_report(data: Data, args: argparse.Namespace) -> dict[str, Any]:
    metric = "roc_auc" if data.task == "classification" else "mae"
    higher = direction_of(metric) == HIGHER
    rows: dict[str, list[dict[str, Any]]] = {}
    worst: list[dict[str, Any]] = []
    resamples = min(args.resamples, SLICE_RESAMPLES)
    overall: dict[str, float | None] = {
        name: slice_metric(data, list(range(len(scores))), scores, None) for name, scores in data.scores.items()
    }
    for column, values in data.slices.items():
        rows[column] = []
        groups: dict[str, list[int]] = {}
        for i, value in enumerate(values):
            groups.setdefault(value, []).append(i)
        for value, members in sorted(groups.items()):
            entry: dict[str, Any] = {"value": value, "rows": len(members)}
            if data.task == "classification":
                positives = sum(1 for i in members if data.labels[i])
                entry["positives"] = positives
                too_small = len(members) < MIN_SLICE_ROWS or min(positives, len(members) - positives) < MIN_SLICE_CLASS
            else:
                too_small = len(members) < MIN_SLICE_ROWS
            entry["too_small"] = too_small
            rows[column].append(entry)
            if too_small:
                continue
            remap: dict[int, int] = {}
            clusters = [remap.setdefault(data.clusters[i], len(remap)) for i in members]
            rng = random.Random(f"{args.seed}:slice:{column}:{value}")
            subset = {name: [scores[i] for i in members] for name, scores in data.scores.items()}
            points: dict[str, float | None] = {
                name: slice_metric(data, members, scores, None) for name, scores in data.scores.items()
            }
            orders = {name: ms.order_scores(s) for name, s in subset.items()}
            labels = [data.labels[i] for i in members] if data.task == "classification" else []
            residuals = (
                {
                    name: [abs(s - data.values[i]) for s, i in zip(values_s, members, strict=True)]
                    for name, values_s in subset.items()
                }
                if data.task != "classification"
                else {}
            )
            draws: dict[str, list[float | None]] = {name: [] for name in data.scores}
            for _ in range(resamples):
                weights = ms.bootstrap_weights(rng, clusters, len(remap))
                for name in data.scores:
                    if data.task == "classification":
                        draws[name].append(ms.rank_sweep(orders[name], labels, weights).auc)
                    else:
                        total = sum(weights)
                        draws[name].append(sum(map(mul, weights, residuals[name])) / total)
            entry["models"] = {}
            for name in data.scores:
                defined = [v for v in draws[name] if v is not None]
                low, high = interval(defined, args.confidence)
                point = points[name]
                reference = overall[name]
                gap = (
                    None if point is None or reference is None else (reference - point if higher else point - reference)
                )
                diffs = [
                    (m - b if higher else b - m)
                    for m, b in zip(draws[name], draws[args.baseline], strict=True)
                    if m is not None and b is not None
                ]
                diff_low, diff_high = interval(diffs, args.confidence)
                clearly_worse = bool(
                    low is not None
                    and high is not None
                    and reference is not None
                    and (high < reference if higher else low > reference)
                )
                report = {
                    "value": rounded(point),
                    "low": rounded(low),
                    "high": rounded(high),
                    "shortfall_against_whole_file": rounded(gap),
                    "clearly_worse_than_whole_file": clearly_worse,
                    "against_baseline_low": rounded(diff_low),
                    "against_baseline_high": rounded(diff_high),
                }
                entry["models"][name] = report
                if gap is not None:
                    worst.append(
                        {
                            "model": name,
                            "column": column,
                            "value": value,
                            "rows": len(members),
                            metric: rounded(point),
                            "low": rounded(low),
                            "high": rounded(high),
                            "whole_file": rounded(reference),
                            "shortfall": rounded(gap),
                            "clearly_worse": clearly_worse,
                        }
                    )
    ranked_pairs = len(worst)
    worst.sort(key=lambda r: -(r["shortfall"] or 0.0))
    per_model: dict[str, list[dict[str, Any]]] = {}
    for row in worst:
        per_model.setdefault(row["model"], [])
        if len(per_model[row["model"]]) < args.worst:
            per_model[row["model"]].append(row)
    return {
        "metric": metric,
        "resamples": resamples,
        "by_column": rows,
        "worst": per_model,
        "note": f"{ranked_pairs} slice and model pairs were ranked: at 95% intervals about one in twenty can look "
        "clearly worse by chance, so check a single mild flag before acting on it.",
        "rule": f"a slice needs at least {MIN_SLICE_ROWS} rows and {MIN_SLICE_CLASS} of each class to be ranked; "
        "shortfall is against the whole file; clearly worse means the slice's whole interval is below the whole file's "
        "value",
    }


def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    data = load(args)
    models = {name: build_model(name, data) for name in args.model_list}
    primary = args.primary or ("roc_auc" if data.task == "classification" else "mae")
    known = METRICS[data.task]
    if primary != "cost_per_1000" and primary not in known:
        raise SystemExit(f"--primary must be one of: {', '.join(known)}")
    if primary == "cost_per_1000" and args.cost_fp is None:
        raise SystemExit("--primary cost_per_1000 needs --cost-fp and --cost-fn")
    samples = bootstrap(models, data, args)
    report, comparisons, _ = overall_report(models, data, args, samples)
    result: dict[str, Any] = {
        "task": data.task,
        "seed": args.seed,
        "resamples": args.resamples,
        "confidence": args.confidence,
        "read": data.read,
        "primary_metric": primary,
        "baseline": args.baseline,
        "models": report,
        "comparisons": comparisons,
        "primary_reading": {
            c["model"]: {"reading": c["reading"], "improvement": c["improvement"], "low": c["low"], "high": c["high"]}
            for c in comparisons
            if c["metric"] == primary
        },
    }
    notes: list[str] = []
    if data.read["repeated_ids"]:
        notes.append(
            f"{data.read['repeated_ids']} rows share an id with another row: the rows of an id are resampled together."
        )
    if len(args.model_list) > 4:
        notes.append("Many models against one baseline: the best of several is flattered by the choosing itself.")
    if data.task == "classification":
        not_probabilities = [m.name for m in models.values() if not m.probabilities]
        if not_probabilities:
            notes.append(
                f"{', '.join(not_probabilities)}: scores outside 0..1, so only ranking metrics are computed for them."
            )
        result["calibration"] = {
            m.name: calibration_table(data.labels, data.scores[m.name], args.bins, args.confidence)
            for m in models.values()
            if m.probabilities
        }
        if args.cost_fp is not None:
            result["costs"] = {"false_positive": args.cost_fp, "false_negative": args.cost_fn}
            result["thresholds"] = {m.name: threshold_report(m, data, args) for m in models.values()}
    if data.slices:
        result["slices"] = slice_report(data, args)
    if notes:
        result["notes"] = notes
    return result


def main(argv: list[str] | None = None) -> int:
    args = read_args(argv)
    json.dump(evaluate(args), sys.stdout, indent=1, ensure_ascii=False)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
