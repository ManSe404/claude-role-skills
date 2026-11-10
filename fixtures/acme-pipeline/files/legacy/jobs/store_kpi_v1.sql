-- The first store KPIs, before the BI sales board.
truncate table dw.store_kpi_v1;

insert into dw.store_kpi_v1 (store_id, order_date, lines, revenue)
select store_id, order_date, count(*), sum(amount)
from dw.orders_v1
group by store_id, order_date;
