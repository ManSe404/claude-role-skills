-- silver.invoices: the ERP invoices of one delivery, typed.
-- The amount goes through util.parse_amount (pipeline/functions/parse_amount.sql): see the incident of 2026-09-14.
delete from silver.invoices where load_date = cast(:load_date as date);

insert into silver.invoices (invoice_id, order_id, invoice_date, store_id, amount, currency, due_date, load_date)
select
  invoice_id,
  order_id,
  cast(invoice_date as date) as invoice_date,
  store_id,
  util.parse_amount(amount) as amount,
  currency,
  cast(due_date as date) as due_date,
  cast(:load_date as date) as load_date
from bronze.erp_invoices
where load_date = cast(:load_date as date);
