#!/usr/bin/env python3
"""The statistics the data-scientist scripts share. Import it; there is nothing to run.

Ranking and error metrics, seeded bootstrap draws, calibration, cost thresholds, proportions and means, a chi-square
tail, Holm's correction, sample sizes, population stability index. Everything is built on statistics.NormalDist,
math and random.Random, no other library, so what a script prints can be recomputed by hand.

Conventions:
- A score is "higher means more likely positive". Tied scores are one group: a tie never counts as a win for
  either side of a pair and is never split across a threshold, so the row order of a file cannot change a number.
- ROC-AUC is the probability a positive outranks a negative, ties as half. PR-AUC is average precision, the sum of
  precision at each distinct score weighted by the recall added there, as most libraries compute it. The trapezoid
  under a precision-recall curve overstates it, so it is not used.
- Standard library only. Read-only.
"""

from __future__ import annotations

import math
import random
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import NormalDist

NORMAL = NormalDist()
LOG_LOSS_CLIP = 1e-15
PSI_FLOOR = 1e-4
PSI_STABLE = 0.10
PSI_MAJOR = 0.25

# Armitage, McPherson and Rowe (1969): the true false-positive rate when a two-sided 5% test is read at this many
# equally spaced looks and the first significant look ends it. Beyond 100 looks the rate keeps rising towards 1.
PEEKING_FALSE_POSITIVE = {1: 0.05, 2: 0.083, 3: 0.107, 4: 0.126, 5: 0.142, 10: 0.193, 20: 0.248, 50: 0.320, 100: 0.374}


def to_float(cell: str | None) -> float | None:
    """A number from a cell, or None. Accepts what float accepts (1e-05 included) and a decimal comma."""
    if cell is None:
        return None
    text = cell.strip()
    try:
        value = float(text)
    except ValueError:
        try:
            value = float(text.replace(",", "."))
        except ValueError:
            return None
    return value if math.isfinite(value) else None


def parse_binary(cell: str | None, positive: str | None = None) -> bool | None:
    """True, False or None for a label cell. With no `positive` value, only 1/0, true/false, yes/no are read."""
    if cell is None:
        return None
    text = cell.strip().lower()
    if positive is not None:
        return text == positive.strip().lower()
    if text in ("1", "true", "yes", "t", "y", "1.0"):
        return True
    if text in ("0", "false", "no", "f", "n", "0.0"):
        return False
    return None


def z_for(confidence: float) -> float:
    """The two-sided normal multiplier of a confidence level, 1.96 for 0.95."""
    return NORMAL.inv_cdf(0.5 + confidence / 2)


def two_sided_p(z: float) -> float:
    """Two-sided p-value of a z score. erfc stays accurate in the tails, where 1 - cdf rounds to zero."""
    return math.erfc(abs(z) / math.sqrt(2))


def percentile(ordered: Sequence[float], share: float) -> float:
    """Linear interpolation between order statistics; `ordered` must be sorted."""
    if not ordered:
        raise ValueError("percentile of nothing")
    position = share * (len(ordered) - 1)
    low = math.floor(position)
    high = math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


# ---------------------------------------------------------------------------- ranking and error metrics


@dataclass(frozen=True)
class Ordered:
    """Rows from the highest score down; `ends` marks the last row of each group of equal scores."""

    rows: list[int]
    ends: list[bool]


@dataclass(frozen=True)
class Ranks:
    auc: float | None
    ap: float | None
    min_cost: float | None


def order_scores(scores: Sequence[float]) -> Ordered:
    rows = sorted(range(len(scores)), key=lambda i: -scores[i])
    ends = [i == len(rows) - 1 or scores[rows[i]] != scores[rows[i + 1]] for i in range(len(rows))]
    return Ordered(rows, ends)


def rank_sweep(
    ordered: Ordered,
    labels: Sequence[bool],
    weights: Sequence[float] | None = None,
    cost_fp: float | None = None,
    cost_fn: float | None = None,
) -> Ranks:
    """ROC-AUC, average precision and, given both costs, the lowest cost per row over all thresholds.

    Weights let a bootstrap resample reuse the one sort. A pass over the rows, not over pairs, so a resample costs
    O(n); the same code gives the point estimates, so an estimate and its interval cannot disagree on a definition.
    """
    rows = ordered.rows
    ends = ordered.ends
    if weights is None:
        weights = [1.0] * len(labels)
    positives = sum(w for w, y in zip(weights, labels, strict=True) if y)
    total = sum(weights)
    negatives = total - positives
    if positives == 0 or negatives == 0:
        return Ranks(None, None, None)
    with_costs = cost_fp is not None and cost_fn is not None
    tp = fp = 0.0
    group_tp = group_fp = 0.0
    area = precision_area = 0.0
    best_cost = float(positives) * float(cost_fn) if with_costs and cost_fn is not None else math.inf
    for position, row in enumerate(rows):
        weight = weights[row]
        if labels[row]:
            group_tp += weight
        else:
            group_fp += weight
        if ends[position] and (group_tp or group_fp):
            # A negative in this group is beaten by every positive above and ties with those beside it.
            area += group_fp * (tp + 0.5 * group_tp)
            tp += group_tp
            fp += group_fp
            if group_tp:
                precision_area += group_tp * tp / (tp + fp)
            if with_costs and cost_fp is not None and cost_fn is not None:
                cost = fp * cost_fp + (positives - tp) * cost_fn
                if cost < best_cost:
                    best_cost = cost
            group_tp = group_fp = 0.0
    return Ranks(area / (positives * negatives), precision_area / positives, best_cost / total if with_costs else None)


def roc_auc(labels: Sequence[bool], scores: Sequence[float]) -> float | None:
    """ROC-AUC, or None when only one class is present."""
    return rank_sweep(order_scores(scores), labels).auc


def average_precision(labels: Sequence[bool], scores: Sequence[float]) -> float | None:
    """PR-AUC as average precision, or None when only one class is present."""
    return rank_sweep(order_scores(scores), labels).ap


def clip_probability(p: float) -> float:
    return min(max(p, LOG_LOSS_CLIP), 1 - LOG_LOSS_CLIP)


def log_loss_row(y: bool, p: float) -> float:
    q = clip_probability(p)
    return -math.log(q if y else 1 - q)


def brier_row(y: bool, p: float) -> float:
    return (p - (1.0 if y else 0.0)) ** 2


def weighted_mean(values: Sequence[float], weights: Sequence[float] | None = None) -> float:
    if weights is None:
        return sum(values) / len(values)
    return sum(v * w for v, w in zip(values, weights, strict=True)) / sum(weights)


def log_loss(labels: Sequence[bool], probabilities: Sequence[float]) -> float:
    return weighted_mean([log_loss_row(y, p) for y, p in zip(labels, probabilities, strict=True)])


def brier(labels: Sequence[bool], probabilities: Sequence[float]) -> float:
    return weighted_mean([brier_row(y, p) for y, p in zip(labels, probabilities, strict=True)])


# ---------------------------------------------------------------------------- bootstrap


def bootstrap_weights(rng: random.Random, clusters: Sequence[int], n_clusters: int) -> list[float]:
    """One bootstrap resample as a weight per row: n clusters drawn with replacement, rows of a cluster move together.

    `int(random() * n)` and not `randrange`, because only `random()` keeps its sequence across Python versions.
    """
    counts = [0.0] * n_clusters
    draw = rng.random
    for _ in range(n_clusters):
        counts[int(draw() * n_clusters)] += 1.0
    return [counts[c] for c in clusters]


# ---------------------------------------------------------------------------- proportions and means


def wilson(successes: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """The Wilson interval of a proportion; unlike the Wald interval it behaves at 0, 1 and with small n."""
    if n == 0:
        return (0.0, 1.0)
    z = z_for(confidence)
    p = successes / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return (max(0.0, centre - margin), min(1.0, centre + margin))


@dataclass(frozen=True)
class Comparison:
    """Treatment minus control, its z score, two-sided p-value and confidence interval."""

    difference: float
    z: float
    p_value: float
    low: float
    high: float
    se: float


def two_proportions(x_control: int, n_control: int, x_treat: int, n_treat: int, confidence: float = 0.95) -> Comparison:
    """Two-proportion z test. The p-value uses the pooled standard error, the interval the unpooled one."""
    p_c = x_control / n_control
    p_t = x_treat / n_treat
    pooled = (x_control + x_treat) / (n_control + n_treat)
    se_pooled = math.sqrt(pooled * (1 - pooled) * (1 / n_control + 1 / n_treat))
    se = math.sqrt(p_c * (1 - p_c) / n_control + p_t * (1 - p_t) / n_treat)
    diff = p_t - p_c
    z = diff / se_pooled if se_pooled else 0.0
    margin = z_for(confidence) * se
    return Comparison(diff, z, two_sided_p(z), diff - margin, diff + margin, se)


def welch(
    mean_control: float,
    var_control: float,
    n_control: int,
    mean_treat: float,
    var_treat: float,
    n_treat: int,
    confidence: float = 0.95,
) -> Comparison:
    """Difference of two means, normal approximation with unequal variances (for large samples, as A/B tests are)."""
    se = math.sqrt(var_control / n_control + var_treat / n_treat)
    diff = mean_treat - mean_control
    z = diff / se if se else 0.0
    margin = z_for(confidence) * se
    return Comparison(diff, z, two_sided_p(z), diff - margin, diff + margin, se)


def variance(values: Sequence[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    return sum((v - mean) ** 2 for v in values) / (n - 1)


def chi_square_sf(x: float, df: int) -> float:
    """The chi-square upper tail: the regularized upper incomplete gamma Q(df/2, x/2)."""
    if x <= 0:
        return 1.0
    a = df / 2
    z = x / 2
    if z < a + 1:
        # Series for the lower tail: it converges fast below the mean.
        term = total = 1 / a
        for n in range(1, 10_000):
            term *= z / (a + n)
            total += term
            if abs(term) < abs(total) * 1e-16:
                break
        return 1 - total * math.exp(-z + a * math.log(z) - math.lgamma(a))
    # Continued fraction for the upper tail (Lentz), which converges fast above the mean.
    tiny = 1e-300
    b = z + 1 - a
    c = 1 / tiny
    d = 1 / b
    h = d
    for i in range(1, 10_000):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = tiny if abs(d) < tiny else d
        c = b + an / c
        c = tiny if abs(c) < tiny else c
        d = 1 / d
        step = d * c
        h *= step
        if abs(step - 1) < 1e-16:
            break
    return h * math.exp(-z + a * math.log(z) - math.lgamma(a))


def holm(p_values: Sequence[float]) -> list[float]:
    """Holm's step-down adjustment, in the input order; adjusted values never fall as p rises."""
    m = len(p_values)
    order = sorted(range(m), key=lambda i: p_values[i])
    adjusted = [0.0] * m
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * p_values[i]))
        adjusted[i] = running
    return adjusted


# ---------------------------------------------------------------------------- planning a test


def _z_pair(alpha: float, power: float) -> tuple[float, float]:
    return NORMAL.inv_cdf(1 - alpha / 2), NORMAL.inv_cdf(power)


def sample_size_proportions(
    p_control: float, p_treat: float, alpha: float = 0.05, power: float = 0.8, ratio: float = 1.0
) -> tuple[int, int]:
    """Units in control and treatment to detect p_control vs p_treat, two-sided (normal approximation, Fleiss).

    `ratio` is treatment units per control unit. The same formula as R's power.prop.test when ratio is 1.
    """
    z_alpha, z_power = _z_pair(alpha, power)
    delta = abs(p_treat - p_control)
    bar = (p_control + ratio * p_treat) / (1 + ratio)
    first = z_alpha * math.sqrt(bar * (1 - bar) * (1 + 1 / ratio))
    second = z_power * math.sqrt(p_control * (1 - p_control) + p_treat * (1 - p_treat) / ratio)
    n_control = (first + second) ** 2 / delta**2
    return math.ceil(n_control), math.ceil(n_control * ratio)


def sample_size_means(
    sd: float, delta: float, alpha: float = 0.05, power: float = 0.8, ratio: float = 1.0
) -> tuple[int, int]:
    """Units per arm to detect a difference of `delta` in a mean with this standard deviation (normal approximation)."""
    z_alpha, z_power = _z_pair(alpha, power)
    n_control = (1 + 1 / ratio) * (z_alpha + z_power) ** 2 * sd**2 / delta**2
    return math.ceil(n_control), math.ceil(n_control * ratio)


def mde_proportions(
    p_control: float, n_control: int, alpha: float = 0.05, power: float = 0.8, ratio: float = 1.0
) -> float | None:
    """The smallest absolute rise of the proportion this sample can detect; None when no rise up to 1 is detectable."""
    low = 1e-7
    high = 1 - p_control - 1e-9
    if high <= low or sample_size_proportions(p_control, p_control + high, alpha, power, ratio)[0] > n_control:
        return None
    for _ in range(100):
        mid = (low + high) / 2
        if sample_size_proportions(p_control, p_control + mid, alpha, power, ratio)[0] <= n_control:
            high = mid
        else:
            low = mid
    return high


def mde_means(sd: float, n_control: int, alpha: float = 0.05, power: float = 0.8, ratio: float = 1.0) -> float:
    z_alpha, z_power = _z_pair(alpha, power)
    return (z_alpha + z_power) * sd * math.sqrt((1 + 1 / ratio) / n_control)


def peeking_false_positive(looks: int) -> float:
    """The true false-positive rate of a 5% test read at this many equal looks, between table rows by log(looks)."""
    if looks <= 1:
        return PEEKING_FALSE_POSITIVE[1]
    points = sorted(PEEKING_FALSE_POSITIVE)
    if looks >= points[-1]:
        return PEEKING_FALSE_POSITIVE[points[-1]]
    upper = next(p for p in points if p >= looks)
    lower = max(p for p in points if p <= looks)
    if upper == lower:
        return PEEKING_FALSE_POSITIVE[lower]
    share = (math.log(looks) - math.log(lower)) / (math.log(upper) - math.log(lower))
    return PEEKING_FALSE_POSITIVE[lower] + share * (PEEKING_FALSE_POSITIVE[upper] - PEEKING_FALSE_POSITIVE[lower])


# ---------------------------------------------------------------------------- drift


def psi(expected: Sequence[float], actual: Sequence[float], floor: float = PSI_FLOOR) -> float:
    """Population stability index of two share vectors over the same bins. A zero share becomes `floor`."""
    total = 0.0
    for e, a in zip(expected, actual, strict=True):
        e_share = max(e, floor)
        a_share = max(a, floor)
        total += (a_share - e_share) * math.log(a_share / e_share)
    return total


def psi_band(value: float) -> str:
    """The usual reading of PSI: under 0.10 stable, 0.10 to 0.25 a moderate shift, above 0.25 a major one."""
    if value < PSI_STABLE:
        return "stable"
    return "moderate" if value < PSI_MAJOR else "major"


def decile_edges(values: Sequence[float], bins: int = 10) -> list[float]:
    """Upper edges of equal-count bins over `values`, each edge a value that exists, without repeats."""
    ordered = sorted(values)
    n = len(ordered)
    edges = sorted({ordered[min(n - 1, math.ceil(n * i / bins) - 1)] for i in range(1, bins)})
    return edges


def _bin_shares(values: Sequence[float], edges: Sequence[float], missing: int) -> list[float]:
    counts = [0] * (len(edges) + 2)
    for v in values:
        counts[_bin_of(v, edges)] += 1
    counts[-1] = missing
    total = len(values) + missing
    return [c / total for c in counts]


def _bin_of(value: float, edges: Sequence[float]) -> int:
    for i, edge in enumerate(edges):
        if value <= edge:
            return i
    return len(edges)


def numeric_psi(base: Sequence[float | None], other: Sequence[float | None], bins: int = 10) -> float | None:
    """PSI of a numeric feature on the base sample's deciles, missing as its own bin."""
    base_present = [v for v in base if v is not None]
    other_present = [v for v in other if v is not None]
    if not base_present or not other_present:
        return None
    edges = decile_edges(base_present, bins)
    expected = _bin_shares(base_present, edges, len(base) - len(base_present))
    actual = _bin_shares(other_present, edges, len(other) - len(other_present))
    return psi(expected, actual)


def categorical_psi(base: Sequence[str | None], other: Sequence[str | None]) -> float | None:
    """PSI of a categorical feature, one bin per value in either sample, missing as its own bin."""
    if not base or not other:
        return None
    base_counts = Counter(base)
    other_counts = Counter(other)
    labels = sorted({v for v in (*base_counts, *other_counts) if v is not None})
    if not labels:
        return None
    expected = [base_counts[label] / len(base) for label in labels]
    expected.append(base_counts[None] / len(base))
    actual = [other_counts[label] / len(other) for label in labels]
    actual.append(other_counts[None] / len(other))
    return psi(expected, actual)
