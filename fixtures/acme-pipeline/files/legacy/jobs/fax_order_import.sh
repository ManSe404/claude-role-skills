#!/bin/sh
# Import the orders the fax-to-mail gateway saved as CSV files into dw.fax_orders.
set -eu
for file in /data/fax_inbox/*.csv; do
  [ -e "$file" ] || exit 0
  psql "$DW_DSN" -c "\copy dw.fax_orders from '$file' csv header" && mv "$file" /data/fax_inbox/done/
done
