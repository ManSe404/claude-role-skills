-- Loyalty points per card from the old loyalty card system.
truncate table dw.loyalty_points;

insert into dw.loyalty_points (card_id, customer_id, points)
select card_id, customer_id, sum(points)
from loyalty.transactions
group by card_id, customer_id;
