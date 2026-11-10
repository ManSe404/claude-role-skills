-- Drop the dw.tmp_* tables older than a week.
do $$
declare
  name text;
begin
  for name in
    select table_name from information_schema.tables
    where table_schema = 'dw' and table_name like 'tmp\_%'
  loop
    execute format('drop table if exists dw.%I', name);
  end loop;
end
$$;
