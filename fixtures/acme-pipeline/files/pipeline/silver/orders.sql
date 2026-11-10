-- silver.orders: the ERP order lines of one delivery, typed.
-- Runs after the rules of checks/quarantine.yaml have flagged rows in bronze.erp_orders.
-- Parameter :load_date is the delivery date.
delete from silver.orders where load_date = cast(:load_date as date);

insert into silver.orders
  (order_id, line_no, order_date, store_id, customer_id, product_id, quantity, weight_g, amount, currency, status,
   load_date)
select
  order_id,
  cast(line_no as integer) as line_no,
  cast(order_date as date) as order_date,
  store_id,
  customer_id,
  product_id,
  cast(quantity as integer) as quantity,
  cast(weight_g as integer) as weight_g,
  cast(amount as numeric(12, 2)) as amount,
  currency,
  status,
  cast(:load_date as date) as load_date
from bronze.erp_orders
where load_date = cast(:load_date as date)
  and not quarantined;
