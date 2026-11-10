-- silver.customers: the ERP customer master, reloaded in full every morning from the ERP replica.
truncate table silver.customers;

insert into silver.customers
  (customer_id, name, tax_id, email, phone, city, country, segment, updated_at, load_date)
select
  customer_id,
  trim(name) as name,
  nullif(trim(tax_id), '') as tax_id,
  lower(trim(email)) as email,
  phone,
  city,
  country,
  segment,
  updated_at,
  cast(:load_date as date) as load_date
from erp_replica.customers;
