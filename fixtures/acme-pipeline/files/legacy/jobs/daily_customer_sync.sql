-- Copy the customer master from the ERP into dw.customers, in full.
truncate table dw.customers;

insert into dw.customers (customer_id, name, tax_id, email, phone, city, segment)
select customer_id, name, tax_id, email, phone, city, segment
from erp.customers;
