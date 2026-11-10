-- gold.sales_daily: what each franchise store bought per day, for finance and the BI sales board.
-- Rebuilt in full by job build_sales_daily after load_erp_orders.
create or replace table gold.sales_daily as
select
  o.order_date as sales_date,
  o.store_id,
  s.store_name,
  o.currency,
  count(distinct o.order_id) as orders,
  count(*) as order_lines,
  sum(o.amount) as gross_revenue,
  sum(case when o.status = 'cancelled' then o.amount else 0 end) as cancelled_amount,
  sum(case when o.status <> 'cancelled' then o.amount else 0 end) as net_revenue,
  sum(o.weight_g) / 1000.0 as kg_eq,
  s.customer_id,
  c.email as customer_email,
  current_timestamp as built_at
from silver.orders as o
join ref.stores as s on s.store_id = o.store_id
left join silver.customers as c on c.customer_id = s.customer_id
group by o.order_date, o.store_id, s.store_name, o.currency, s.customer_id, c.email;
