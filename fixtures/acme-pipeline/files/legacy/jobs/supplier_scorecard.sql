-- Weekly supplier scorecard: late and short deliveries per supplier over the last four weeks.
truncate table dw.supplier_scorecard;

insert into dw.supplier_scorecard (supplier_id, deliveries, late, short)
select
  supplier_id,
  count(*) as deliveries,
  sum(case when received_at > promised_at then 1 else 0 end) as late,
  sum(case when received_qty < ordered_qty then 1 else 0 end) as short
from dw.supplier_deliveries
where received_at >= current_date - 28
group by supplier_id;
