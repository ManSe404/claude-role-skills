"""The git history of the acme-churn fixture.

The files under files/ are the state after the last commit. Each commit lists the files it adds.

The story: Acme Stream started a churn model in the spring, added training and scoring, and then the business asked
for three things. Everything here is fictional.
"""

MILA = ("Mila Cerović", "mila.cerovic@example.com")
TOMA = ("Toma Lipić", "toma.lipic@example.com")

COMMITS = [
    {
        "date": "2026-03-16T10:20:00+01:00",
        "author": TOMA,
        "message": "Start the churn model: extract, features, split",
        "add": [".gitignore", "README.md", "model/extract.py", "model/features.py", "model/split.py"],
    },
    {
        "date": "2026-04-22T15:10:00+02:00",
        "author": MILA,
        "message": "Train the gradient-boosted model and score the holdout",
        "add": ["model/train.py", "model/score.py"],
    },
    {
        "date": "2026-10-12T09:05:00+02:00",
        "author": TOMA,
        "message": "Briefs: retention offers, auto-renew reminders, the renewal-nudge experiment",
        "add": [
            "docs/briefs/retention-offers.md",
            "docs/briefs/auto-renew-reminders.md",
            "docs/briefs/renewal-nudge-experiment.md",
        ],
    },
]
