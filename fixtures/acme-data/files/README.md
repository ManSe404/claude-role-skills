# Acme Foods data warehouse

Acme Foods is a food retailer in Novi Sad with 12 stores. This repository holds the small sales warehouse behind the
store reports.

## Layout

- `models/staging/`: one model per ERP table, schema `staging`.
- `models/intermediate/`: order lines joined to their orders.
- `models/marts/`: the sales fact and the customer, product and store dimensions, schema `marts`.
- `warehouse/ddl/` and `warehouse/procs/`: T-SQL tables and procedures in schema `dw`.
- `reports/`: the store performance report for the regional managers.
- `notebooks/`: the Spark notebook that writes the stock snapshot.
- `exports/`: the contact list for the marketing mailing.
- `docs/briefs/`: briefs for what comes next.
- `data/`: sample ERP exports for trying things out, not in git.

## How it runs

The scheduler runs these every night at 02:00, in this order:

1. `dbt run`
2. `dw.merge_dim_product`
3. `dw.load_daily_sales` with yesterday's date

The stock snapshot notebook runs as its own Spark job at 06:00. `dw.export_by_region` runs on request.

## Test

    dbt test
