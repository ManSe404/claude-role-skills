-- bronze.crm_contacts: people at the CRM accounts, a full extract per delivery. Holds personal data.
-- Columns as in sources/crm/README-vendor.md.
create table if not exists bronze.crm_contacts (
  contact_id text,
  customer_id text,
  first_name text,
  last_name text,
  job_title text,
  email text,
  phone text,
  iban text,
  consent_date text,
  preferred_language text,
  load_date date not null
);
