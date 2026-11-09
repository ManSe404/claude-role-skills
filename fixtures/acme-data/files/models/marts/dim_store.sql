with stores as (

    select * from {{ ref('stg_stores') }}

),

final as (

    select
        store_id,
        store_name,
        city,
        region
    from stores

)

select * from final
