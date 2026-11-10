-- bronze.erp_payments: payments received against invoices, as delivered by the ERP. All columns are text.
create table if not exists bronze.erp_payments (
  payment_id text,
  invoice_id text,
  paid_on text,
  amount text,
  currency text,
  method text,
  load_date date not null
);
