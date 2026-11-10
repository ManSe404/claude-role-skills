-- bronze.crm_activities: visits, calls and offers of the previous day, as delivered. All columns are text.
create table if not exists bronze.crm_activities (
  activity_id text,
  customer_id text,
  contact_id text,
  activity_date text,
  type text,
  subject text,
  deal_value text,
  owner text,
  load_date date not null
);
