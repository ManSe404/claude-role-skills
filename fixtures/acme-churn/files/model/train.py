"""Train the churn model and write it to disk."""

import joblib
from features import FEATURES, LABEL
from sklearn.ensemble import HistGradientBoostingClassifier
from split import split


def train(rows):
    train_rows, test_rows = split(rows)
    model = HistGradientBoostingClassifier(max_depth=6, random_state=7)
    model.fit([[row[f] for f in FEATURES] for row in train_rows], [row[LABEL] for row in train_rows])
    joblib.dump(model, "models/gbt_v7.joblib")
    return model, test_rows
