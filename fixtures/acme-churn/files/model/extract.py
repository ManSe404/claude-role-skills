"""Build the snapshot table the churn model trains on, one row per customer and snapshot date."""

SNAPSHOT_SQL = """
select
    c.customer_id,
    s.snapshot_date,
    c.full_name,
    c.email,
    c.phone,
    p.plan,
    p.region,
    s.tenure_months,
    p.monthly_fee_eur,
    a.logins_30d,
    a.tickets_90d,
    a.payment_failures_90d,
    p.discount_pct,
    (select max(l.login_ts) from logins l where l.customer_id = c.customer_id) as last_login_at,
    n.nps_last,
    x.cancellation_reason,
    case when x.cancelled_at between s.snapshot_date and s.snapshot_date + 60 then 1 else 0 end as churned_60d
from snapshots s
join customers c using (customer_id)
join plans p on p.customer_id = c.customer_id and p.as_of = s.snapshot_date
join activity_rollup a on a.customer_id = c.customer_id and a.as_of = s.snapshot_date
left join nps_latest n on n.customer_id = c.customer_id
left join cancellations x on x.customer_id = c.customer_id
"""


def load_snapshots(connection):
    """Read the snapshots into a list of dicts."""
    with connection.cursor() as cursor:
        cursor.execute(SNAPSHOT_SQL)
        names = [column[0] for column in cursor.description]
        return [dict(zip(names, row)) for row in cursor.fetchall()]
