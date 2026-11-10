"""Split the snapshots into train and test."""

CUT = "2026-04-01"


def split(rows):
    """Train on everything before the cut, test on the rest."""
    train = [row for row in rows if row["snapshot_date"] < CUT]
    test = [row for row in rows if row["snapshot_date"] >= CUT]
    return train, test
