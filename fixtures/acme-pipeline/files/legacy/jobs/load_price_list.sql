-- Load the current price list into dw.price_list.
truncate table dw.price_list;

\copy dw.price_list (product_id, price_rsd, valid_from) from '/data/staging/price_list.csv' csv header
