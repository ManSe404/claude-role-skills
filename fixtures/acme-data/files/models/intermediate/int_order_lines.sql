{{ config(materialized='ephemeral') }}

with orders as (

    select * from {{ ref('stg_orders') }}

),

lines as (

    select * from {{ ref('stg_order_lines') }}

),

final as (

    select
        l.order_id,
        l.line_no,
        l.product_id,
        l.quantity,
        l.unit_price,
        o.customer_id,
        o.store_id,
        o.order_date,
        EXTRACT(YEAR FROM order_date) as order_year
    from lines as l
    inner join orders as o on o.order_id = l.order_id
    where o.status <> 'cancelled'

)

select * from final
