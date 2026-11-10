#!/usr/bin/env python3
"""Explore one table before a predictive model is built: what relates to the target and what would break a model.

Usage: python3 explore_target.py --data FILE --label LABEL [--positive VALUE] [--id COLUMN] [--entity COLUMN]
                                 [--time COLUMN] [--horizon-days N] [--period month|week]
                                 [--exclude COLUMN[,COLUMN]] [--bootstrap N] [--seed N] [--max-rows N]

The file is CSV or JSON Lines, with a yes/no target. It reports the target's rate overall and per period; whether the
newest rows' labels can be known yet; each feature's distribution, odd codes for unknown values and outliers; how
strongly each feature alone relates to the target, with a seeded bootstrap interval and a test corrected across all
features; the shape of the relation for numbers; segments whose rate differs after correction; whether a missing value
carries signal; redundant features; and columns to check for leakage.

`--time` is the moment the prediction is made. `--horizon-days` is how long after it the label is decided, and the last
date in the file is taken as the day of the extract. `--entity` is the customer a row belongs to: resampling moves all
of an entity's rows together.

Column names and counts only. Category levels are printed for columns with few levels, are numbered instead of named
when the column's name suggests people, and a personal column is left out altogether. Read-only, standard library only,
JSON on stdout.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys
from bisect import bisect_left
from collections import Counter
from collections.abc import Sequence
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

Group = tuple[int, int]  # positives, rows

BINS_LARGE = 10
BINS_SMALL = 5
BINS_LARGE_FROM = 2000
MAX_LEVELS_NAMED = 30
MAX_LEVELS_SHOWN = 12
ID_LIKE_SHARE = 0.5
ID_LIKE_FROM = 50
MIN_EXPECTED = 5.0
MIN_PERIOD_ROWS = 30
MIN_SEGMENT_ROWS = 30
MIN_SEGMENT_GAP = 0.02
MISSING_RATE_GAP = 0.02
RARE_LEVEL = 0.01
RARE_LEVELS_MATTER = 0.05
NEAR_CONSTANT = 0.99
MOSTLY_ZERO = 0.5
HEAVY_TAIL = 2.0
OUTLIER_FENCE = 3.0
OUTLIERS_MATTER = 0.01
SENTINEL_MIN_ROWS = 5
SENTINEL_MIN_SHARE = 0.005
NOT_MONOTONE_GAP = 0.03
REDUNDANT = 0.9
ALL_ONE_CLASS_ROWS = 20
FILLED_FOR_ONE_CLASS_ROWS = 10
RARE_CLASS = 0.05
ALPHA = 0.05
PAIRS_MAX_ROWS = 20_000
PAIRS_MAX_COLUMNS = 60
BOOTSTRAP_FULL_ROWS = 20_000
BOOTSTRAP_MIN = 50
PEOPLE_NAME = re.compile(
    r"manager|owner|agent|assignee|employee|advisor|adviser|consultant|operator|salesperson|cashier|driver|doctor|nurse"
    r"|teacher|username|(^|_)(rep|user|name|staff|seller)(_|$)",
    re.I,
)


@dataclass
class Data:
    table: measure.Table
    rows: list[measure.Row]
    labels: list[bool]
    no_label: int
    clusters: list[int]
    n_clusters: int


def read_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Explore one table before a predictive model is built.")
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--positive", help="the label value that means yes, unless it is 1/0, true/false, yes/no")
    parser.add_argument("--id", dest="row_id")
    parser.add_argument("--entity")
    parser.add_argument("--time")
    parser.add_argument("--horizon-days", type=int)
    parser.add_argument("--period", choices=("month", "week"), default="month")
    parser.add_argument("--exclude", default="", help="columns that are not features, comma separated")
    parser.add_argument("--bootstrap", type=int, default=200)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--max-rows", type=int, default=data_profile.MAX_ROWS)
    args = parser.parse_args(argv)
    if args.horizon_days is not None and args.time is None:
        parser.error("--horizon-days needs --time")
    return args


def load_data(args: argparse.Namespace) -> Data:
    table = measure.load(args.data, args.max_rows)
    measure.check_public(table, [args.label], "the label")
    if args.time:
        measure.check_public(table, [args.time], "the time column")
    measure.check_columns(table, [c for c in (args.entity, args.row_id) if c])
    rows: list[measure.Row] = []
    labels: list[bool] = []
    for row in table.rows:
        value = ms.parse_binary(row[args.label], args.positive)
        if value is not None:
            rows.append(row)
            labels.append(value)
    no_label = len(table.rows) - len(rows)
    if not rows or (args.positive is None and no_label > len(table.rows) / 2):
        raise SystemExit(
            f"{args.label} does not read as yes/no ({len(rows)} of {len(table.rows)} rows do). "
            "Name the value that means yes with --positive. A numeric target is not covered by this script."
        )
    if all(labels) or not any(labels):
        raise SystemExit(f"{args.label} has only one class in {len(rows)} rows; there is nothing to relate it to")
    clusters, n_clusters = make_clusters(rows, args.entity)
    return Data(table, rows, labels, no_label, clusters, n_clusters)


def make_clusters(rows: list[measure.Row], entity: str | None) -> tuple[list[int], int]:
    """One cluster per entity, one per row when there is no entity or a row's entity is empty."""
    if not entity:
        return list(range(len(rows))), len(rows)
    ids: dict[str, int] = {}
    clusters: list[int] = []
    next_free = 0
    for row in rows:
        key = row[entity]
        if key is None:
            clusters.append(next_free)
            next_free += 1
            continue
        if key not in ids:
            ids[key] = next_free
            next_free += 1
        clusters.append(ids[key])
    return clusters, next_free


def kind_of(values: Sequence[str | None]) -> str:
    """empty, constant, numeric, date, id-like or category. A number with two values is a category."""
    present = [v for v in values if v is not None]
    if not present:
        return "empty"
    distinct = len(set(present))
    if distinct == 1:
        # One value and some blanks is a yes/no in disguise and can be a perfect leak; with no blanks it is constant.
        return "constant" if len(present) == len(values) else "category"
    if sum(1 for v in present if ms.to_float(v) is not None) >= 0.95 * len(present):
        return "numeric" if distinct > 2 else "category"
    if sum(1 for v in present if measure.day(v) is not None) >= 0.95 * len(present):
        return "date"
    return "id-like" if distinct > max(ID_LIKE_FROM, ID_LIKE_SHARE * len(present)) else "category"


# ---------------------------------------------------------------------------- counting helpers


def rate_of(positives: int, rows: int) -> dict[str, Any]:
    low, high = ms.wilson(positives, rows)
    return {
        "rows": rows,
        "positives": positives,
        "rate": round(positives / rows, 4) if rows else None,
        "interval": [round(low, 4), round(high, 4)],
    }


def group_counts(keys: Sequence[Any], labels: Sequence[bool]) -> dict[Any, Group]:
    counts: dict[Any, list[int]] = {}
    for key, label in zip(keys, labels, strict=True):
        entry = counts.setdefault(key, [0, 0])
        entry[0] += int(label)
        entry[1] += 1
    return {key: (entry[0], entry[1]) for key, entry in counts.items()}


def chi_square(groups: Sequence[Group]) -> tuple[float, int, float | None]:
    """Chi-square of group against label, no continuity correction: statistic, degrees of freedom and p-value."""
    positives = sum(g[0] for g in groups)
    rows = sum(g[1] for g in groups)
    if len(groups) < 2 or positives == 0 or positives == rows:
        return 0.0, 0, None
    rate = positives / rows
    statistic = 0.0
    for group_positives, group_rows in groups:
        expected = group_rows * rate
        statistic += (group_positives - expected) ** 2 / expected
        statistic += (group_positives - expected) ** 2 / (group_rows - expected)
    degrees = len(groups) - 1
    return statistic, degrees, ms.chi_square_sf(statistic, degrees)


def rank_test(labels: Sequence[bool], values: Sequence[float], auc: float | None) -> float | None:
    """Two-sided p-value of the Mann-Whitney test, read from the AUC, with the correction for ties."""
    positives = sum(labels)
    negatives = len(labels) - positives
    total = positives + negatives
    if auc is None or positives == 0 or negatives == 0:
        return None
    ties = sum(t**3 - t for t in Counter(values).values())
    variance = positives * negatives / 12 * (total + 1 - ties / (total * (total - 1)))
    if variance <= 0:
        return None
    p_value: float = ms.two_sided_p((auc - 0.5) * positives * negatives / math.sqrt(variance))
    return p_value


def merge_small(groups: Sequence[Group], base_rate: float) -> list[Group]:
    """Pool the groups too small for a chi-square test, so that every expected count is at least MIN_EXPECTED."""

    def small(group: Group) -> bool:
        return min(group[1] * base_rate, group[1] * (1 - base_rate)) < MIN_EXPECTED

    kept = [g for g in groups if not small(g)]
    pooled = (sum(g[0] for g in groups if small(g)), sum(g[1] for g in groups if small(g)))
    if pooled[1] == 0:
        return kept
    if not small(pooled):
        return [*kept, pooled]
    if not kept:
        return [pooled]
    kept.sort(key=lambda g: g[1])
    first = kept[0]
    return [(first[0] + pooled[0], first[1] + pooled[1]), *kept[1:]]


def average_ranks(values: Sequence[float]) -> list[float]:
    """Ranks from 1, ties sharing their average."""
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start
        while end + 1 < len(order) and values[order[end + 1]] == values[order[start]]:
            end += 1
        shared = (start + end) / 2 + 1
        for position in range(start, end + 1):
            ranks[order[position]] = shared
        start = end + 1
    return ranks


def pearson(a: Sequence[float], b: Sequence[float]) -> float | None:
    n = len(a)
    if n < 3:
        return None
    mean_a, mean_b = sum(a) / n, sum(b) / n
    cross = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b, strict=True))
    spread_a = sum((x - mean_a) ** 2 for x in a)
    spread_b = sum((y - mean_b) ** 2 for y in b)
    if spread_a == 0 or spread_b == 0:
        return None
    return cross / math.sqrt(spread_a * spread_b)


def spearman(a: Sequence[float | None], b: Sequence[float | None]) -> float | None:
    pairs = [(x, y) for x, y in zip(a, b, strict=True) if x is not None and y is not None]
    return pearson(average_ranks([x for x, _ in pairs]), average_ranks([y for _, y in pairs]))


def cramers_v(a: Sequence[str | None], b: Sequence[str | None]) -> float | None:
    pairs = [(x, y) for x, y in zip(a, b, strict=True) if x is not None and y is not None]
    if not pairs:
        return None
    left, right, joint = Counter(x for x, _ in pairs), Counter(y for _, y in pairs), Counter(pairs)
    smaller = min(len(left), len(right)) - 1
    if smaller < 1:
        return None
    n = len(pairs)
    statistic = 0.0
    for x, x_count in left.items():
        for y, y_count in right.items():
            expected = x_count * y_count / n
            statistic += (joint.get((x, y), 0) - expected) ** 2 / expected
    return math.sqrt(statistic / (n * smaller))


def correlation_ratio(groups: Sequence[str | None], numbers: Sequence[float | None]) -> float | None:
    """Eta, on ranks so one extreme value cannot decide it: 1 if the group fixes the number, 0 if it says nothing."""
    pairs = [(g, x) for g, x in zip(groups, numbers, strict=True) if g is not None and x is not None]
    if len(pairs) < 3:
        return None
    ranks = average_ranks([x for _, x in pairs])
    grand = sum(ranks) / len(ranks)
    total = sum((r - grand) ** 2 for r in ranks)
    if total == 0:
        return None
    members: dict[str, list[float]] = {}
    for (group, _), rank in zip(pairs, ranks, strict=True):
        members.setdefault(group, []).append(rank)
    between = sum(len(v) * (sum(v) / len(v) - grand) ** 2 for v in members.values())
    return math.sqrt(between / total)


def skewness(values: Sequence[float]) -> float | None:
    """The third standardised moment."""
    n = len(values)
    if n < 3:
        return None
    mean = sum(values) / n
    second = sum((v - mean) ** 2 for v in values) / n
    if second == 0:
        return None
    return float((sum((v - mean) ** 3 for v in values) / n) / second**1.5)


def find_sentinels(values: Sequence[float]) -> list[float]:
    """Values that look like a code for unknown: a spike at the very top far above the rest, or the only negative value.

    A cap at the top of a distribution has no gap below it and a natural tail has no spike, so neither is flagged.
    """
    counts = Counter(values)
    ordered = sorted(counts)
    if len(ordered) < 3:
        return []
    enough = max(SENTINEL_MIN_ROWS, SENTINEL_MIN_SHARE * len(values))
    found: list[float] = []
    top, below = ordered[-1], ordered[-2]
    if counts[top] >= enough and counts[top] > counts[below] and below > 0 and top >= 2 * below:
        found.append(top)
    low, above = ordered[0], ordered[1]
    if counts[low] >= enough and low < 0 <= above:
        found.append(low)
    return found


def plain(value: float, places: int = 4) -> int | float:
    rounded = round(value, places)
    return int(rounded) if rounded == int(rounded) else rounded


# ---------------------------------------------------------------------------- one feature


def interval_of(
    scores: Sequence[float], labels: Sequence[bool], clusters: Sequence[int], draws: int, seed: int, higher: bool
) -> list[float] | None:
    """A percentile bootstrap of the signed AUC, turned the way the point estimate runs."""
    remap: dict[int, int] = {}
    local = [remap.setdefault(c, len(remap)) for c in clusters]
    ordered = ms.order_scores(scores)
    rng = random.Random(seed)
    results: list[float] = []
    for _ in range(draws):
        auc = ms.rank_sweep(ordered, labels, ms.bootstrap_weights(rng, local, len(remap))).auc
        if auc is not None:
            results.append(auc if higher else 1 - auc)
    if not results:
        return None
    results.sort()
    return [round(ms.percentile(results, 0.025), 4), round(ms.percentile(results, 0.975), 4)]


@dataclass
class Option:
    via: str
    auc: float
    scores: list[float]
    labels: list[bool]
    clusters: list[int]


def choose_strength(options: list[Option], draws: int, seed: int) -> dict[str, Any]:
    best = max(options, key=lambda o: max(o.auc, 1 - o.auc))
    return {
        "strength": round(max(best.auc, 1 - best.auc), 4),
        "interval": interval_of(best.scores, best.labels, best.clusters, draws, seed, best.auc >= 0.5),
        "via": best.via,
    }


def presence_option(present: Sequence[bool], data: Data) -> Option | None:
    if all(present):
        return None
    scores = [1.0 if p else 0.0 for p in present]
    auc = ms.roc_auc(data.labels, scores)
    return (
        None if auc is None else Option("whether the value is present at all", auc, scores, data.labels, data.clusters)
    )


def summary_of(values: list[float], sentinels: list[float], present_rows: int) -> tuple[dict[str, Any], list[str]]:
    """The distribution without the codes for unknown, so that a 999 does not set the mean, and what stands out."""
    ordered = sorted(values)
    q1, median, q3 = (ms.percentile(ordered, s) for s in (0.25, 0.5, 0.75))
    mean = sum(ordered) / len(ordered)
    spread = math.sqrt(sum((v - mean) ** 2 for v in ordered) / len(ordered))
    skew = skewness(ordered)
    iqr = q3 - q1
    outliers = sum(1 for v in ordered if v < q1 - OUTLIER_FENCE * iqr or v > q3 + OUTLIER_FENCE * iqr) if iqr > 0 else 0
    zeros = sum(1 for v in ordered if v == 0) / len(ordered)
    summary: dict[str, Any] = {
        "min": plain(ordered[0]),
        "p01": plain(ms.percentile(ordered, 0.01)),
        "p25": plain(q1),
        "median": plain(median),
        "p75": plain(q3),
        "p99": plain(ms.percentile(ordered, 0.99)),
        "max": plain(ordered[-1]),
        "mean": plain(mean),
        "sd": plain(spread),
        "skew": None if skew is None else round(skew, 3),
        "zero_share": round(zeros, 4),
        "distinct": len(set(ordered)),
        "outliers": outliers,
    }
    flags: list[str] = []
    if sentinels:
        flags.append("code for unknown")
    if skew is not None and abs(skew) >= HEAVY_TAIL:
        flags.append("heavy tail")
    if zeros >= MOSTLY_ZERO:
        flags.append("mostly zero")
    if outliers >= OUTLIERS_MATTER * present_rows:
        flags.append("outliers")
    return summary, flags


def numeric_feature(name: str, kind: str, cells: list[str | None], data: Data, draws: int, seed: int) -> dict[str, Any]:
    """Numbers and dates. A date is its day number; a code for unknown is taken out and reported on its own."""
    if kind == "date":
        days = [measure.day(c) for c in cells]
        numbers: list[float | None] = [None if d is None else float(d.toordinal()) for d in days]
    else:
        numbers = [ms.to_float(c) for c in cells]
    raw = [v for v in numbers if v is not None]
    sentinels = find_sentinels(raw) if kind == "numeric" else []
    codes: list[float | None] = [v if v in sentinels else None for v in numbers]
    numbers = [None if v in sentinels else v for v in numbers]
    rows = [i for i, v in enumerate(numbers) if v is not None]
    if len(rows) < 2:
        return {"feature": name, "kind": kind, "strength": None, "signal": False, "flags": ["almost no usable values"]}
    values = [v for v in numbers if v is not None]
    labels = [data.labels[i] for i in rows]
    clusters = [data.clusters[i] for i in rows]
    edges = ms.decile_edges(values, BINS_LARGE if len(values) >= BINS_LARGE_FROM else BINS_SMALL)
    bin_ids = [bisect_left(edges, v) for v in values]
    counts = group_counts(bin_ids, labels)

    def edge_text(value: float) -> Any:
        return date.fromordinal(int(value)).isoformat() if kind == "date" else plain(value)

    lows = [min(values), *edges]
    highs = [*edges, max(values)]
    bins: list[dict[str, Any]] = []
    for index in sorted(counts):
        positives, group_rows = counts[index]
        bins.append({"from": edge_text(lows[index]), "to": edge_text(highs[index]), **rate_of(positives, group_rows)})
    groups = [counts[index] for index in sorted(counts)]
    base_rate = sum(data.labels) / len(data.labels)
    bins_p = chi_square(merge_small(groups, base_rate))[2]

    missing = [i for i, v in enumerate(numbers) if v is None and codes[i] is None]
    extra: list[Group] = []
    if missing:
        group = (sum(1 for i in missing if data.labels[i]), len(missing))
        bins.append({"from": "(missing)", "to": "(missing)", **rate_of(*group)})
        extra.append(group)
    sentinel_info: list[dict[str, Any]] = []
    for code in sentinels:
        members = [i for i, v in enumerate(codes) if v == code]
        group = (sum(1 for i in members if data.labels[i]), len(members))
        extra.append(group)
        sentinel_info.append(
            {"value": plain(code), "share": round(len(members) / len(data.labels), 4), **rate_of(*group)}
        )
        bins.append({"from": f"(code {plain(code)})", "to": f"(code {plain(code)})", **rate_of(*group)})

    statistic, degrees, overall_p = chi_square(merge_small([*groups, *extra], base_rate))
    rank_auc = ms.roc_auc(labels, values)
    rank_p = rank_test(labels, values, rank_auc)
    # Two tests look at each number, one for a trend and one for any shape, so the smaller p-value counts double.
    tests = [p for p in (rank_p, overall_p) if p is not None]
    p_value = min(1.0, len(tests) * min(tests)) if tests else None
    oof = ms.out_of_fold_rates([str(b) for b in bin_ids], labels, random.Random(seed))
    binned_auc = ms.roc_auc(labels, oof)
    options: list[Option] = []
    if rank_auc is not None:
        options.append(Option("rank of the values", rank_auc, values, labels, clusters))
    if binned_auc is not None:
        options.append(Option("bins of the values (out of fold)", binned_auc, oof, labels, clusters))
    presence = presence_option([v is not None for v in numbers], data)
    if presence is not None:
        options.append(presence)
    if not options:
        return {"feature": name, "kind": kind, "strength": None, "signal": False, "flags": ["one class only"]}
    chosen = choose_strength(options, draws, seed + 1)
    folded_rank = ms.strongest(rank_auc) or 0.5
    folded_binned = ms.strongest(binned_auc) or 0.5
    trend = rank_p is not None and rank_p < ALPHA and folded_binned - folded_rank < NOT_MONOTONE_GAP
    if trend:
        shape = "rising" if (rank_auc or 0.5) >= 0.5 else "falling"
    elif bins_p is not None and bins_p < ALPHA:
        shape = "not monotone"
    else:
        shape = "flat"
    flags: list[str] = []
    result: dict[str, Any] = {
        "feature": name,
        "kind": kind,
        **chosen,
        "rank_strength": None if rank_auc is None else round(folded_rank, 4),
        "binned_strength": None if binned_auc is None else round(folded_binned, 4),
        "shape": shape,
        "higher_means_more_positive": None if rank_auc is None else rank_auc >= 0.5,
        "rank_p": None if rank_p is None else round(rank_p, 6),
        "chi_square": round(statistic, 3),
        "degrees": degrees,
        "p_value": p_value,
        "bins": bins,
    }
    if kind == "date":
        result["summary"] = {"first": edge_text(min(values)), "last": edge_text(max(values))}
    else:
        result["summary"], flags = summary_of(values, sentinels, len(raw))
        if sentinel_info:
            result["sentinels"] = sentinel_info
    if shape == "not monotone":
        flags.append("not monotone")
    result["flags"] = flags
    return result


def category_feature(name: str, cells: list[str | None], data: Data, draws: int, seed: int) -> dict[str, Any]:
    counts = group_counts(cells, data.labels)
    named = [k for k in counts if k is not None]
    total = len(cells)
    ranked = sorted(named, key=lambda k: (-counts[k][1], k))
    distinct = len(ranked)
    show_levels = distinct <= MAX_LEVELS_NAMED
    hide_names = PEOPLE_NAME.search(name) is not None
    display = {k: (f"level {i}" if hide_names else k) for i, k in enumerate(ranked, start=1)}
    levels: list[dict[str, Any]] = []
    if show_levels:
        for key in ranked[:MAX_LEVELS_SHOWN]:
            levels.append({"level": display[key], "share": round(counts[key][1] / total, 4), **rate_of(*counts[key])})
        if None in counts:
            levels.append({"level": "(missing)", "share": round(counts[None][1] / total, 4), **rate_of(*counts[None])})
    rare = [k for k in ranked if counts[k][1] < RARE_LEVEL * total]
    rare_rows = sum(counts[k][1] for k in rare)
    base_rate = sum(data.labels) / len(data.labels)
    statistic, degrees, p_value = chi_square(merge_small(list(counts.values()), base_rate))
    rng = random.Random(seed)
    oof = ms.out_of_fold_rates(cells, data.labels, rng)
    auc = ms.roc_auc(data.labels, oof)
    options: list[Option] = []
    if auc is not None:
        options.append(Option("category rates (out of fold)", auc, oof, data.labels, data.clusters))
    presence = presence_option([c is not None for c in cells], data)
    if presence is not None:
        options.append(presence)
    chosen = choose_strength(options, draws, seed + 1) if options else {"strength": None, "interval": None, "via": None}
    flags: list[str] = []
    top_share = counts[ranked[0]][1] / total
    if top_share >= NEAR_CONSTANT:
        flags.append("near constant")
    if not show_levels:
        flags.append("high cardinality")
    if rare_rows >= RARE_LEVELS_MATTER * total and show_levels:
        flags.append("rare levels")
    if show_levels and any(counts[k][1] >= ALL_ONE_CLASS_ROWS and counts[k][0] in (0, counts[k][1]) for k in ranked):
        flags.append("a level with one class only")
    result: dict[str, Any] = {
        "feature": name,
        "kind": "category",
        **chosen,
        "chi_square": round(statistic, 3),
        "degrees": degrees,
        "p_value": p_value,
        "summary": {
            "distinct": distinct,
            "rare_levels": len(rare),
            "rows_in_rare_levels": rare_rows,
            "top_level_share": round(top_share, 4),
        },
        "levels": levels,
        "flags": flags,
    }
    if hide_names:
        result["level_names_hidden"] = "the column's name suggests people"
    if distinct > MAX_LEVELS_SHOWN and show_levels:
        result["levels_not_shown"] = distinct - MAX_LEVELS_SHOWN
    return result


# ---------------------------------------------------------------------------- across features


def segments_of(features: list[str], data: Data, kinds: dict[str, str], skip: set[str]) -> list[dict[str, Any]]:
    """Each level of a category against all the other rows, corrected across every level tested."""
    found: list[dict[str, Any]] = []
    for name in features:
        if kinds[name] != "category" or name in skip:
            continue
        cells = [r[name] for r in data.rows]
        counts = group_counts(cells, data.labels)
        named = sorted((k for k in counts if k is not None), key=lambda k: (-counts[k][1], k))
        if len(named) > MAX_LEVELS_NAMED:
            continue
        hide = PEOPLE_NAME.search(name) is not None
        positives = sum(g[0] for g in counts.values())
        rows = sum(g[1] for g in counts.values())
        for position, key in enumerate(named, start=1):
            level_positives, level_rows = counts[key]
            if level_rows < MIN_SEGMENT_ROWS or level_rows == rows:
                continue
            compared = ms.two_proportions(positives - level_positives, rows - level_rows, level_positives, level_rows)
            found.append(
                {
                    "feature": name,
                    "level": f"level {position}" if hide else key,
                    **rate_of(level_positives, level_rows),
                    "rate_elsewhere": round((positives - level_positives) / (rows - level_rows), 4),
                    "difference": round(compared.difference, 4),
                    "p_value": compared.p_value,
                }
            )
    for row, adjusted in zip(found, ms.holm([r["p_value"] for r in found]), strict=True):
        row["adjusted_p"] = round(adjusted, 6)
        row["differs"] = adjusted < ALPHA and abs(row["difference"]) >= MIN_SEGMENT_GAP
        row["p_value"] = round(row["p_value"], 6)
    found.sort(key=lambda r: r["adjusted_p"])
    return found


def missingness_of(features: list[str], data: Data) -> list[dict[str, Any]]:
    """Whether a missing value says something about the target."""
    found: list[dict[str, Any]] = []
    for name in features:
        cells = [r[name] for r in data.rows]
        missing = sum(1 for c in cells if c is None)
        if missing == 0 or missing == len(cells):
            continue
        missing_positives = sum(1 for c, y in zip(cells, data.labels, strict=True) if c is None and y)
        present = len(cells) - missing
        present_positives = sum(data.labels) - missing_positives
        compared = ms.two_proportions(present_positives, present, missing_positives, missing)
        found.append(
            {
                "feature": name,
                "missing_rows": missing,
                "missing_share": round(missing / len(cells), 4),
                "rate_when_missing": round(missing_positives / missing, 4),
                "rate_when_present": round(present_positives / present, 4),
                "difference": round(compared.difference, 4),
                "p_value": compared.p_value,
            }
        )
    for row, adjusted in zip(found, ms.holm([r["p_value"] for r in found]), strict=True):
        row["adjusted_p"] = round(adjusted, 6)
        row["carries_signal"] = adjusted < ALPHA and abs(row["difference"]) >= MISSING_RATE_GAP
        row["p_value"] = round(row["p_value"], 6)
    found.sort(key=lambda r: -abs(r["difference"]))
    return found


def redundant_of(
    features: list[dict[str, Any]], data: Data, rng: random.Random
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Pairs of features that say the same thing. A long table is sampled and a wide one cut, and the output says so."""
    usable = [
        f
        for f in features
        if f["kind"] == "numeric"
        or (f["kind"] == "category" and f["summary"]["distinct"] <= MAX_LEVELS_NAMED and f["summary"]["distinct"] > 1)
    ]
    usable.sort(key=lambda f: -(f["strength"] or 0.0))
    kept = usable[:PAIRS_MAX_COLUMNS]
    index = ms.shuffled(len(data.rows), rng)[:PAIRS_MAX_ROWS]
    numbers: dict[str, list[float | None]] = {}
    texts: dict[str, list[str | None]] = {}
    for feature in kept:
        name = feature["feature"]
        if feature["kind"] == "numeric":
            codes = {s["value"] for s in feature.get("sentinels", [])}
            cells = (ms.to_float(data.rows[i][name]) for i in index)
            numbers[name] = [None if v in codes else v for v in cells]
        else:
            texts[name] = [data.rows[i][name] for i in index]
    pairs: list[dict[str, Any]] = []
    for first, second in combinations([f["feature"] for f in kept], 2):
        if first in numbers and second in numbers:
            value, measured_by = spearman(numbers[first], numbers[second]), "Spearman correlation"
        elif first in texts and second in texts:
            value, measured_by = cramers_v(texts[first], texts[second]), "Cramer's V"
        elif first in texts:
            value, measured_by = correlation_ratio(texts[first], numbers[second]), "correlation ratio on ranks"
        else:
            value, measured_by = correlation_ratio(texts[second], numbers[first]), "correlation ratio on ranks"
        if value is not None and abs(value) >= REDUNDANT:
            pairs.append({"a": first, "b": second, "value": round(value, 4), "measure": measured_by})
    pairs.sort(key=lambda p: -abs(p["value"]))
    scope = {
        "rows_compared": len(index),
        "columns_compared": len(kept),
        "columns_left_out": len(usable) - len(kept),
    }
    return pairs, scope


def period_of(day: date, period: str) -> str:
    if period == "week":
        year, week, _ = day.isocalendar()
        return f"{year}-W{week:02d}"
    return f"{day.year}-{day.month:02d}"


def over_time(data: Data, column: str, period: str, horizon: int | None) -> dict[str, Any]:
    days = [measure.day(r[column]) for r in data.rows]
    dated = [(d, y) for d, y in zip(days, data.labels, strict=True) if d is not None]
    if not dated:
        return {"column": column, "periods": [], "rows_without_a_date": len(days)}
    counts = group_counts([period_of(d, period) for d, _ in dated], [y for _, y in dated])
    periods = [{"period": key, **rate_of(*counts[key])} for key in sorted(counts)]
    # Unfinished labels would look like a change in the rate, so whether it moves is asked of rows that can be known.
    known = dated
    if horizon is not None:
        cut = max(d for d, _ in dated) - timedelta(days=horizon)
        known = [(d, y) for d, y in dated if d <= cut] or dated
    known_counts = group_counts([period_of(d, period) for d, _ in known], [y for _, y in known])
    tested = [known_counts[key] for key in sorted(known_counts) if known_counts[key][1] >= MIN_PERIOD_ROWS]
    statistic, degrees, p_value = chi_square(tested)
    rates = [g[0] / g[1] for g in tested]
    result: dict[str, Any] = {
        "column": column,
        "period": period,
        "periods": periods,
        "rows_without_a_date": len(days) - len(dated),
        "first": min(d for d, _ in dated).isoformat(),
        "last": max(d for d, _ in dated).isoformat(),
        "chi_square": round(statistic, 3),
        "degrees": degrees,
        "p_value": p_value,
        "moves": p_value is not None and p_value < ALPHA,
        "periods_tested": len(tested),
        "lowest_rate": round(min(rates), 4) if rates else None,
        "highest_rate": round(max(rates), 4) if rates else None,
    }
    if horizon is not None:
        result["labels"] = maturity(dated, horizon)
    return result


def maturity(dated: list[tuple[date, bool]], horizon: int) -> dict[str, Any]:
    """Rows too recent for their outcome to be known, against the same length of time just before them."""
    last = max(d for d, _ in dated)
    cut = last - timedelta(days=horizon)
    before_cut = cut - timedelta(days=horizon)
    recent = [y for d, y in dated if d > cut]
    earlier = [y for d, y in dated if before_cut < d <= cut]
    result: dict[str, Any] = {
        "horizon_days": horizon,
        "assumes_extract_on": last.isoformat(),
        "last_fully_known_date": cut.isoformat(),
        "rows_not_yet_known": len(recent),
        "rows_just_before": len(earlier),
        "rate_not_yet_known": round(sum(recent) / len(recent), 4) if recent else None,
        "rate_just_before": round(sum(earlier) / len(earlier), 4) if earlier else None,
        "looks_unfinished": False,
    }
    if recent and earlier:
        compared = ms.two_proportions(sum(earlier), len(earlier), sum(recent), len(recent))
        result["p_value"] = round(compared.p_value, 6)
        result["looks_unfinished"] = compared.p_value < ALPHA and compared.difference < 0
    return result


def entities_of(data: Data, column: str) -> dict[str, Any]:
    per_entity = Counter(r[column] for r in data.rows if r[column] is not None)
    return {
        "column": column,
        "entities": len(per_entity),
        "entities_with_several_rows": sum(1 for n in per_entity.values() if n > 1),
        "rows_of_those_entities": sum(n for n in per_entity.values() if n > 1),
        "most_rows_for_one_entity": max(per_entity.values(), default=0),
    }


def leak_suspects(results: list[dict[str, Any]], data: Data, time_column: str | None) -> list[dict[str, Any]]:
    """Columns to check before they are trusted. Being on this list is a question, not a finding."""
    moments = [measure.day(r[time_column]) for r in data.rows] if time_column else []
    suspects: list[dict[str, Any]] = []
    for feature in results:
        name = feature["feature"]
        reasons: list[str] = []
        strength = feature.get("strength")
        if strength is not None and strength >= ms.ALMOST_PERFECT:
            reasons.append(f"almost perfect on its own (strength {strength})")
        elif strength is not None and strength >= ms.SUSPICIOUS:
            reasons.append(f"suspiciously strong on its own (strength {strength})")
        cells = [r[name] for r in data.rows]
        filled_yes = sum(1 for c, y in zip(cells, data.labels, strict=True) if c is not None and y)
        filled_no = sum(1 for c, y in zip(cells, data.labels, strict=True) if c is not None and not y)
        if filled_no == 0 and filled_yes >= FILLED_FOR_ONE_CLASS_ROWS:
            reasons.append(f"filled only when the target is yes ({filled_yes} rows)")
        if filled_yes == 0 and filled_no >= FILLED_FOR_ONE_CLASS_ROWS:
            reasons.append(f"filled only when the target is no ({filled_no} rows)")
        if ms.OUTCOME_NAME.search(name):
            reasons.append("the name suggests an outcome")
        if feature["kind"] == "date" and moments:
            later = sum(
                1 for c, m in zip(cells, moments, strict=True) if m is not None and (d := measure.day(c)) and d > m
            )
            if later:
                reasons.append(f"dated after the prediction moment on {later} rows")
        if reasons:
            suspects.append({"feature": name, "reasons": reasons})
    return suspects


def problems_of(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Everything worth reading first, the worst first. A place to look: each ends as a finding or is cleared."""
    found: list[dict[str, Any]] = []

    def add(severity: str, check: str, what: str, columns: list[str] | None = None) -> None:
        found.append({"severity": severity, "check": check, "what": what, "columns": columns or []})

    time = result.get("over_time")
    if time:
        if time.get("moves"):
            add(
                "high",
                "target over time",
                f"The target's rate moves between periods, from {time['lowest_rate']} to {time['highest_rate']} "
                f"(chi-square p {time['p_value']:.2g}).",
                [time["column"]],
            )
        labels = time.get("labels")
        if labels and labels["looks_unfinished"]:
            add(
                "high",
                "labels not known yet",
                f"{labels['rows_not_yet_known']} rows after {labels['last_fully_known_date']} have a rate of "
                f"{labels['rate_not_yet_known']} against {labels['rate_just_before']} just before them.",
                [time["column"]],
            )
    for suspect in result["leak_suspects"]:
        strong = any(r.startswith(("almost perfect", "filled only", "dated after")) for r in suspect["reasons"])
        add("high" if strong else "medium", "check for leakage", "; ".join(suspect["reasons"]), [suspect["feature"]])
    if result["target"]["rare_class"]:
        add("medium", "rare class", f"The rarer class is under {RARE_CLASS:.0%} of the rows.")
    entities = result.get("entities")
    if entities and entities["entities_with_several_rows"]:
        add(
            "medium",
            "several rows per entity",
            f"{entities['entities_with_several_rows']} of {entities['entities']} entities have more than one row: "
            "a random split would put the same entity on both sides.",
            [entities["column"]],
        )
    for feature in result["features"]:
        name = feature["feature"]
        for code in feature.get("sentinels", []):
            add(
                "medium",
                "code for unknown",
                f"{code['value']} on {code['rows']} rows ({code['share']:.1%}) looks like a code for unknown; "
                f"the rate there is {code['rate']}.",
                [name],
            )
        flags = feature.get("flags", [])
        if "not monotone" in flags:
            add(
                "medium",
                "not monotone",
                f"The relation changes direction: strength {feature['binned_strength']} from bins against "
                f"{feature['rank_strength']} from ranks. A linear term would miss it.",
                [name],
            )
        if "high cardinality" in flags:
            add("medium", "high cardinality", f"{feature['summary']['distinct']} levels: easy to overfit.", [name])
        if "near constant" in flags:
            add("low", "near constant", f"One level covers {feature['summary']['top_level_share']:.1%}.", [name])
        if "heavy tail" in flags:
            add("low", "heavy tail", f"Skew {feature['summary']['skew']}: a transform may help.", [name])
    leaks = {s["feature"] for s in result["leak_suspects"] if any(r.startswith("filled only") for r in s["reasons"])}
    for row in result["missingness"]:
        if row["carries_signal"] and row["feature"] not in leaks:
            add(
                "medium",
                "missing values carry signal",
                f"The rate is {row['rate_when_missing']} when missing and {row['rate_when_present']} when present.",
                [row["feature"]],
            )
    for pair in result["redundant"]:
        add("medium", "redundant features", f"{pair['measure']} {pair['value']}.", [pair["a"], pair["b"]])
    order = {"high": 0, "medium": 1, "low": 2}
    found.sort(key=lambda p: order[p["severity"]])
    return found


def main(argv: list[str] | None = None) -> int:
    args = read_args(argv)
    data = load_data(args)
    excluded = {c.strip() for c in args.exclude.split(",") if c.strip()}
    roles = {args.label, args.row_id, args.entity, args.time}
    header = data.table.header
    personal = data.table.personal
    candidates = [c for c in header if c not in roles and c not in excluded and c not in personal]
    kinds = {c: kind_of([r[c] for r in data.rows]) for c in candidates}
    not_used = [{"column": c, "why": kinds[c]} for c in candidates if kinds[c] in ("empty", "constant", "id-like")]
    features = [c for c in candidates if c not in {n["column"] for n in not_used}]

    rows = len(data.rows)
    draws = max(BOOTSTRAP_MIN, min(args.bootstrap, int(args.bootstrap * BOOTSTRAP_FULL_ROWS / rows)))
    results: list[dict[str, Any]] = []
    for position, name in enumerate(features):
        cells = [r[name] for r in data.rows]
        seed = args.seed * 1000 + position * 2
        if kinds[name] == "category":
            results.append(category_feature(name, cells, data, draws, seed))
        else:
            results.append(numeric_feature(name, kinds[name], cells, data, draws, seed))
    tested = [f for f in results if f.get("p_value") is not None]
    for feature, adjusted in zip(tested, ms.holm([f["p_value"] for f in tested]), strict=True):
        feature["adjusted_p"] = round(adjusted, 6)
        feature["signal"] = adjusted < ALPHA
        feature["p_value"] = round(feature["p_value"], 6)
    for feature in results:
        feature.setdefault("signal", False)
        if not feature["signal"] and "shape" in feature:
            # A shape read from a relation the corrected test does not support would be a shape in the noise.
            feature["shape"] = "flat"
            feature["flags"] = [f for f in feature["flags"] if f != "not monotone"]
    results.sort(key=lambda f: (-(f.get("strength") or 0.0), f["feature"]))

    positives = sum(data.labels)
    suspects = leak_suspects(results, data, args.time)
    obvious = {
        s["feature"] for s in suspects if any(r.startswith(("almost perfect", "filled only")) for r in s["reasons"])
    }
    output: dict[str, Any] = {
        "file": data.table.path.name,
        "rows_read": len(data.table.rows),
        "rows_used": rows,
        "rows_without_a_label": data.no_label,
        "target": {
            "column": args.label,
            **rate_of(positives, rows),
            "rare_class": min(positives, rows - positives) / rows < RARE_CLASS,
        },
        "features": results,
        "segments": segments_of(features, data, kinds, obvious),
        "missingness": missingness_of(features, data),
        "leak_suspects": suspects,
        "personal_columns": personal,
        "not_used": not_used,
        "excluded": sorted(excluded),
        "bootstrap_draws": draws,
        "seed": args.seed,
        "notes": list(data.table.notes),
    }
    output["redundant"], output["redundant_scope"] = redundant_of(results, data, random.Random(args.seed))
    if args.time:
        output["over_time"] = over_time(data, args.time, args.period, args.horizon_days)
    if args.entity:
        output["entities"] = entities_of(data, args.entity)
        if output["entities"]["entities_with_several_rows"]:
            output["notes"].append(
                "Some entities have several rows. The intervals resample whole entities; the chi-square tests treat "
                "rows as independent, so their p-values are too small."
            )
    output["problems"] = problems_of(output)
    json.dump(output, sys.stdout, indent=1, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
