-- One row per order from the ERP extract.
select
    order_id,
    order_date,
    shipped_date,
    channel,
    store_id,
    region,
    product_line,
    customer_id,
    units,
    net_amount,
    shipping_fee,
    status
from {{ source('erp', 'orders') }}
