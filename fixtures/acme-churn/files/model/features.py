"""The columns the churn model uses."""

ID_COLUMNS = ["row_id", "customer_id", "snapshot_date"]
LABEL = "churned_60d"

FEATURES = [
    "plan",
    "region",
    "tenure_months",
    "monthly_fee_eur",
    "logins_30d",
    "tickets_90d",
    "payment_failures_90d",
    "discount_pct",
    "nps_last",
    "cancellation_reason",
    "days_since_last_login",
]


def add_recency(row):
    """Days since the customer last logged in, from the warehouse extract."""
    last = row["last_login_at"][:10]
    snap = row["snapshot_date"]
    row["days_since_last_login"] = (date_of(snap) - date_of(last)).days
    return row


def date_of(text):
    from datetime import date

    return date.fromisoformat(text)
