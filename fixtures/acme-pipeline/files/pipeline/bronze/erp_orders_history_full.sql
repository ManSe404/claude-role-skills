-- bronze.erp_orders_history_full: a one-off copy of every order line of the old warehouse, 2014 to June 2026,
-- loaded on 2026-06-20 to reconcile the new silver.orders against the old reports.
-- Drop it once finance has signed the reconciliation off.
create table if not exists bronze.erp_orders_history_full (
  order_id text,
  line_no text,
  order_date text,
  store_id text,
  customer_id text,
  product_id text,
  quantity text,
  weight_g text,
  amount text,
  currency text,
  status text,
  sales_rep_code text,
  audit_user text,
  audit_changed_at text,
  source_system text,
  copied_at timestamp
);
