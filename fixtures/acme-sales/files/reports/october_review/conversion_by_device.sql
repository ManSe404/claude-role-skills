-- Conversion per device in October.
select
    device,
    sum(orders) as orders,
    sum(sessions) as sessions,
    100.0 * sum(orders) / sum(sessions) as conversion_pct
from analytics.sessions
where day between '2026-10-01' and '2026-10-31'
group by device
order by device;
