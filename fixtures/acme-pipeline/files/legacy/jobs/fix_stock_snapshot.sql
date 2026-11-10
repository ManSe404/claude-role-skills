-- Negative stock breaks the store report: set it to zero in tonight's snapshot.
update dw.stock_snapshot
set on_hand = 0
where on_hand < 0
  and snapshot_date = current_date;
