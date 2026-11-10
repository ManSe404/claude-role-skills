-- Sales per store and day of the last 7 days, for finance. The cron line writes the result as CSV.
select o.order_date, o.store_id, s.store_name, sum(o.amount) as revenue
from dw.orders as o
join dw.stores as s on s.store_id = o.store_id
where o.order_date >= current_date - 7
group by o.order_date, o.store_id, s.store_name
order by o.order_date, o.store_id;
