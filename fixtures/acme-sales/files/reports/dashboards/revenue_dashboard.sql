-- Monthly revenue for the BI dashboard. Maintained by the BI team.
select
    date_trunc('month', shipped_date) as revenue_month,
    sum(net_amount + shipping_fee) as net_revenue
from staging.stg_orders
where status in ('completed', 'returned')
  and channel <> 'staff'
group by 1
