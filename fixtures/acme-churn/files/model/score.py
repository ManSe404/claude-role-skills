"""Score the holdout with every candidate and write predictions.csv: one row per id, one column per model."""

import csv


def write_predictions(path, rows, models):
    names = list(models)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["prediction_id", "churned_60d", "plan", "region", *names])
        for row in rows:
            writer.writerow([row["prediction_id"], row["churned_60d"], row["plan"], row["region"],
                             *[models[n].predict_proba([row["x"]])[0][1] for n in names]])
