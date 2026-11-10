# Reading the audit

A flag is a place to look, not a verdict. Every flag ends as a finding with a file and a line, or
cleared with a reason on the page.

## Target leakage

Each feature's `strength` is how well it alone orders the rows by the label (ROC-AUC, folded so 0.5 is
none and 1.0 is perfect): ranks for numbers and dates, an out-of-fold positive rate per category, and how well
its presence alone predicts the label.

| strength | reading |
|---|---|
| 0.95 and up | treat as a leak until proven otherwise: a real feature almost never does this alone |
| 0.85 to 0.95 | suspiciously strong: read where it comes from |
| below 0.85 | no sign from this check |

Leakage is a question of time, not of strength: does this column exist at the moment of the prediction? A status
written after the event, a field filled by a closing process, an amount refunded, a score computed from the
outcome. Read the feature code, the SQL and the table's load time. `name_suggests_outcome` only flags a
name to read; it is a place to start, not evidence.

## Time leakage

- `after_prediction_moment`: a feature dated after `--time` was not known then. Dates are compared as
  calendar days, so a timestamp on the snapshot day itself is not flagged.
- `split_order`: `test_rows_on_or_before_train_last` counts test rows that are not after training. A random split
  shows up here as a large number; a few rows usually mean rows were copied.
- `train_rows_with_labels_after_test_start`: with `--horizon-days`, training rows whose label window
  reaches into the test period. Their labels were only known then, so training on them used the future.

## The same data on both sides

- Entity overlap: the same customer in train and test makes the test score too good, because the model
  learned that customer. Whether it is a bug depends on what the model is for: if it will only ever score
  existing customers in later periods, a time-based split may be right, and the page says so; if it must generalise
  to new customers, split by entity. Follow the project's own statement of what the model does.
- Exact duplicates: every column equal except `--id`. A duplicate across splits inflates the test score by
  showing the model an answer it has seen. Duplicates within a split double a row's weight.

## Class balance and missingness

- A rare class (under 5%) makes accuracy useless and PR-AUC necessary, and needs enough rare cases to train at all.
  `splits_differ` says the positive rate differs between train and test by more than chance.
- Missingness that differs by class: a column filled less often for one class. It means the moment or
  the way the data gets recorded depends on the outcome: either a leak (a field only filled after an event) or
  a real signal that may not exist at prediction time. Either way, decide what a missing value means at
  serving before training on it. The column tests are corrected with Holm: `differs` needs both a difference
  of 5 points or more and a corrected p-value below 0.05.

## Drift

The population stability index compares a feature's distribution in train and test: the sum over bins of
(share in test minus share in train) times the logarithm of their ratio. Bins are the training deciles for numbers
and the values themselves for categories, with missing as a bin of its own.

| PSI | reading |
|---|---|
| under 0.10 | stable |
| 0.10 to 0.25 | a moderate shift, look at it |
| above 0.25 | a major shift, the model was trained on another population |

A high PSI says the feature moved, not that the model got worse: check it against the model's evaluation.

## Personal columns

Columns listed in `personal_columns` must not be used as features: drop them before training unless there is a
documented legal basis. They are excluded from the checks above and from everything the page shows.

## What a clean audit does not prove

- A window computed past the prediction moment looks normal in the values. Read the feature code.
- Two features that together give the answer pass one by one.
- A leak can be in how rows were selected, not in any column, such as keeping only customers who stayed for a year.
