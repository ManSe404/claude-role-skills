# Acme Stream churn model

Acme Stream sells monthly and annual subscriptions (fictional). This repository holds the churn
model: the extract, the features, the split and training, and the briefs that ask for models.

`data/` is not committed. It holds:

| file | what it is |
|---|---|
| `train.csv`, `test.csv` | one row per customer snapshot; `churned_60d` is 1 if the customer cancelled within 60 days of `snapshot_date`; the label is known 60 days later |
| `predictions.csv` | a holdout scored by three candidates: `baseline_score` (the current score), `logreg_v2` and `gbt_v7`; `prediction_id`, `churned_60d`, slice columns `plan` and `region` |
| `experiment_broken.csv`, `experiment_clean.csv` | the renewal-nudge A/B test, one row per subscriber, see `docs/briefs/` |

The prediction is made on `snapshot_date`. Features are as of that day; a feature known later was not
known then. Personal columns exist in the data for joining; nothing in this repository should
need them.

## Layout

- `model/extract.py`: the warehouse extract;
- `model/features.py`: the feature list;
- `model/split.py`: the train and test split;
- `model/train.py`: training;
- `model/score.py`: writes the predictions file;
- `docs/briefs/`: what the business has asked for.
