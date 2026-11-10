-- silver.payments: payments received against invoices, from one ERP delivery, typed.
delete from silver.payments where load_date = cast(:load_date as date);

insert into silver.payments (payment_id, invoice_id, paid_on, amount, currency, method, load_date)
select
  payment_id,
  invoice_id,
  cast(paid_on as date) as paid_on,
  cast(amount as numeric(12, 2)) as amount,
  currency,
  method,
  cast(:load_date as date) as load_date
from bronze.erp_payments
where load_date = cast(:load_date as date);
