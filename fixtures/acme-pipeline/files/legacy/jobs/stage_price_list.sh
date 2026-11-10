#!/bin/sh
# Take the price list purchasing keeps on the file share and stage it as UTF-8.
set -eu
cp /mnt/purchasing/cenovnik/price_list_current.csv /tmp/price_list_cp1250.csv
iconv -f WINDOWS-1250 -t UTF-8 /tmp/price_list_cp1250.csv > /data/staging/price_list.csv
rm /tmp/price_list_cp1250.csv
