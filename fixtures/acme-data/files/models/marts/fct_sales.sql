{{ config(materialized='table') }}

-- One row per order line, on the day it was sold.
with order_lines as (

    select * from {{ ref('int_order_lines') }}

),

products as (

    select product_id, list_price from {{ ref('dim_product') }}

),

final as (

    select
        l.order_id,
        l.line_no,
        l.order_date as sale_date,
        l.customer_id,
        l.store_id,
        l.product_id,
        l.quantity,
        l.unit_price,
        l.quantity * l.unit_price * (1 - coalesce(promo.discount_pct, 0) / 100.0) as net_amount,
        l.quantity * p.list_price as list_amount,
        promo.promotion_id,
        coalesce(promo.discount_pct, 0) as discount_pct
    from order_lines as l
    left join products as p on p.product_id = l.product_id
    left join {{ ref('stg_promotions') }} as promo on l.product_id = promo.product_id

)

select * from final
