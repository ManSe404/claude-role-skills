with source as (

    select * from {{ source('erp','order_lines') }}

),

final as (

    select
        order_id,
        line_no,
        product_id,
        quantity,
        cast(unit_price as decimal(10, 2)) as unit_price
    from source

)

select * from final
