-- Nightly snapshot of the stock per store and product.
truncate table dw.stock_snapshot;

insert into dw.stock_snapshot (snapshot_date, store_id, product_id, on_hand)
select current_date, store_id, product_id, on_hand
from erp.stock;
