with source as (

    select * from {{ source('erp','customers') }}

),

final as (

    select
        customer_id,
        first_name,
        last_name,
        email,
        phone,
        national_id,
        cast(birth_date as date) as birth_date,
        city,
        loyalty_tier
    from source

)

select * from final
