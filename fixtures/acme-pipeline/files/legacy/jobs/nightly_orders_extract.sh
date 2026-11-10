#!/bin/sh
# Extract yesterday's order lines from the ERP database for the old warehouse and the logistics partner.
set -eu
psql "$ERP_DSN" -c "\copy (select * from erp.order_lines where order_date = current_date - 1) to '/data/extracts/orders_latest.csv' csv header"
