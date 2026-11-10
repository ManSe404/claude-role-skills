-- Web conversion in October: orders per visit.
select
    sum(orders) as orders,
    sum(case when logged_in then sessions else 0 end) as sessions,
    100.0 * sum(orders) / sum(case when logged_in then sessions else 0 end) as conversion_pct
from analytics.sessions
where day between '2026-10-01' and '2026-10-31';
