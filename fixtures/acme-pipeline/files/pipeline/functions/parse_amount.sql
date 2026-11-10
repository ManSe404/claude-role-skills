-- util.parse_amount: a delivered amount as numeric(12, 2), whatever number format the ERP export uses.
-- Reads 1234.50, 1234,50 and 1.234,50; an empty value is null. Added after the incident of 2026-09-14.
create schema if not exists util;

create or replace function util.parse_amount(raw text) returns numeric(12, 2) as $$
  select case
    when raw is null or trim(raw) = '' then null
    when position(',' in raw) > 0 then cast(replace(replace(trim(raw), '.', ''), ',', '.') as numeric(12, 2))
    else cast(trim(raw) as numeric(12, 2))
  end
$$ language sql immutable;
