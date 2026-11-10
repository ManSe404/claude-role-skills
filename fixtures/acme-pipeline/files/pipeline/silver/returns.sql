-- silver.returns: goods the stores sent back, from one ERP delivery, typed.
delete from silver.returns where load_date = cast(:load_date as date);

insert into silver.returns (return_id, order_id, return_date, store_id, amount, currency, reason, load_date)
select
  return_id,
  order_id,
  cast(return_date as date) as return_date,
  store_id,
  cast(amount as numeric(12, 2)) as amount,
  currency,
  reason,
  cast(:load_date as date) as load_date
from bronze.erp_returns
where load_date = cast(:load_date as date);
