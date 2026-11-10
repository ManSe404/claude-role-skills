-- bronze.erp_invoices: the ERP invoices as delivered, one partition per delivery date. All columns are text.
create table if not exists bronze.erp_invoices (
  invoice_id text,
  order_id text,
  invoice_date text,
  store_id text,
  amount text,
  currency text,
  due_date text,
  load_date date not null
);
