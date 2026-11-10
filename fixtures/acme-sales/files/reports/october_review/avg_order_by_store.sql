-- Average order per store, and the average across stores for the headline.
with store_orders as (
    select
        store_id,
        count(*) as orders,
        avg(net_amount) as avg_order
    from analytics.orders
    where channel = 'store'
      and status = 'completed'
      and order_date between '2026-10-01' and '2026-10-31'
    group by store_id
)
select store_id, orders, avg_order
from store_orders
order by avg_order desc;

select avg(avg_order) as avg_order_all_stores
from store_orders;
