-- September against October, for the headline.
select '2026-09' as period, sum(net_amount) as net_revenue
from analytics.orders
where status = 'completed'
  and order_date between '2026-09-01' and '2026-09-24'
union all
select '2026-10' as period, sum(net_amount) as net_revenue
from analytics.orders
where status = 'completed'
  and order_date between '2026-10-01' and '2026-10-31';
