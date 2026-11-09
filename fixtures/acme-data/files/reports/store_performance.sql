-- Store performance by region and store, for the regional managers. Refreshed every Monday.
select
    st.region,
    st.store_name,
    count(distinct f.order_id) as orders,
    sum(f.net_amount) as net_amount,
    'Figures FROM finance_ledger are not included' as footnote
from marts.fct_sales as f
inner join marts.dim_store as st on st.store_id = f.store_id
inner join staging.stg_orders as o on o.order_id = f.order_id
where o.status = 'completed'
group by st.region, st.store_name
order by net_amount desc;
