#!/usr/bin/env python3
"""Generate the sample data of the acme-churn fixture into extras/data/.

Usage: python3 fixtures/acme-churn/make_data.py [TARGET_DIR]

Everything is made up: Acme Stream, its subscribers and every person. E-mails are at example.com and phones are in
the 555 range. Only `Random.random()` is used, because it is the one method whose sequence Python guarantees across
versions, so the same seed gives the same bytes on every interpreter.

The planted problems, recomputed from the CSVs by the tests:

- train.csv and test.csv: `cancellation_reason` is only filled for customers who already churned; `last_login_at` is
  later than `snapshot_date` on a known number of rows; some customers appear on both sides; some test rows are exact
  copies of training rows; `nps_last` is missing far more often for churners; `monthly_fee_eur` drifted between the
  two periods after a price rise.
- predictions.csv: a baseline and two models. One model's edge over the baseline is inside the noise, the other's is
  real, and the real winner is badly calibrated and much worse on the `legacy` plan.
- experiment_clean.csv and experiment_broken.csv: arm counts and successes are exact. The clean run's primary metric is
  significant until it is corrected for four metrics; the broken run has a sample ratio mismatch.
- snapshots.csv: the whole history before anyone splits it, for exploring. The churn rate jumps from 2025-11; the last
  three months have labels that are not all known yet; `tenure_months` uses 999 for unknown; `avg_session_min` relates
  to churn in a U, so a rank test sees nothing; the legacy plan churns more; `annual_fee_eur` repeats the monthly fee;
  `campaign_code` has hundreds of levels and no signal; `is_internal_account` is nearly constant;
  `retention_call_outcome` is only filled for customers who churned; some customers have several rows;
  `account_manager` holds people's names.
"""

from __future__ import annotations

import argparse
import csv
import math
import random
import sys
from datetime import date, timedelta
from pathlib import Path
from statistics import NormalDist

HERE = Path(__file__).resolve().parent
TARGET = HERE / "extras" / "data"
SEED = 20261110
NORMAL = NormalDist()

FIRST_NAMES = ["Ana", "Bojan", "Danica", "Goran", "Ivana", "Jasna", "Lazar", "Marija", "Nada", "Petar", "Sava", "Vera"]
LAST_NAMES = ["Borović", "Cerović", "Dubović", "Grabić", "Hrastić", "Javorac", "Kestenić", "Lipić", "Topolić", "Vrbić"]
ASCII = str.maketrans("ćčšžđ", "ccszd")
PLANS = [("basic", 9.0, 0.34), ("plus", 19.0, 0.34), ("pro", 39.0, 0.20), ("legacy", 14.0, 0.12)]
REGIONS = ["north", "south", "east", "west"]
MANAGERS = ["Mila Borović", "Nenad Javorac", "Olga Lipić", "Pavle Grabić", "Rada Vrbić", "Sima Topolić"]
REASONS = ["too expensive", "not using it", "switched provider", "missing a feature", "other"]
TRAIN_MONTHS = [
    date(2025, 7, 1),
    date(2025, 8, 1),
    date(2025, 9, 1),
    date(2025, 10, 1),
    date(2025, 11, 1),
    date(2025, 12, 1),
    date(2026, 1, 1),
    date(2026, 2, 1),
    date(2026, 3, 1),
]
TEST_MONTHS = [date(2026, 4, 1), date(2026, 5, 1), date(2026, 6, 1)]
COLUMNS = [
    "row_id",
    "customer_id",
    "snapshot_date",
    "plan",
    "region",
    "tenure_months",
    "monthly_fee_eur",
    "logins_30d",
    "tickets_90d",
    "payment_failures_90d",
    "discount_pct",
    "last_login_at",
    "nps_last",
    "cancellation_reason",
    "full_name",
    "email",
    "phone",
    "churned_60d",
]

TRAIN_ROWS = 2400
TEST_ROWS = 1000
# A price rise took effect with the test period; `monthly_fee_eur` is the one feature that moves between the splits.
TEST_FEE_RISE = 1.07
# Planted counts: rows of test that are exact copies of train rows, and more test rows for customers also in train.
EXACT_COPIES = 40
OVERLAP_EXTRA_ROWS = 110
TIME_LEAK_TRAIN_ROWS = 96
TIME_LEAK_TEST_ROWS = 40
# (intercept, slope) of each model's probability on its signal: the baseline and logreg_v2 are tuned to be calibrated.
BASELINE = (-1.55, 0.45)
LOGREG = (-1.55, 0.45)
GBT = (-0.7, 1.15)


def normal(rng: random.Random) -> float:
    return NORMAL.inv_cdf(min(max(rng.random(), 1e-12), 1 - 1e-12))


def choose(rng: random.Random, items: list[str]) -> str:
    return items[int(rng.random() * len(items))]


def weighted(rng: random.Random, items: list[tuple[str, float, float]]) -> tuple[str, float]:
    point = rng.random() * sum(weight for _, _, weight in items)
    running = 0.0
    for name, fee, weight in items:
        running += weight
        if point <= running:
            return name, fee
    return items[-1][0], items[-1][1]


def poisson(rng: random.Random, mean: float) -> int:
    limit = math.exp(-mean)
    count = 0
    product = rng.random()
    while product > limit:
        count += 1
        product *= rng.random()
    return count


def expit(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def person(rng: random.Random, index: int) -> dict[str, str]:
    first = choose(rng, FIRST_NAMES)
    last = choose(rng, LAST_NAMES)
    email = f"{first.lower()}.{last.lower().translate(ASCII)}.{index}@example.com"
    return {
        "full_name": f"{first} {last}",
        "email": email,
        "phone": f"+381-11-555-{1000 + index % 9000:04d}",
    }


def feature_row(
    rng: random.Random, customer: str, identity: dict[str, str], day: date, fee_rise: float
) -> dict[str, str]:
    engagement = normal(rng)
    plan, fee = weighted(rng, PLANS)
    tenure = 1 + int(rng.random() * 60)
    logins = max(0, round(12 + 5 * engagement + 2 * normal(rng)))
    tickets = poisson(rng, max(0.05, 1.1 - 0.5 * engagement))
    failures = poisson(rng, 0.14)
    discount = choose(rng, ["0", "5", "10", "15", "20"])
    risk = -1.85 - 0.8 * engagement + 0.28 * tickets - 0.01 * tenure + 0.45 * failures
    churned = rng.random() < expit(risk)
    gap = 1 + int(rng.random() * 22)
    last_login = day - timedelta(days=gap)
    fee_paid = round(fee * fee_rise * (1 + 0.06 * normal(rng)), 2)
    nps = (
        ""
        if rng.random() < (0.55 if churned else 0.10)
        else str(min(10, max(0, round(6.5 - (2.2 if churned else 0) + 2 * normal(rng)))))
    )
    reason = choose(rng, REASONS) if churned and rng.random() < 0.93 else ""
    return {
        "row_id": "",
        "customer_id": customer,
        "snapshot_date": day.isoformat(),
        "plan": plan,
        "region": choose(rng, REGIONS),
        "tenure_months": str(tenure),
        "monthly_fee_eur": f"{fee_paid:.2f}",
        "logins_30d": str(logins),
        "tickets_90d": str(tickets),
        "payment_failures_90d": str(failures),
        "discount_pct": discount,
        "last_login_at": f"{last_login.isoformat()}T{6 + int(rng.random() * 14):02d}:00:00",
        "nps_last": nps,
        "cancellation_reason": reason,
        **identity,
        "churned_60d": "1" if churned else "0",
    }


def plant_time_leak(rng: random.Random, rows: list[dict[str, str]], count: int) -> None:
    """Mark exactly `count` rows: an extract run after the snapshot stamped the login it saw then, not the one before.

    The rows that become exact copies in test are left out, so the copies carry nothing planted but the copying."""
    picks = [i for i in shuffled(len(rows), rng) if i >= EXACT_COPIES][:count]
    for i in picks:
        day = date.fromisoformat(rows[i]["snapshot_date"]) + timedelta(days=1 + int(rng.random() * 20))
        rows[i]["last_login_at"] = f"{day.isoformat()}T09:00:00"


def shuffled(n: int, rng: random.Random) -> list[int]:
    order = list(range(n))
    for i in range(n - 1, 0, -1):
        j = int(rng.random() * (i + 1))
        order[i], order[j] = order[j], order[i]
    return order


def build_splits(rng: random.Random) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    train: list[dict[str, str]] = []
    for i in range(TRAIN_ROWS):
        customer = f"C{i:05d}"
        day = TRAIN_MONTHS[int(rng.random() * len(TRAIN_MONTHS))]
        train.append(feature_row(rng, customer, person(rng, i), day, 1.0))
    plant_time_leak(rng, train, TIME_LEAK_TRAIN_ROWS)

    fresh_customers = TEST_ROWS - EXACT_COPIES - OVERLAP_EXTRA_ROWS
    test: list[dict[str, str]] = []
    for i in range(fresh_customers):
        index = TRAIN_ROWS + i
        day = TEST_MONTHS[int(rng.random() * len(TEST_MONTHS))]
        test.append(feature_row(rng, f"C{index:05d}", person(rng, index), day, TEST_FEE_RISE))
    # Customers already in train, seen again later: not exact copies, but the same people on both sides.
    overlap = [i for i in shuffled(TRAIN_ROWS, rng) if i >= EXACT_COPIES][:OVERLAP_EXTRA_ROWS]
    for i in overlap:
        day = TEST_MONTHS[int(rng.random() * len(TEST_MONTHS))]
        identity = {k: train[i][k] for k in ("full_name", "email", "phone")}
        test.append(feature_row(rng, train[i]["customer_id"], identity, day, TEST_FEE_RISE))
    plant_time_leak(rng, test, TIME_LEAK_TEST_ROWS)
    # Exact copies, from the first rows of train so the two planted sets of customers cannot collide.
    test.extend(dict(train[i]) for i in range(EXACT_COPIES))
    return train, test


def number_rows(rows: list[dict[str, str]], prefix: str) -> None:
    for i, row in enumerate(rows, start=1):
        row["row_id"] = f"{prefix}{i:06d}"


def plan_of(rng: random.Random) -> str:
    return weighted(rng, PLANS)[0]


def build_predictions(rng: random.Random) -> list[dict[str, str]]:
    """A baseline and two models scored on the same held-out rows.

    The baseline and `logreg_v2` see the same one signal through independent noise, so `logreg_v2` is a coin flip
    better. `gbt_v7` also sees the second signal: a real improvement, but its probabilities are pushed high and
    stretched, and on the legacy plan its signal is mostly noise.
    """
    rows = []
    for i in range(1, 3001):
        first_signal, second_signal = normal(rng), normal(rng)
        plan = plan_of(rng)
        region = choose(rng, REGIONS)
        true_logit = -1.75 + 0.85 * first_signal + 0.85 * second_signal
        churned = rng.random() < expit(true_logit)
        base_signal = first_signal + 0.85 * normal(rng)
        logreg_signal = first_signal + 0.82 * normal(rng)
        gbt_signal = first_signal + second_signal + 0.55 * normal(rng)
        if plan == "legacy":
            gbt_signal = 0.25 * gbt_signal + 1.35 * normal(rng)
        baseline = expit(BASELINE[0] + BASELINE[1] * base_signal)
        logreg = expit(LOGREG[0] + LOGREG[1] * logreg_signal)
        gbt = expit(GBT[0] + GBT[1] * gbt_signal)
        identity = person(rng, 100_000 + i)
        rows.append(
            {
                "prediction_id": f"P{i:06d}",
                "churned_60d": "1" if churned else "0",
                "plan": plan,
                "region": region,
                "baseline_score": f"{baseline:.6f}",
                "logreg_v2": f"{logreg:.6f}",
                "gbt_v7": f"{gbt:.6f}",
                "email": identity["email"],
            }
        )
    return rows


# (name, control successes, treatment successes) in exact counts; the clean run has 3012 and 2988 units.
CLEAN_PROPORTIONS = [
    ("renewed", 1499, 1570),
    ("upgraded", 241, 251),
    ("app_open_7d", 1205, 1221),
    ("support_contact", 181, 188),
    ("refund_requested", 30, 34),
]
BROKEN_PROPORTIONS = [("renewed", 1372, 1369), ("support_contact", 158, 142)]


def experiment_rows(
    rng: random.Random,
    control_n: int,
    treatment_n: int,
    proportions: list[tuple[str, int, int]],
    arpu_shift: float,
    start: date,
    days: int,
) -> list[dict[str, str]]:
    units = [("control", i) for i in range(control_n)] + [("treatment", i) for i in range(treatment_n)]
    order = shuffled(len(units), rng)
    rows = []
    for position, idx in enumerate(order):
        arm, seq = units[idx]
        identity = person(rng, 200_000 + position)
        row: dict[str, str] = {
            "subscriber_id": f"S{position + 1:06d}",
            "variant": arm,
            "assigned_at": (start + timedelta(days=int(rng.random() * days))).isoformat(),
            "email": identity["email"],
        }
        rows.append((row, arm, seq))
    columns: dict[str, dict[tuple[str, int], str]] = {}
    for name, control_hits, treatment_hits in proportions:
        hits = dict.fromkeys(((a, s) for a, s in units), "0")
        for arm, count, n in (("control", control_hits, control_n), ("treatment", treatment_hits, treatment_n)):
            for i in shuffled(n, rng)[:count]:
                hits[(arm, i)] = "1"
        columns[name] = hits
    done = []
    for row, arm, seq in rows:
        for name, _, _ in proportions:
            row[name] = columns[name][(arm, seq)]
        mean = 29.0 + (arpu_shift if arm == "treatment" else 0.0)
        row["arpu_eur"] = f"{max(0.0, mean + 11.0 * normal(rng)):.2f}"
        done.append(row)
    return done


SNAPSHOT_ROWS = 6000
SNAPSHOT_CUSTOMERS = 4500
# SEED + 1 happened to give `region`, which has no effect here, a chance association (p 0.002), so the next one is used.
SNAPSHOT_SEED = SEED + 2
SNAPSHOT_MONTHS = [date(2025 + (m > 12), (m - 1) % 12 + 1, 1) for m in range(1, 17)]
RATE_JUMP_FROM = date(2025, 11, 1)
# Share of the churn that has been recorded by the last date in the file: a 60-day outcome is not all known yet.
LABEL_KNOWN = {date(2026, 2, 1): 0.97, date(2026, 3, 1): 0.5, date(2026, 4, 1): 0.08}
UNKNOWN_TENURE = 999
UNKNOWN_TENURE_ROWS = 180
SNAPSHOT_COLUMNS = [
    "snapshot_id",
    "customer_id",
    "snapshot_date",
    "plan",
    "region",
    "tenure_months",
    "monthly_fee_eur",
    "annual_fee_eur",
    "logins_30d",
    "tickets_90d",
    "avg_session_min",
    "discount_pct",
    "is_internal_account",
    "campaign_code",
    "retention_call_outcome",
    "nps_last",
    "account_manager",
    "full_name",
    "email",
    "phone",
    "churned_60d",
]


def snapshot_row(
    rng: random.Random,
    index: int,
    customer: str,
    identity: dict[str, str],
    month: date,
    plan: tuple[str, float],
    region: str,
    tenure: int,
) -> dict[str, str]:
    engagement = normal(rng)
    session = normal(rng)
    name, fee = plan
    logins = max(0, round(12 + 5 * engagement + 2 * normal(rng)))
    tickets = poisson(rng, max(0.05, 1.1 - 0.5 * engagement))
    risk = (
        (-2.75 if month < RATE_JUMP_FROM else -1.95)
        - 0.7 * engagement
        + 0.25 * tickets
        - 0.01 * tenure
        + 0.5 * (session * session - 1)
        + (0.95 if name == "legacy" else 0.0)
    )
    churned = rng.random() < expit(risk)
    recorded = churned and rng.random() < LABEL_KNOWN.get(month, 1.0)
    fee_paid = round(fee * (1 + 0.06 * normal(rng)), 2)
    nps = "" if rng.random() < (0.5 if churned else 0.1) else str(min(10, max(0, round(6.5 + 2 * normal(rng)))))
    return {
        "snapshot_id": f"S{index:06d}",
        "customer_id": customer,
        "snapshot_date": month.isoformat(),
        "plan": name,
        "region": region,
        "tenure_months": str(tenure),
        "monthly_fee_eur": f"{fee_paid:.2f}",
        "annual_fee_eur": f"{fee_paid * 12:.2f}",
        "logins_30d": str(logins),
        "tickets_90d": str(tickets),
        "avg_session_min": f"{max(1.0, 20 + 9 * session):.1f}",
        "discount_pct": choose(rng, ["0", "5", "10", "15", "20"]),
        "is_internal_account": "1" if rng.random() < 0.004 else "0",
        "campaign_code": f"CMP-{int(rng.random() * 400):03d}",
        "retention_call_outcome": choose(rng, ["declined offer", "no answer", "accepted then left"])
        if recorded
        else "",
        "nps_last": nps,
        "account_manager": choose(rng, MANAGERS),
        **identity,
        "churned_60d": "1" if recorded else "0",
    }


def months_between(first: date, second: date) -> int:
    return (second.year - first.year) * 12 + second.month - first.month


def build_snapshots() -> list[dict[str, str]]:
    """Its own generator, so that adding this file does not move a byte of the older ones.

    A customer's second row is a later snapshot of the same customer: same plan and region, tenure moved on by the
    months between, and never after the first row has been labelled as churned.
    """
    rng = random.Random(SNAPSHOT_SEED)
    rows: list[dict[str, str]] = []
    firsts: list[tuple[dict[str, str], tuple[str, float]]] = []
    for i in range(SNAPSHOT_CUSTOMERS):
        month = SNAPSHOT_MONTHS[int(rng.random() * len(SNAPSHOT_MONTHS))]
        plan = weighted(rng, PLANS)
        row = snapshot_row(
            rng,
            i + 1,
            f"K{i:05d}",
            person(rng, 300_000 + i),
            month,
            plan,
            choose(rng, REGIONS),
            1 + int(rng.random() * 48),
        )
        rows.append(row)
        firsts.append((row, plan))
    # Customers who can be seen again: not churned, and not on the last snapshot of the file.
    eligible = [
        i
        for i in shuffled(SNAPSHOT_CUSTOMERS, rng)
        if firsts[i][0]["churned_60d"] == "0" and firsts[i][0]["snapshot_date"] < SNAPSHOT_MONTHS[-1].isoformat()
    ]
    for offset, i in enumerate(eligible[: SNAPSHOT_ROWS - SNAPSHOT_CUSTOMERS]):
        first, plan = firsts[i]
        start = date.fromisoformat(first["snapshot_date"])
        later = [m for m in SNAPSHOT_MONTHS if m > start]
        month = later[int(rng.random() * len(later))]
        identity = {k: first[k] for k in ("full_name", "email", "phone")}
        tenure = int(first["tenure_months"]) + months_between(start, month)
        rows.append(
            snapshot_row(
                rng,
                SNAPSHOT_CUSTOMERS + offset + 1,
                first["customer_id"],
                identity,
                month,
                plan,
                first["region"],
                tenure,
            )
        )
    rows.sort(key=lambda r: (r["snapshot_date"], r["snapshot_id"]))
    for i in shuffled(len(rows), rng)[:UNKNOWN_TENURE_ROWS]:
        rows[i]["tenure_months"] = str(UNKNOWN_TENURE)
    return rows


def write(path: Path, rows: list[dict[str, str]], columns: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("target", nargs="?", type=Path, default=TARGET)
    args = parser.parse_args(argv)
    args.target.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    train, test = build_splits(rng)
    number_rows(train, "T")
    number_rows(test, "E")
    write(args.target / "train.csv", train, COLUMNS)
    write(args.target / "test.csv", test, COLUMNS)
    predictions = build_predictions(rng)
    write(args.target / "predictions.csv", predictions, list(predictions[0]))
    clean_columns = [
        "subscriber_id",
        "variant",
        "assigned_at",
        "renewed",
        "upgraded",
        "app_open_7d",
        "arpu_eur",
        "support_contact",
        "refund_requested",
        "email",
    ]
    clean = experiment_rows(rng, 3012, 2988, CLEAN_PROPORTIONS, 0.25, date(2026, 9, 1), 14)
    write(args.target / "experiment_clean.csv", clean, clean_columns)
    broken_columns = ["subscriber_id", "variant", "assigned_at", "renewed", "arpu_eur", "support_contact", "email"]
    broken = experiment_rows(rng, 2640, 2360, BROKEN_PROPORTIONS, 2.1, date(2026, 8, 1), 14)
    write(args.target / "experiment_broken.csv", broken, broken_columns)
    write(args.target / "snapshots.csv", build_snapshots(), SNAPSHOT_COLUMNS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
