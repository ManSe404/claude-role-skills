-- Net revenue per month, the finance definition: completed orders, by the day the order was placed,
-- net of tax and without the shipping fee.
select
    date_trunc('month', order_date) as revenue_month,
    sum(net_amount) as net_revenue
from {{ ref('stg_orders') }}
where status = 'completed'
group by 1
