#!/bin/sh
# Send yesterday's order lines to the logistics partner, who plans the next day's deliveries from them.
set -eu
DAY=$(date -d yesterday +%Y%m%d)
lftp -u "acme_export,${SFTP_PASSWORD}" sftp://sftp.partner.example.org <<EOF
cd /inbound/acme
put /data/extracts/orders_latest.csv -o acme_orders_${DAY}.csv
bye
EOF
