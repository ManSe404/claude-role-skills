{{ config(materialized='table') }}

with customers as (

    select * from {{ ref('stg_customers') }}

),

final as (

    select
        customer_id,
        first_name,
        last_name,
        email,
        phone,
        national_id,
        birth_date,
        city,
        loyalty_tier
    from customers

)

select * from final
