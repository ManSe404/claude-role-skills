with source as (

    select * from {{ source('erp','stores') }}

),

final as (

    select
        store_id,
        name as store_name,
        city,
        region
    from source

)

select * from final
