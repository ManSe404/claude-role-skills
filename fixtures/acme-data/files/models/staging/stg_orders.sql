{{ config(materialized='view') }}

with source as (

    -- FROM old_orders_backup
    select * from {{ source('erp','orders') }}

),

final as (

    select
        order_id,
        customer_id,
        store_id,
        cast(order_date as date) as order_date,
        status
    from source

)

select * from final
