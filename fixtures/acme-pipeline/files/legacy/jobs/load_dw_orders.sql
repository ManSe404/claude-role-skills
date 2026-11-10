-- Load yesterday's order extract into dw.orders.
create temp table orders_in (like dw.orders);

\copy orders_in from '/data/extracts/orders_latest.csv' csv header

insert into dw.orders
select * from orders_in
on conflict (order_id, line_no) do nothing;
