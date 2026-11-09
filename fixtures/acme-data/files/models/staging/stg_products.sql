with source as (

    select * from {{ source('erp','products') }}

),

final as (

    select
        product_id,
        name,
        category,
        cast(list_price as decimal(10, 2)) as list_price
    from source

)

select * from final
