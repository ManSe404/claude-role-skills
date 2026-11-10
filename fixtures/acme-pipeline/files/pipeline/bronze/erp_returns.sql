-- bronze.erp_returns: goods the stores sent back, as delivered by the ERP. All columns are text.
create table if not exists bronze.erp_returns (
  return_id text,
  order_id text,
  return_date text,
  store_id text,
  amount text,
  currency text,
  reason text,
  load_date date not null
);
