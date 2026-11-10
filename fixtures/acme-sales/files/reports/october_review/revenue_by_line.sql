-- Net revenue per product line in October.
select
    o.product_line,
    sum(o.net_amount) as net_revenue
from analytics.orders as o
left join analytics.order_promotions as p
    on p.order_id = o.order_id
where o.status = 'completed'
  and o.order_date between '2026-10-01' and '2026-10-31'
group by o.product_line
order by o.product_line;
