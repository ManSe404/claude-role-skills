-- bronze.erp_orders: the ERP order lines as delivered, one partition per delivery date (load_date).
-- Every delivered column is kept as text; typing happens in silver.
create table if not exists bronze.erp_orders (
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
  row_id text generated always as (order_id || '/' || line_no) stored,
  quarantined boolean not null default false,
  load_date date not null
);
