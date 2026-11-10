-- bronze.crm_customers: the CRM accounts, a full extract per delivery. Columns as in sources/crm/README-vendor.md.
create table if not exists bronze.crm_customers (
  customer_id text,
  company_name text,
  tax_id text,
  segment text,
  status text,
  city text,
  country text,
  credit_limit text,
  created_on text,
  closed_on text,
  parent_customer_id text,
  key_account_manager text,
  load_date date not null
);
