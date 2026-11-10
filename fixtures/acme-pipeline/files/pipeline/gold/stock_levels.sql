-- gold.stock_levels: stock on hand per store and product, refreshed from the ERP replica by job refresh_stock.
create or replace table gold.stock_levels as
select
  st.store_id,
  st.product_id,
  st.on_hand,
  st.reserved,
  st.on_hand - st.reserved as available,
  st.updated_at,
  current_timestamp as refreshed_at
from erp_replica.stock as st
join ref.stores as s on s.store_id = st.store_id;
