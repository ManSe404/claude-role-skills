-- Orders by status in October, for reference.
select status, count(*) as orders
from analytics.orders
where order_date between '2026-10-01' and '2026-10-31'
group by status
order by status;
