#!/bin/sh
# Weekly export of the 2025 promotions for the marketing agency.
set -eu
psql "$DW_DSN" --csv -o /data/exports/promo_2025.csv -c "select * from dw.promotions where promo_year = 2025"
