# Plan: pack `data-scientist`

Status: built on 2026-11-10 from Stefan's brief. Decisions are at the end. Last pack of this series.

## Goal

A pack for the person who answers for a model or an experiment. Four jobs where the usual failure is
a confident number that is wrong: building the wrong thing, trusting a training set that leaks, calling
noise a win, and reading an A/B test that was broken from the start.

Same format as the other packs: `SKILL.md` in the fixed order, scripts that count, a page that is
JSON drawn by `render_page.py`. Every statistic is computed by the scripts and tested against values
known independently.

Out of scope:
- general statistics questions, profiling a table, hypothesis tests on ordinary data (`data:*` skills from
  the Anthropic plugin: `statistical-analysis`, `explore-data`, `analyze`, `validate-data`);
- numbers people ask about (`metric-spec`, `number-moved`, `number-reconcile`, `report-review`);
- LLM solutions (`ai-pattern`, `ai-review`), and LLM evals, retrieval tuning and traces (a later
  `ai-engineering` pack);
- training a model, tuning hyperparameters or serving: these skills read files of data and predictions.

Descriptions say "predictive model", "training set" or "A/B test" so they do not take general requests.

## Skills

### 1. `ds-frame`: before modelling

When: someone asks for a model or a prediction, before anything is trained.
Input: a brief, optionally a folder of history.

Steps:
1. **Frame:** the decision the prediction changes, the exact target and the point in time it is
   predicted, when the label is known, what each error costs. Each with where it came from.
2. **Size** from history if there is any: `data_profile.py`, `measure.py` for the base rate and how a
   stated rule does.
3. **Rules:** facts as JSON, `frame_rules.py` applies the ladder (lookup or rule, simple score, linear or
   logistic, gradient-boosted trees, deep learning). An LLM problem goes to `ai-pattern`.
4. **Economics:** what the two trivial policies cost, the break-even probability, the ceiling a perfect
   model could save.
5. **Choose** the lowest rung that passes, name the baseline that must be beaten, write acceptance
   criteria with thresholds. The page.

Never: starts a model; overrules a rule of the script; states a cost the brief did not give without marking it.

### `ds-explore`: before the split (added 2026-11-10)

Added after the pack was built. Exploring had been left to Anthropic's `data:explore-data`, which is generic (it never
mentions a target, a label or leakage), is not part of this repository and is not available on every account. The pack
also had a hole: `ds-frame` comes before anyone looks closely at the data and `ds-dataset` needs a split that exists.

When: one table and a yes/no target, before any split. Input: the file, the target, the id, entity and time columns,
how long until the outcome is known.

`explore_target.py`: the rate per period, whether the newest labels can be known yet, each feature's distribution and
codes for unknown, strength with a seeded bootstrap interval, a test per feature corrected by Holm across all of them
(for a number, a Mann-Whitney test for a trend and a chi-square over bins for any shape, the smaller p-value doubled), the
shape, segments, whether missing carries signal, redundant pairs, leak suspects. `shuffled`, `out_of_fold_rates` and
`strongest` moved from `dataset_audit.py` to `model_stats.py` so that both use one definition.

The data analyst keeps the general look at a table in the `data` plugin; the same script can back an analyst version.

Not covered: a numeric target, interactions between features, whether a feature is known at prediction time.

Fixture: `extras/data/snapshots.csv`, 6,000 rows from their own generator so no older file moved by a byte. Planted: the
rate jumps from 2025-11, the last three months' labels are not in, 999 for unknown tenure, a U-shaped feature, a segment,
a redundant fee, 400 campaign codes, a near-constant flag, a column filled only for churners, missing values that carry
signal, repeated customers and a column of account managers' names whose levels must stay numbered.

### 2. `ds-dataset`: audit a training set

When: before anyone trusts a model built on a training set, with train and test files at hand.
Input: the train and test files, the label, entity, id and time columns; the modelling code if there is any.

Steps:
1. **Shape:** `data_profile.py`.
2. **Audit:** `dataset_audit.py`: target leakage (single-feature strength, presence of a value by class, names),
   time leakage (feature timestamps after the prediction moment, the order of the splits, label windows
   crossing the cut), the same entity on both sides, exact duplicates across splits, class balance, missingness
   that differs by class, drift by population stability index (PSI), personal columns.
3. **Read** the code behind each flag, so a flag becomes a finding with file:line or is cleared.
4. **Verdict:** can a model built on this be trusted, and what must change first. The page.

Never: changes the data or the code; calls a strong feature a leak without reading where it comes from.

### 3. `ds-evaluate`: compare models

When: two or more trained models with a file of predictions, before choosing one.
Input: one or more prediction files (id, label, one score column per model, optional slice columns), the
baseline's name, the costs of each error.

Steps:
1. **Read and check** the file: labels, scores, duplicate ids; every model compared on the same rows.
2. **Compare:** `model_eval.py`: ROC-AUC, PR-AUC, log loss, Brier (classification); MAE, RMSE, bias (regression);
   seeded bootstrap intervals; a paired bootstrap difference against the baseline, called "better", "worse"
   or "inside the noise".
3. **Calibration** table, and a threshold chosen from the costs, with an out-of-sample check.
4. **Slices:** each slice's metric and interval, the worst slices; too-small slices are not ranked.
5. **Recommend** which model, or none, and what must happen before it is used. The page.

Never: calls a difference inside the noise a win; ranks a slice without its interval; shows an id.

### 4. `ds-experiment`: A/B tests

When: before an A/B test (size it) or after one (read it).
Input: the plan's numbers; afterwards one file with one row per randomised unit.

Steps:
1. **Before launch:** `ab_test.py plan`: sample size or minimum detectable effect, correction for
   several metrics, how long at the given traffic.
2. **After:** sample ratio mismatch first; a broken split stops the read-out and no metric is printed.
3. **Read** `ab_test.py read`: intervals for proportions and means, Holm correction over the metrics a ship
   could rest on, guardrails with their margins, peeking, a call of ship, do not ship or inconclusive.
4. **Say** what the call rests on. The page.

Never: reads a metric past a sample ratio mismatch; ships on an uncorrected p-value; overrides the call.

## Scripts

All standard library, read-only, JSON on stdout, CSV and JSON Lines. Columns and counts only.

| script | skills | what it does |
|---|---|---|
| `model_stats.py` (shared) | dataset, evaluate, experiment | The statistics, one source: AUC and average precision by a sweep over tied scores, log loss, Brier, seeded bootstrap draws, Wilson, chi-square tail, two proportions, Welch, Holm, sample sizes, PSI, peeking table. |
| `measure.py`, `data_profile.py` (shared) | all four | Loading, cleaning, personal column detection, shape. |
| `frame_rules.py` | frame | Ladder rules on the facts of a brief, in the pattern of `decide.py`; the economics; the baseline. |
| `dataset_audit.py` | dataset | The eight audits. Prints columns and counts, never a value. |
| `model_eval.py` | evaluate | Metrics, bootstrap, paired comparison, calibration, thresholds, slices. |
| `ab_test.py` | experiment | `plan` and `read`. |

The bootstrap resamples rows through weights over a sort done once per model, because a resort per resample
is too slow in pure Python. A row's sequence comes from `Random.random()`, the one method whose sequence Python
guarantees across versions.

## Charts

The existing `chart` block is enough: `bar` for PSI, single-feature strength and worst slices; `line` for
calibration and for cost against threshold. `shared/render_page.py` is not changed.

## Fixture: `fixtures/acme-churn/` (all fictional)

A subscription business predicting churn. `files/` (a small `model/` folder, `docs/briefs/`), `history.py`,
`extras/data/` generated by a seeded `make_data.py` kept beside them.

Planted, recorded as importable constants in `tests/test_fixture_acme_churn.py`:
1. a feature only known after churn (`cancellation_reason`);
2. a timestamp leak: `last_login_at` later than `snapshot_date` on a known number of rows;
3. the same customers in train and test;
4. exact duplicates across the splits;
5. missingness that differs by class (`nps_last`);
6. drift in one feature with a known PSI range (`monthly_fee_eur`);
7. predictions: one model's win inside the noise, another's real;
8. one model that ranks well but is badly calibrated;
9. one slice where a model is much worse;
10. an experiment with a sample ratio mismatch, and one without, where the primary metric is significant
    until corrected for several metrics.

Briefs: one where a rule is right (catches overbuilding), one that justifies a model, one for the experiment.
Personal columns are present and never shown.

## Evals (`claude plugin eval`)

1. **frame-catches-overbuilding:** the rule, not a model.
2. **frame-justifies-a-model:** a learned model, the baseline named, criteria.
3. **dataset-finds-the-leaks:** at least five of the planted problems, no personal value.
4. **evaluate-calls-noise-noise:** one win real, one inside the noise, the calibration, the slice.
5. **experiment-reads-correctly:** the broken split stops, the correction changes the call.
6. **explore-finds-what-matters:** at least six of nine planted facts, the leak not recommended, no personal value.

Each has a `skill-fired` grader. Evals run only when Stefan asks.

## Other

- `roles/data-scientist.md`, `plugin.json`, the marketplace entry, the expected list in
  `tests/test_skill_files.py`, `pyproject.toml`, README section, CLAUDE.md, the `model_stats.py` marker.
- Real runs on the fixture: each skill headless on a fresh build, a cheap call first, under $12 in total, each
  page recomputed by hand and copied to `references/example.json`.

## Decisions (Stefan, 2026-11-10, in the brief)

1. Four skills as above, standard library only, statistics implemented by hand.
2. Accuracy first: tests use values known independently.
3. A personal value never reaches a script's output; every SKILL.md forbids printing rows with personal columns.
4. A sample ratio mismatch stops the read-out.
