{{ config(materialized='table') }}

with promotions as (

    select * from {{ ref('stg_promotions') }}

),

final as (

    select
        product_id,
        count(*) as campaigns,
        min(start_date) as first_campaign,
        max(end_date) as last_campaign,
        avg(discount_pct) as avg_discount_pct
    from promotions
    group by product_id

)

select * from final
