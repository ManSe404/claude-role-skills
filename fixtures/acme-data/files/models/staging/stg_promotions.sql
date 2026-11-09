with source as (

    select * from {{ source('erp','promotions') }}

),

final as (

    select
        promotion_id,
        product_id,
        cast(start_date as date) as start_date,
        cast(end_date as date) as end_date,
        cast(discount_pct as decimal(5, 2)) as discount_pct
    from source

)

select * from final
