with products as (

    select * from {{ ref('stg_products') }}

),

final as (

    select
        product_id,
        name,
        category,
        list_price
    from products

)

select * from final
