#!/usr/bin/env python3
"""Audit a training set before anyone trusts a model built on it.

Usage: python3 dataset_audit.py --train TRAIN.csv --test TEST.csv --label LABEL
                                [--valid FILE] [--positive VALUE] [--id COLUMN] [--entity COLUMN]
                                [--time COLUMN] [--label-time COLUMN] [--horizon-days N]
                                [--exclude COLUMN[,COLUMN]] [--seed N] [--max-rows N]
       python3 dataset_audit.py --data FILE --split-column COLUMN --label LABEL ...
                                [--train-value train --test-value test --valid-value valid]

Files are CSV or JSON Lines. The checks: target leakage (how well one feature alone predicts the label, whether a
value is present only for one class, names that suggest an outcome), time leakage (a feature dated after the moment
of the prediction, the order of the splits, labels that end after the test period begins), the same entity on both
sides of a split, exact duplicates across splits, class balance, missingness that differs by class, drift between
train and test (population stability index) and personal columns.

`--id` is a row id: it is left out when rows are compared for duplicates. `--entity` is the customer or other thing a
row belongs to. `--time` is the moment the prediction is made; a feature dated later than that was not known then.
`--horizon-days` is how long after `--time` the label is decided.

It prints columns and counts, never a value of a row, so nothing here can reveal a personal value. Numeric strength is
rank based, so a monotone transform does not hide a leak. Read-only, standard library only, JSON on stdout.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from itertools import combinations
from pathlib import Path
from typing import Any

# The other scripts of this pack are copies in the same folder.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import data_profile
import measure
import model_stats as ms

LOW_CARDINALITY = 10
ID_LIKE_SHARE = 0.5
MISSING_GAP = 0.05
RARE_CLASS = 0.05


@dataclass
class Split:
    name: str
    rows: list[measure.Row]
    labels: list[bool]
    rows_read: int
    no_label: int


def read_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit a training set before anyone trusts a model built on it.")
    parser.add_argument("--train", type=Path)
    parser.add_argument("--test", type=Path)
    parser.add_argument("--valid", type=Path)
    parser.add_argument("--data", type=Path, help="one file with a split column, instead of --train and --test")
    parser.add_argument("--split-column")
    parser.add_argument("--train-value", default="train")
    parser.add_argument("--test-value", default="test")
    parser.add_argument("--valid-value", default="valid")
    parser.add_argument("--label", required=True)
    parser.add_argument("--positive", help="the label value that means positive, unless it is 1/0, true/false, yes/no")
    parser.add_argument("--id", dest="row_id")
    parser.add_argument("--entity")
    parser.add_argument("--time")
    parser.add_argument("--label-time")
    parser.add_argument("--horizon-days", type=int)
    parser.add_argument("--exclude", default="", help="columns that are not features, comma separated")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--max-rows", type=int, default=data_profile.MAX_ROWS)
    args = parser.parse_args(argv)
    if args.data is None and (args.train is None or args.test is None):
        parser.error("give --train and --test, or --data with --split-column")
    if args.data is not None and args.split_column is None:
        parser.error("--data needs --split-column")
    return args


def make_split(name: str, rows: list[measure.Row], label: str, positive: str | None) -> Split:
    kept: list[measure.Row] = []
    labels: list[bool] = []
    no_label = 0
    for row in rows:
        value = ms.parse_binary(row[label], positive)
        if value is None:
            no_label += 1
            continue
        kept.append(row)
        labels.append(value)
    return Split(name, kept, labels, len(rows), no_label)


def load_splits(args: argparse.Namespace) -> tuple[dict[str, Split], list[str], dict[str, str]]:
    """The splits, the header of the first one and every personal column found in any of them, with its kind."""
    tables: dict[str, measure.Table] = {}
    if args.data is not None:
        whole = measure.load(args.data, args.max_rows)
        measure.check_columns(whole, [args.split_column])
        wanted = {args.train_value: "train", args.test_value: "test", args.valid_value: "valid"}
        grouped: dict[str, list[measure.Row]] = {}
        for row in whole.rows:
            name = wanted.get(row[args.split_column] or "")
            if name:
                grouped.setdefault(name, []).append(row)
        for name in ("train", "test"):
            if name not in grouped:
                raise SystemExit(f"--split-column {args.split_column}: no rows for the {name} split")
        for name, rows in grouped.items():
            tables[name] = measure.Table(name, args.data, whole.header, rows, len(rows), whole.notes, whole.personal)
    else:
        for name, path in (("train", args.train), ("test", args.test), ("valid", args.valid)):
            if path is not None:
                tables[name] = measure.load(path, args.max_rows)
    header = tables["train"].header
    personal: dict[str, str] = {}
    for table in tables.values():
        personal.update(table.personal)
        measure.check_columns(table, [args.label])
        measure.check_public(table, [args.label], "the label")
        for column, role in ((args.time, "the time column"), (args.label_time, "the label time")):
            if column:
                measure.check_public(table, [column], role)
    if args.entity:
        measure.check_columns(tables["train"], [args.entity])
    if args.row_id:
        measure.check_columns(tables["train"], [args.row_id])
    splits = {n: make_split(n, t.rows, args.label, args.positive) for n, t in tables.items()}
    return splits, header, personal


def column_kind(values: list[str | None]) -> str:
    """numeric, categorical, date, id-like or empty. Numbers with very few distinct values count as categories."""
    present = [v for v in values if v is not None]
    if not present:
        return "empty"
    distinct = len(set(present))
    if sum(1 for v in present if ms.to_float(v) is not None) >= 0.95 * len(present):
        return "numeric" if distinct > LOW_CARDINALITY else "categorical"
    if sum(1 for v in present if measure.day(v) is not None) >= 0.95 * len(present):
        return "date"
    return "id-like" if distinct > max(50, ID_LIKE_SHARE * len(present)) else "categorical"


def feature_strength(
    name: str, kind: str, values: list[str | None], labels: list[bool], rng: random.Random
) -> dict[str, Any]:
    """How well this one feature predicts the label on its own, and how much of that is whether it is present at all."""
    presence = ms.strongest(ms.roc_auc(labels, [0.0 if v is None else 1.0 for v in values]))
    if kind == "categorical":
        strength = ms.strongest(ms.roc_auc(labels, ms.out_of_fold_rates(values, labels, rng)))
        via = "category rates (out of fold)"
    else:
        if kind == "date":
            parsed = [measure.day(v) for v in values]
            pairs = [(float(d.toordinal()), y) for d, y in zip(parsed, labels, strict=True) if d is not None]
        else:
            numbers = [ms.to_float(v) for v in values]
            pairs = [(n, y) for n, y in zip(numbers, labels, strict=True) if n is not None]
        strength = ms.strongest(ms.roc_auc([y for _, y in pairs], [v for v, _ in pairs]))
        via = "rank (AUC) of the values"
    if presence is not None and (strength is None or presence > strength):
        strength, via = presence, "whether the value is present at all"
    return {
        "feature": name,
        "kind": kind,
        "strength": None if strength is None else round(strength, 4),
        "via": via,
        "present_share": round(sum(1 for v in values if v is not None) / len(values), 4),
        "flag": flag_of(strength),
        "name_suggests_outcome": ms.OUTCOME_NAME.search(name) is not None,
    }


def flag_of(strength: float | None) -> str | None:
    if strength is None or strength < ms.SUSPICIOUS:
        return None
    return "almost perfect" if strength >= ms.ALMOST_PERFECT else "suspiciously strong"


def days_after(rows: list[measure.Row], column: str, reference: str) -> list[int]:
    """For each row where the column is dated after the reference, by how many days. Calendar days, never hours: a
    datetime on the snapshot day itself is not a leak."""
    gaps = []
    for row in rows:
        left, right = measure.day(row[column]), measure.day(row[reference])
        if left is not None and right is not None and left > right:
            gaps.append((left - right).days)
    return gaps


def split_dates(rows: list[measure.Row], column: str) -> list[date]:
    return sorted(d for d in (measure.day(r[column]) for r in rows) if d is not None)


def time_leakage(
    splits: dict[str, Split],
    date_features: list[str],
    moment: str | None,
    label_time: str | None,
    horizon_days: int | None,
) -> dict[str, Any]:
    result: dict[str, Any] = {"after_prediction_moment": [], "after_label_time": []}
    if moment:
        for feature in date_features:
            for name, split in splits.items():
                gaps = days_after(split.rows, feature, moment)
                if gaps:
                    result["after_prediction_moment"].append(
                        {
                            "column": feature,
                            "split": name,
                            "rows": len(gaps),
                            "share_of_split": round(len(gaps) / max(1, len(split.rows)), 4),
                            "max_days_after": max(gaps),
                        }
                    )
    if label_time:
        for feature in date_features:
            for name, split in splits.items():
                gaps = days_after(split.rows, feature, label_time)
                if gaps:
                    result["after_label_time"].append({"column": feature, "split": name, "rows": len(gaps)})
    if moment and "test" in splits:
        train, test = split_dates(splits["train"].rows, moment), split_dates(splits["test"].rows, moment)
        if train and test:
            not_after = sum(1 for d in test if d <= train[-1])
            order: dict[str, Any] = {
                "train_first": train[0].isoformat(),
                "train_last": train[-1].isoformat(),
                "test_first": test[0].isoformat(),
                "test_last": test[-1].isoformat(),
                "test_rows_on_or_before_train_last": not_after,
                "train_before_test": not_after == 0,
            }
            if horizon_days is not None:
                # A few test rows dated inside the train window must not move the cut for every train row.
                after = [d for d in test if d > train[-1]]
                start = after[0] if after else test[0]
                order["test_start_for_labels"] = start.isoformat()
                order["train_rows_with_labels_after_test_start"] = sum(
                    1 for d in train if d + timedelta(days=horizon_days) > start
                )
                order["horizon_days"] = horizon_days
            result["split_order"] = order
    return result


def entity_overlap(splits: dict[str, Split], entity: str | None) -> list[dict[str, Any]]:
    if not entity:
        return []
    results = []
    for first, second in combinations(splits, 2):
        a = {r[entity] for r in splits[first].rows if r[entity] is not None}
        b = [r[entity] for r in splits[second].rows if r[entity] is not None]
        shared = a & set(b)
        results.append(
            {
                "sides": [first, second],
                "shared_entities": len(shared),
                "entities_in_first": len(a),
                "entities_in_second": len(set(b)),
                "rows_of_second_with_a_shared_entity": sum(1 for v in b if v in shared),
                "share_of_rows_of_second": round(sum(1 for v in b if v in shared) / max(1, len(b)), 4),
            }
        )
    return results


def duplicates(splits: dict[str, Split], header: list[str], row_id: str | None) -> dict[str, Any]:
    """Rows identical in every column but the row id, inside each split and across pairs of splits."""
    columns = [c for c in header if c != row_id]
    keys = {name: Counter(tuple(r.get(c) for c in columns) for r in s.rows) for name, s in splits.items()}
    within = {name: sum(c - 1 for c in counts.values() if c > 1) for name, counts in keys.items()}
    across = []
    for first, second in combinations(splits, 2):
        rows = sum(n for key, n in keys[second].items() if key in keys[first])
        across.append({"sides": [first, second], "rows_of_second_also_in_first": rows})
    return {"within": within, "across": across, "compared_columns": len(columns)}


def class_balance(splits: dict[str, Split]) -> dict[str, Any]:
    result: dict[str, Any] = {"by_split": {}, "rare_class": False, "splits_differ": False, "test": None}
    for name, split in splits.items():
        positives = sum(split.labels)
        rate = positives / len(split.labels) if split.labels else 0.0
        result["by_split"][name] = {
            "rows": len(split.labels),
            "positives": positives,
            "rate": round(rate, 4),
        }
        if min(rate, 1 - rate) < RARE_CLASS:
            result["rare_class"] = True
    train = result["by_split"]["train"]
    test = result["by_split"].get("test")
    if test and train["rows"] and test["rows"]:
        comparison = ms.two_proportions(train["positives"], train["rows"], test["positives"], test["rows"])
        result["test"] = {"difference": round(comparison.difference, 4), "p_value": round(comparison.p_value, 6)}
        result["splits_differ"] = comparison.p_value < 0.001
    return result


def missing_by_class(features: list[str], split: Split, kinds: dict[str, str]) -> list[dict[str, Any]]:
    """Missing share among positives and among negatives of the training split, with a corrected test per column."""
    rows: list[dict[str, Any]] = []
    positives = sum(split.labels)
    negatives = len(split.labels) - positives
    for feature in features:
        if kinds[feature] == "empty" or positives == 0 or negatives == 0:
            continue
        missing_pos = sum(1 for r, y in zip(split.rows, split.labels, strict=True) if y and r[feature] is None)
        missing_neg = sum(1 for r, y in zip(split.rows, split.labels, strict=True) if not y and r[feature] is None)
        comparison = ms.two_proportions(missing_neg, negatives, missing_pos, positives)
        rows.append(
            {
                "feature": feature,
                "missing_share_positive": round(missing_pos / positives, 4),
                "missing_share_negative": round(missing_neg / negatives, 4),
                "difference": round(comparison.difference, 4),
                "p_value": round(comparison.p_value, 6),
            }
        )
    adjusted = ms.holm([row["p_value"] for row in rows])
    for row, adj in zip(rows, adjusted, strict=True):
        row["adjusted_p"] = round(adj, 6)
        row["differs"] = adj < 0.05 and abs(row["difference"]) >= MISSING_GAP
    rows.sort(key=lambda r: -abs(r["difference"]))
    return rows


def drift(features: list[str], kinds: dict[str, str], splits: dict[str, Split]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    base = splits["train"]
    for feature in features:
        kind = kinds[feature]
        if kind not in ("numeric", "categorical"):
            continue
        for name, split in splits.items():
            if name == "train" or not split.rows or feature not in split.rows[0]:
                continue
            if kind == "numeric":
                value = ms.numeric_psi(
                    [ms.to_float(r[feature]) for r in base.rows], [ms.to_float(r[feature]) for r in split.rows]
                )
            else:
                value = ms.categorical_psi([r[feature] for r in base.rows], [r[feature] for r in split.rows])
            if value is not None:
                rows.append({"feature": feature, "against": name, "psi": round(value, 4), "band": ms.psi_band(value)})
    rows.sort(key=lambda r: -r["psi"])
    return rows


def problems_of(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Every check that did not pass, as one list, the worst first."""
    found: list[dict[str, Any]] = []

    def add(severity: str, check: str, what: str, columns: list[str] | None = None) -> None:
        found.append({"severity": severity, "check": check, "what": what, "columns": columns or []})

    for row in result["target_leakage"]:
        if row["flag"] == "almost perfect":
            add(
                "high",
                "target leakage",
                f"{row['feature']} predicts the label almost perfectly on its own "
                f"(strength {row['strength']}, via {row['via']}).",
                [row["feature"]],
            )
        elif row["flag"] == "suspiciously strong":
            add(
                "medium",
                "target leakage",
                f"{row['feature']} is unusually strong on its own (strength "
                f"{row['strength']}, via {row['via']}): read where it comes from.",
                [row["feature"]],
            )
    time = result["time_leakage"]
    for row in time["after_prediction_moment"]:
        add(
            "high",
            "time leakage",
            f"{row['column']} is dated after the prediction moment on {row['rows']} rows of {row['split']}.",
            [row["column"]],
        )
    for row in time["after_label_time"]:
        add(
            "high",
            "time leakage",
            f"{row['column']} is dated after the label is known on {row['rows']} rows of {row['split']}.",
            [row["column"]],
        )
    order = time.get("split_order")
    if order and not order["train_before_test"]:
        add(
            "high",
            "time leakage",
            f"{order['test_rows_on_or_before_train_last']} test rows are dated on or before the "
            "last training day: the test set is not fully after the training set.",
        )
    if order and order.get("train_rows_with_labels_after_test_start"):
        add(
            "medium",
            "time leakage",
            f"{order['train_rows_with_labels_after_test_start']} train rows have labels that end "
            "after the test period begins.",
        )
    for pair in result["entity_overlap"]:
        if pair["shared_entities"]:
            add(
                "high",
                "same entity on both sides",
                f"{pair['shared_entities']} entities are in both {pair['sides'][0]} "
                f"and {pair['sides'][1]} ({pair['rows_of_second_with_a_shared_entity']} rows of {pair['sides'][1]}).",
            )
    dup = result["duplicates"]
    for pair in dup["across"]:
        if pair["rows_of_second_also_in_first"]:
            add(
                "high",
                "duplicates across splits",
                f"{pair['rows_of_second_also_in_first']} rows of {pair['sides'][1]} are "
                f"exact copies of rows in {pair['sides'][0]}.",
            )
    for name, count in dup["within"].items():
        if count:
            add("medium", "duplicates within a split", f"{name} has {count} exact duplicate rows.")
    for row in result["missing_by_class"]:
        if row["differs"]:
            add(
                "medium",
                "missingness differs by class",
                f"{row['feature']} is missing for {row['missing_share_positive']:.1%} of positives and "
                f"{row['missing_share_negative']:.1%} of negatives.",
                [row["feature"]],
            )
    for row in result["drift"]:
        if row["band"] == "major":
            add(
                "medium",
                "drift",
                f"{row['feature']} shifted between train and {row['against']}: PSI {row['psi']}.",
                [row["feature"]],
            )
        elif row["band"] == "moderate":
            add(
                "low",
                "drift",
                f"{row['feature']} moved somewhat between train and {row['against']}: PSI {row['psi']}.",
                [row["feature"]],
            )
    balance = result["class_balance"]
    if balance["rare_class"]:
        add("low", "class balance", "The rarer class is under 5% of a split: judge the model on PR-AUC and costs.")
    if balance["splits_differ"]:
        add("medium", "class balance", "The positive rate differs between train and test.")
    if result["personal_columns"]:
        columns = [c["column"] for c in result["personal_columns"]]
        add(
            "medium",
            "personal columns",
            f"{len(columns)} columns hold personal data: drop them before training.",
            columns,
        )
    rank = {"high": 0, "medium": 1, "low": 2}
    found.sort(key=lambda p: rank[p["severity"]])
    return found


def audit(args: argparse.Namespace) -> dict[str, Any]:
    splits, header, personal = load_splits(args)
    train = splits["train"]
    if not train.labels:
        raise SystemExit("the training split has no rows with a usable label")
    excluded = {c.strip() for c in args.exclude.split(",") if c.strip()}
    reserved = {args.label, args.row_id, args.entity, args.time, args.label_time, args.split_column} | excluded
    candidates = [c for c in header if c not in reserved and c not in personal]
    kinds = {c: column_kind([r[c] for r in train.rows]) for c in candidates}
    rng = random.Random(args.seed)
    strength = [
        feature_strength(c, kinds[c], [r[c] for r in train.rows], train.labels, rng)
        for c in candidates
        if kinds[c] in ("numeric", "categorical", "date")
    ]
    strength.sort(key=lambda r: -(r["strength"] or 0.0))
    date_features = [c for c in candidates if kinds[c] == "date"]
    features = [c for c in candidates if kinds[c] in ("numeric", "categorical")]
    result: dict[str, Any] = {
        "seed": args.seed,
        "splits": {
            n: {"rows_read": s.rows_read, "rows_with_a_label": len(s.rows), "rows_without_a_label": s.no_label}
            for n, s in splits.items()
        },
        "personal_columns": [{"column": c, "kind": k} for c, k in sorted(personal.items())],
        "features": {
            "checked": [c for c in candidates if kinds[c] != "id-like" and kinds[c] != "empty"],
            "id_like_not_checked": [c for c in candidates if kinds[c] == "id-like"],
            "empty_in_train": [c for c in candidates if kinds[c] == "empty"],
            "excluded": sorted(excluded & set(header)),
            "personal_not_checked": sorted(set(personal) & set(header)),
        },
        "target_leakage": strength,
        "time_leakage": time_leakage(splits, date_features, args.time, args.label_time, args.horizon_days),
        "entity_overlap": entity_overlap(splits, args.entity),
        "duplicates": duplicates(splits, header, args.row_id),
        "class_balance": class_balance(splits),
        "missing_by_class": missing_by_class(features + date_features, train, kinds),
        "drift": drift(features, kinds, splits) if len(splits) > 1 else [],
    }
    problems = problems_of(result)
    result["problems"] = problems
    result["verdict"] = (
        "do not trust yet"
        if any(p["severity"] == "high" for p in problems)
        else "fix these first"
        if any(p["severity"] == "medium" for p in problems)
        else "no blocking problem found"
    )
    result["limits"] = [
        "A feature computed over a window past the prediction moment is invisible in the values: read the code.",
        "Strength looks at one feature at a time: two features that leak only together are not found.",
        "PSI compares two samples; it says a distribution moved, not whether the model cares.",
    ]
    return result


def main(argv: list[str] | None = None) -> int:
    args = read_args(argv)
    json.dump(audit(args), sys.stdout, indent=1, ensure_ascii=False)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
