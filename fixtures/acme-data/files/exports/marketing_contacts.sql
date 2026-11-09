-- Contact list for the monthly mailing. Marketing loads the result into its campaign tool by hand.
select
    c.customer_id,
    c.first_name,
    c.last_name,
    c.email, c.national_id,
    c.city,
    c.loyalty_tier
from marts.dim_customer as c
where c.loyalty_tier in ('gold', 'silver');
