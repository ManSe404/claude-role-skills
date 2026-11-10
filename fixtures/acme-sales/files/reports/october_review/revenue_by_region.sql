-- Net revenue per region in October.
select
    region,
    sum(net_amount) as net_revenue
from analytics.orders
where status = 'completed'
  and order_date between '2026-10-01' and '2026-10-31'
  and region <> 'unknown'
group by region
order by region;
