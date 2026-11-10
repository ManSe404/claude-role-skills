-- Margin per store for the previous month. Runs on the 15th, once the month's returns and credit notes are in.
delete from dw.margin_monthly
where month = date_trunc('month', current_date - interval '1 month');

insert into dw.margin_monthly (month, store_id, revenue, cost, margin)
select
  date_trunc('month', order_date) as month,
  store_id,
  sum(amount) as revenue,
  sum(cost_amount) as cost,
  sum(amount) - sum(cost_amount) as margin
from dw.orders
where order_date >= date_trunc('month', current_date - interval '1 month')
  and order_date < date_trunc('month', current_date)
group by 1, 2;
