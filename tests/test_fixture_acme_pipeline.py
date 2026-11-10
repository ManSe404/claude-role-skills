"""The acme-pipeline fixture: the made-up data platform of Acme Foods that the data-engineer skills are tested on.

PLANTED[skill] lists what each skill must find, as (id, short name, file, regex for the evidence line); a problem
whose evidence spans files has one entry per file. DECOYS[skill] lists what looks wrong but is fine, in the same
shape. PLANTED_AT and DECOYS_AT pin each entry, by (id, short name), to its line in the built fixture. FACTS[skill]
holds the numbers an eval grader needs: counts, EUR totals, dates. Every fact is recomputed here from the fixture's
files, so the numbers cannot drift from the data. The evals and the script tests import these; make_data.py builds
the data, history.py the commits.
"""

from __future__ import annotations

import csv
import json
import py_compile
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import build_fixture
import pytest
from conftest import ROOT, git, load

Entry = tuple[str, str, str, str]

PLANTED: dict[str, list[Entry]] = {
    "source-profile": [
        (
            "SP1",
            "activities.csv is semicolon-separated",
            "sources/crm/2026-11-04/activities.csv",
            r"^activity_id;customer_id;contact_id;activity_date;type;channel;subject;deal_value;owner$",
        ),
        (
            "SP1",
            "an offer value with a decimal comma",
            "sources/crm/2026-11-04/activities.csv",
            r"^ACT-11040005;.*;451\.226,00;",
        ),
        (
            "SP1",
            "the vendor promises commas and a decimal point",
            "sources/crm/README-vendor.md",
            r"^- Format of every file: CSV, UTF-8, comma-separated, a header line, a decimal point",
        ),
        ("SP2", "consent_date as dd.mm.yyyy", "sources/crm/2026-11-04/contacts.csv", r"^CT-50015,.*,07\.01\.2021,"),
        ("SP3", "job_title null written as N/A", "sources/crm/2026-11-04/contacts.csv", r"^CT-50041,.*,N/A,"),
        ("SP3", "job_title null written as -", "sources/crm/2026-11-04/contacts.csv", r"^CT-50030,.*,-,"),
        ("SP3", "job_title null written as NULL", "sources/crm/2026-11-04/contacts.csv", r"^CT-50040,.*,NULL,"),
        (
            "SP4",
            "CRM-10077 a second time with another city and credit limit",
            "sources/crm/2026-11-04/customers.csv",
            r"^CRM-10077,.*,Inđija,RS,226000\.00,",
        ),
        (
            "SP5",
            "a contact of an account missing from customers.csv",
            "sources/crm/2026-11-04/contacts.csv",
            r"^CT-50002,CRM-19002,",
        ),
        (
            "SP6",
            "an open account closed on 9999-12-31",
            "sources/crm/2026-11-04/customers.csv",
            r"^CRM-10001,.*,9999-12-31,,KAM-09$",
        ),
        ("SP6", "created on 1900-01-01", "sources/crm/2026-11-04/customers.csv", r"^CRM-10035,.*,1900-01-01,"),
        (
            "SP6",
            "the vendor says closed_on is empty while open",
            "sources/crm/README-vendor.md",
            r"^\| `closed_on` \| date \| when the account was closed; empty while it is open \|$",
        ),
        (
            "SP7",
            "activities of 11-03 have no channel",
            "sources/crm/2026-11-03/activities.csv",
            r"^activity_id;customer_id;contact_id;activity_date;type;subject;deal_value;owner$",
        ),
        (
            "SP7",
            "activities of 11-04 add channel",
            "sources/crm/2026-11-04/activities.csv",
            r"^activity_id;customer_id;contact_id;activity_date;type;channel;",
        ),
        (
            "SP8",
            "contacts carry e-mail, phone and IBAN",
            "sources/crm/2026-11-04/contacts.csv",
            r"^contact_id,customer_id,first_name,last_name,job_title,email,phone,iban,",
        ),
        (
            "SP8",
            "a contact with an IBAN",
            "sources/crm/2026-11-04/contacts.csv",
            r"^CT-50011,.*,RS91999181710391811518,",
        ),
        (
            "SP9",
            "the vendor documents preferred_language, which did not arrive",
            "sources/crm/README-vendor.md",
            r"^\| `preferred_language` \| code \|",
        ),
        (
            "SP9",
            "legacy_crm_ref arrives but is not documented",
            "sources/crm/2026-11-04/contacts.csv",
            r"^contact_id,.*,consent_date,legacy_crm_ref$",
        ),
    ],
    "source-contract": [
        ("SC1", "delivery due by 06:00", "contracts/erp.yaml", r'^  deliver_by: "06:00"$'),
        (
            "SC1",
            "the orders of 3 November arrived at 07:37",
            "ops/deliveries.jsonl",
            r'"file": "sources/erp/2026-11-03/orders\.csv", "arrived_at": "2026-11-03T07:37',
        ),
        ("SC2", "amount typed as integer cents", "contracts/erp.yaml", r"^    unit: cents$"),
        (
            "SC2",
            "the ERP sends amounts with two decimals",
            "sources/erp/2026-11-02/orders.csv",
            r"^SO-261101-0001,1,.*,7110\.00,RSD,",
        ),
        ("SC3", "no owner", "contracts/erp.yaml", r"^owner: TBD$"),
        ("SC3", "no change process", "contracts/erp.yaml", r"^change_process: TBD$"),
        ("SC4", "the contract lists sales_rep_code", "contracts/erp.yaml", r"^  - name: sales_rep_code$"),
        (
            "SC4",
            "the latest delivery has no sales_rep_code",
            "sources/erp/2026-11-04/orders.csv",
            r"^order_id,line_no,order_date,store_id,customer_id,product_id,quantity,weight_g,amount,currency,status$",
        ),
    ],
    "pipeline-incident": [
        (
            "PI1",
            "silver.orders failed on a decimal comma",
            "ops/runs.jsonl",
            r'"run_id": "load_erp_orders-2026-11-03-1", .*"task": "silver\.orders", .*"status": "failed"',
        ),
        ("PI1", "the naive cast", "pipeline/silver/orders.sql", r"^  cast\(amount as numeric\(12, 2\)\) as amount,$"),
        (
            "PI1",
            "the 11-03 delivery writes amounts with a comma",
            "sources/erp/2026-11-03/orders.csv",
            r'^SO-261102-0001,1,.*,"18846,00",RSD,',
        ),
        (
            "PI1",
            "the 11-02 delivery wrote them with a point",
            "sources/erp/2026-11-02/orders.csv",
            r"^SO-261101-0001,1,.*,7110\.00,RSD,",
        ),
        (
            "PI2",
            "the same failure on invoices on 2026-09-14",
            "ops/incident-log.md",
            r"^## 2026-09-14: load_erp_finance failed in silver\.invoices$",
        ),
        (
            "PI2",
            "the safe parse that orders never adopted",
            "pipeline/functions/parse_amount.sql",
            r"^create or replace function util\.parse_amount\(raw text\)",
        ),
        (
            "PI3",
            "returns casts the same way",
            "pipeline/silver/returns.sql",
            r"^  cast\(amount as numeric\(12, 2\)\) as amount,$",
        ),
        (
            "PI3",
            "payments casts the same way",
            "pipeline/silver/payments.sql",
            r"^  cast\(amount as numeric\(12, 2\)\) as amount,$",
        ),
        (
            "PI4",
            "gold.sales_daily last built on 2026-11-02",
            "ops/runs.jsonl",
            r'"run_id": "build_sales_daily-2026-11-02-1", .*"status": "success"',
        ),
        (
            "PI4",
            "gold.sales_daily skipped on 2026-11-03",
            "ops/runs.jsonl",
            r'"run_id": "build_sales_daily-2026-11-03-1", .*"status": "skipped"',
        ),
        ("PI4", "finance reads it each morning", "docs/products/sales_daily.md", r"^- Finance reads it each morning"),
    ],
    "data-quality": [
        ("DQ1", "the e-mail check", "checks/silver.yaml", r"^  - name: customers_email_format$"),
        (
            "DQ1",
            "it warns on the last day as on every day",
            "ops/checks.jsonl",
            r'"date": "2026-11-04", "check": "customers_email_format", .*"status": "warn"',
        ),
        ("DQ2", "a condition that is never true", "checks/silver.yaml", r'and amount < amount"$'),
        ("DQ2", "no bad-data case for it", "checks/tests/cases.yaml", r"^cases:$"),
        ("DQ3", "the 08:00 service level", "jobs/build_sales_daily.yaml", r'^sla: "08:00"$'),
        (
            "DQ3",
            "freshness failed on 11-03",
            "ops/checks.jsonl",
            r'"date": "2026-11-03", "check": "sales_daily_fresh", .*"status": "fail"',
        ),
        (
            "DQ4",
            "the first S-031 row in quarantine",
            "ops/quarantine.jsonl",
            r'"row_id": "SO-261027-0274/1", "value": "S-031"',
        ),
        ("DQ4", "the reference table ends at S-030", "ref/stores.csv", r"^S-030,"),
        (
            "DQ5",
            "gold.sales_daily: do not use",
            "ops/checks.jsonl",
            r'"date": "2026-11-04", "check": "sales_daily_fresh", .*"status": "fail"',
        ),
        (
            "DQ5",
            "silver.customers: use with care",
            "ops/checks.jsonl",
            r'"date": "2026-11-04", "check": "customers_email_format", .*"status": "warn"',
        ),
        (
            "DQ5",
            "gold.stock_levels: safe",
            "ops/checks.jsonl",
            r'"date": "2026-11-04", "check": "stock_levels_non_negative", .*"status": "pass"',
        ),
    ],
    "data-cost": [
        (
            "DC1",
            "the largest table",
            "ops/storage.csv",
            r"^bronze\.erp_orders_history_full,bronze,812\.00,32\.48$",
        ),
        (
            "DC1",
            "a one-off copy to drop after sign-off",
            "pipeline/bronze/erp_orders_history_full.sql",
            r"^-- Drop it once finance has signed the reconciliation off\.$",
        ),
        ("DC2", "a full reload every morning", "pipeline/silver/customers.sql", r"^truncate table silver\.customers;$"),
        ("DC2", "the job loads in full", "jobs/rebuild_customers.yaml", r"^load: full$"),
        (
            "DC2",
            "7 rows changed of 24,228 on 11-04",
            "ops/runs.jsonl",
            r'"run_id": "rebuild_customers-2026-11-04-1", .*"rows_written": 24228, "rows_changed": 7,',
        ),
        ("DC3", "every 5 minutes", "jobs/refresh_stock.yaml", r'^schedule: "\*/5 \* \* \* \*"$'),
        ("DC3", "read twice a day", "ops/query_log.csv", r"^2026-11-04,stock_planner,gold\.stock_levels,2$"),
        (
            "DC4",
            "dev-adhoc billed 24 hours on a Sunday",
            "ops/usage.csv",
            r"^2026-11-01,cluster,dev-adhoc,dev-adhoc,24\.00,28\.80$",
        ),
    ],
    "data-migration": [
        ("DM1", "store_kpi_v1 last ran 2026-04-02", "legacy/inventory.csv", r"^store_kpi_v1,.*,2026-04-02 "),
        ("DM1", "promo_export_2025 last ran 2026-03-30", "legacy/inventory.csv", r"^promo_export_2025,.*,2026-03-30 "),
        (
            "DM1",
            "old_loyalty_points last ran 2026-02-28",
            "legacy/inventory.csv",
            r"^old_loyalty_points,.*,2026-02-28 ",
        ),
        (
            "DM1",
            "cleanup_tmp_tables last ran 2026-01-11",
            "legacy/inventory.csv",
            r"^cleanup_tmp_tables,.*,2026-01-11 ",
        ),
        ("DM1", "fax_order_import last ran 2025-12-19", "legacy/inventory.csv", r"^fax_order_import,.*,2025-12-19 "),
        (
            "DM1",
            "supplier_scorecard last ran 2025-11-24",
            "legacy/inventory.csv",
            r"^supplier_scorecard,.*,2025-11-24 ",
        ),
        (
            "DM2",
            "export_store_sales",
            "legacy/jobs/export_store_sales.sql",
            r"^select o\.order_date, o\.store_id, s\.store_name, sum\(o\.amount\) as revenue$",
        ),
        (
            "DM2",
            "export_sales_by_store, the same SQL",
            "legacy/jobs/export_sales_by_store.sql",
            r"^select o\.order_date, o\.store_id, s\.store_name, sum\(o\.amount\) as revenue$",
        ),
        (
            "DM3",
            "stage_price_list writes the file",
            "legacy/jobs/stage_price_list.sh",
            r"> /data/staging/price_list\.csv$",
        ),
        ("DM3", "load_price_list reads it", "legacy/jobs/load_price_list.sql", r"from '/data/staging/price_list\.csv'"),
        ("DM3", "and does not depend on its writer", "legacy/inventory.csv", r"^load_price_list,.*,dw\.price_list,$"),
        (
            "DM4",
            "the partner's SFTP server",
            "legacy/jobs/send_partner_orders.sh",
            r'^lftp -u "acme_export,\$\{SFTP_PASSWORD\}" sftp://sftp\.partner\.example\.org',
        ),
        (
            "DM4",
            "the job in the inventory",
            "legacy/inventory.csv",
            r"^send_partner_orders,.*,sftp://sftp\.partner\.example\.org/",
        ),
        (
            "DM5",
            "load_stock_snapshot at 03:00",
            "legacy/inventory.csv",
            r"^load_stock_snapshot,jobs/load_stock_snapshot\.sql,0 3 \* \* \*,.*,dw\.stock_snapshot,$",
        ),
        (
            "DM5",
            "fix_stock_snapshot at the same minute",
            "legacy/inventory.csv",
            r"^fix_stock_snapshot,jobs/fix_stock_snapshot\.sql,0 3 \* \* \*,.*,dw\.stock_snapshot,$",
        ),
    ],
    "data-product": [
        (
            "DPR1",
            "net revenue without returns in the product document",
            "docs/products/sales_daily.md",
            r"^\| `net_revenue` \| gross revenue minus the cancelled lines; returns are not deducted",
        ),
        (
            "DPR1",
            "net revenue with returns in the BI metrics",
            "reports/bi/metrics.md",
            r"^\| Net revenue \| gross revenue minus cancellations minus returns \|",
        ),
        (
            "DPR2",
            "the served table carries an e-mail",
            "pipeline/gold/sales_daily.sql",
            r"^  c\.email as customer_email,$",
        ),
        (
            "DPR2",
            "the sample has the column",
            "samples/gold/sales_daily.csv",
            r"^sales_date,store_id,.*,customer_email,built_at$",
        ),
        ("DPR3", "no owner named", "docs/products/sales_daily.md", r"^Questions: the data platform team\.$"),
        ("DPR3", "no freshness promise", "docs/products/sales_daily.md", r"^Refreshed: daily, after the ERP load\.$"),
        ("DPR3", "the job has an SLA the document leaves out", "jobs/build_sales_daily.yaml", r'^sla: "08:00"$'),
        ("DPR4", "the documented grain", "docs/products/sales_daily.md", r"^Grain: one row per store and day\.$"),
        (
            "DPR4",
            "the key check uses the currency",
            "checks/gold.yaml",
            r"group by sales_date, store_id, currency having count\(\*\) > 1",
        ),
        ("DPR4", "a second row for S-030 on 10-04", "samples/gold/sales_daily.csv", r"^2026-10-04,S-030,.*,HUF,"),
    ],
    "runbook": [
        ("RB1", "the runbook names load_crm", "docs/runbook.md", r"^\| `load_crm` \|"),
        ("RB1", "the job is ingest_crm", "jobs/ingest_crm.yaml", r"^name: ingest_crm$"),
        ("RB2", "the runbook says make backfill", "docs/runbook.md", r"`make backfill DATE=2026-10-01`"),
        ("RB2", "the target is backfill-day", "Makefile", r"^backfill-day:"),
        ("RB3", "the runbook documents ACME_WAREHOUSE_URL", "docs/runbook.md", r"^- `ACME_WAREHOUSE_URL`:"),
        (
            "RB3",
            "the code reads WAREHOUSE_DSN",
            "pipeline/config/settings.py",
            r'^WAREHOUSE_DSN = os\.environ\["WAREHOUSE_DSN"\]$',
        ),
        ("RB4", "the how-to goes from loader to job", "docs/howto/add-a-source.md", r"^4\. Write the loader"),
        (
            "RB4",
            "the loader refuses a source without a contract",
            "pipeline/loaders/common.py",
            r'raise SystemExit\(f"source \{source\} has no contract registered',
        ),
        (
            "RB4",
            "where the contract is registered",
            "pipeline/config/sources.yaml",
            r"^    contract: contracts/erp\.yaml$",
        ),
        ("RB5", "the runbook says 05:00", "docs/runbook.md", r"^\| `load_erp_orders` \| daily at 05:00 \|"),
        ("RB5", "the cron says 06:30", "jobs/load_erp_orders.yaml", r'^schedule: "30 6 \* \* \*"$'),
    ],
}

DECOYS: dict[str, list[Entry]] = {
    "source-profile": [
        (
            "SP-D1",
            "parent_customer_id is empty and documented as optional",
            "sources/crm/README-vendor.md",
            r"^\| `parent_customer_id` \| text \| optional:",
        ),
        (
            "SP-D2",
            "status X is documented",
            "sources/crm/README-vendor.md",
            r"^\| `status` \| code \| A active, I inactive, X closed by credit control",
        ),
        ("SP-D2", "an account with status X", "sources/crm/2026-11-04/customers.csv", r"^CRM-10029,.*,X,"),
    ],
    "source-contract": [
        ("SC-D1", "on_hold is allowed", "contracts/erp.yaml", r"^    allowed: \[delivered, cancelled, on_hold\]$"),
        (
            "SC-D1",
            "an on_hold line in the latest delivery",
            "sources/erp/2026-11-04/orders.csv",
            r"^SO-261103-0074,3,.*,on_hold$",
        ),
    ],
    "pipeline-incident": [
        (
            "PI-D1",
            "the late-file warning of the same run",
            "ops/runs.jsonl",
            r'"run_id": "load_erp_orders-2026-11-03-1", .*"task": "wait_for_file", .*"status": "warning"',
        ),
        (
            "PI-D2",
            "invoices already parses safely",
            "pipeline/silver/invoices.sql",
            r"^  util\.parse_amount\(amount\) as amount,$",
        ),
    ],
    "data-quality": [
        (
            "DQ-D1",
            "the store check failed after the Hungarian holiday",
            "ops/checks.jsonl",
            r'"date": "2026-10-24", "check": "orders_every_store_ordered", .*"status": "fail"',
        ),
        (
            "DQ-D1",
            "and passed the next day",
            "ops/checks.jsonl",
            r'"date": "2026-10-25", "check": "orders_every_store_ordered", .*"status": "pass"',
        ),
    ],
    "data-cost": [
        ("DC-D1", "the most expensive job", "ops/usage.csv", r"^2026-11-02,job,build_sales_daily,etl,3\.14,6\.28$"),
        (
            "DC-D1",
            "its table is read every hour",
            "ops/query_log.csv",
            r"^2026-11-04,bi_sales_board,gold\.sales_daily,24$",
        ),
    ],
    "data-migration": [
        (
            "DM-D1",
            "a monthly job that last ran on 15 October",
            "legacy/inventory.csv",
            r"^month_end_margin,jobs/month_end_margin\.sql,30 2 15 \* \*,d\.vujic,2026-10-15 02:30,",
        ),
    ],
    "data-product": [
        ("DPR-D1", "kg_eq is documented", "docs/products/sales_daily.md", r"^\| `kg_eq` \| kilogram equivalent"),
    ],
    "runbook": [
        ("RB-D1", "make dq looks wrong", "docs/runbook.md", r"`make dq LAYER=silver`"),
        ("RB-D1", "dq is an alias of checks", "Makefile", r"^dq: checks"),
    ],
}

PLANTED_AT: dict[tuple[str, str], int] = {
    ("SP1", "activities.csv is semicolon-separated"): 1,
    ("SP1", "an offer value with a decimal comma"): 6,
    ("SP1", "the vendor promises commas and a decimal point"): 10,
    ("SP2", "consent_date as dd.mm.yyyy"): 16,
    ("SP3", "job_title null written as N/A"): 42,
    ("SP3", "job_title null written as -"): 31,
    ("SP3", "job_title null written as NULL"): 41,
    ("SP4", "CRM-10077 a second time with another city and credit limit"): 105,
    ("SP5", "a contact of an account missing from customers.csv"): 3,
    ("SP6", "an open account closed on 9999-12-31"): 2,
    ("SP6", "created on 1900-01-01"): 36,
    ("SP6", "the vendor says closed_on is empty while open"): 25,
    ("SP7", "activities of 11-03 have no channel"): 1,
    ("SP7", "activities of 11-04 add channel"): 1,
    ("SP8", "contacts carry e-mail, phone and IBAN"): 1,
    ("SP8", "a contact with an IBAN"): 12,
    ("SP9", "the vendor documents preferred_language, which did not arrive"): 42,
    ("SP9", "legacy_crm_ref arrives but is not documented"): 1,
    ("SC1", "delivery due by 06:00"): 17,
    ("SC1", "the orders of 3 November arrived at 07:37"): 120,
    ("SC2", "amount typed as integer cents"): 48,
    ("SC2", "the ERP sends amounts with two decimals"): 2,
    ("SC3", "no owner"): 7,
    ("SC3", "no change process"): 8,
    ("SC4", "the contract lists sales_rep_code"): 56,
    ("SC4", "the latest delivery has no sales_rep_code"): 1,
    ("PI1", "silver.orders failed on a decimal comma"): 324,
    ("PI1", "the naive cast"): 18,
    ("PI1", "the 11-03 delivery writes amounts with a comma"): 2,
    ("PI1", "the 11-02 delivery wrote them with a point"): 2,
    ("PI2", "the same failure on invoices on 2026-09-14"): 5,
    ("PI2", "the safe parse that orders never adopted"): 5,
    ("PI3", "returns casts the same way"): 10,
    ("PI3", "payments casts the same way"): 9,
    ("PI4", "gold.sales_daily last built on 2026-11-02"): 313,
    ("PI4", "gold.sales_daily skipped on 2026-11-03"): 322,
    ("PI4", "finance reads it each morning"): 12,
    ("DQ1", "the e-mail check"): 15,
    ("DQ1", "it warns on the last day as on every day"): 323,
    ("DQ2", "a condition that is never true"): 7,
    ("DQ2", "no bad-data case for it"): 3,
    ("DQ3", "the 08:00 service level"): 8,
    ("DQ3", "freshness failed on 11-03"): 319,
    ("DQ4", "the first S-031 row in quarantine"): 175,
    ("DQ4", "the reference table ends at S-030"): 31,
    ("DQ5", "gold.sales_daily: do not use"): 327,
    ("DQ5", "silver.customers: use with care"): 323,
    ("DQ5", "gold.stock_levels: safe"): 330,
    ("DC1", "the largest table"): 2,
    ("DC1", "a one-off copy to drop after sign-off"): 3,
    ("DC2", "a full reload every morning"): 2,
    ("DC2", "the job loads in full"): 6,
    ("DC2", "7 rows changed of 24,228 on 11-04"): 334,
    ("DC3", "every 5 minutes"): 3,
    ("DC3", "read twice a day"): 293,
    ("DC4", "dev-adhoc billed 24 hours on a Sunday"): 169,
    ("DM1", "store_kpi_v1 last ran 2026-04-02"): 14,
    ("DM1", "promo_export_2025 last ran 2026-03-30"): 15,
    ("DM1", "old_loyalty_points last ran 2026-02-28"): 10,
    ("DM1", "cleanup_tmp_tables last ran 2026-01-11"): 18,
    ("DM1", "fax_order_import last ran 2025-12-19"): 17,
    ("DM1", "supplier_scorecard last ran 2025-11-24"): 16,
    ("DM2", "export_store_sales"): 2,
    ("DM2", "export_sales_by_store, the same SQL"): 2,
    ("DM3", "stage_price_list writes the file"): 5,
    ("DM3", "load_price_list reads it"): 4,
    ("DM3", "and does not depend on its writer"): 6,
    ("DM4", "the partner's SFTP server"): 5,
    ("DM4", "the job in the inventory"): 13,
    ("DM5", "load_stock_snapshot at 03:00"): 8,
    ("DM5", "fix_stock_snapshot at the same minute"): 9,
    ("DPR1", "net revenue without returns in the product document"): 28,
    ("DPR1", "net revenue with returns in the BI metrics"): 8,
    ("DPR2", "the served table carries an e-mail"): 16,
    ("DPR2", "the sample has the column"): 1,
    ("DPR3", "no owner named"): 8,
    ("DPR3", "no freshness promise"): 7,
    ("DPR3", "the job has an SLA the document leaves out"): 8,
    ("DPR4", "the documented grain"): 5,
    ("DPR4", "the key check uses the currency"): 11,
    ("DPR4", "a second row for S-030 on 10-04"): 32,
    ("RB1", "the runbook names load_crm"): 15,
    ("RB1", "the job is ingest_crm"): 1,
    ("RB2", "the runbook says make backfill"): 31,
    ("RB2", "the target is backfill-day"): 14,
    ("RB3", "the runbook documents ACME_WAREHOUSE_URL"): 21,
    ("RB3", "the code reads WAREHOUSE_DSN"): 5,
    ("RB4", "the how-to goes from loader to job"): 9,
    ("RB4", "the loader refuses a source without a contract"): 35,
    ("RB4", "where the contract is registered"): 4,
    ("RB5", "the runbook says 05:00"): 11,
    ("RB5", "the cron says 06:30"): 3,
}
DECOYS_AT: dict[tuple[str, str], int] = {
    ("SP-D1", "parent_customer_id is empty and documented as optional"): 26,
    ("SP-D2", "status X is documented"): 20,
    ("SP-D2", "an account with status X"): 30,
    ("SC-D1", "on_hold is allowed"): 55,
    ("SC-D1", "an on_hold line in the latest delivery"): 223,
    ("PI-D1", "the late-file warning of the same run"): 321,
    ("PI-D2", "invoices already parses safely"): 11,
    ("DQ-D1", "the store check failed after the Hungarian holiday"): 212,
    ("DQ-D1", "and passed the next day"): 223,
    ("DC-D1", "the most expensive job"): 170,
    ("DC-D1", "its table is read every hour"): 286,
    ("DM-D1", "a monthly job that last ran on 15 October"): 7,
    ("DPR-D1", "kg_eq is documented"): 29,
    ("RB-D1", "make dq looks wrong"): 32,
    ("RB-D1", "dq is an alias of checks"): 20,
}

FACTS: dict[str, dict[str, Any]] = {
    "source-profile": {
        "delivery": "sources/crm/2026-11-04",
        "previous": "sources/crm/2026-11-03",
        "vendor_document": "sources/crm/README-vendor.md",
        "rows": {"customers.csv": 614, "contacts.csv": 911, "activities.csv": 268},
        "rows_previous": {"customers.csv": 612, "contacts.csv": 905, "activities.csv": 243},
        "delimiters": {"customers.csv": ",", "contacts.csv": ",", "activities.csv": ";"},
        "decimal_comma_values": 63,  # activities.deal_value: every offer, as 451.226,00
        "decimal_point_values": 614,  # customers.credit_limit, as 254000.00
        "consent_date_formats": {"YYYY-MM-DD": 853, "DD.MM.YYYY": 58},
        "null_tokens": {"column": "contacts.job_title", "tokens": {"": 41, "N/A": 17, "NULL": 9, "-": 12}},
        "customer_ids": {
            "rows": 614,
            "distinct": 609,
            "duplicated": ["CRM-10077", "CRM-10129", "CRM-10266", "CRM-10402", "CRM-10588"],
        },
        "orphan_contacts": 14,
        "placeholder_dates": {"customers.closed_on 9999-12-31": 568, "customers.created_on 1900-01-01": 24},
        "added_column": {"file": "activities.csv", "column": "channel"},
        "personal_data": {"contacts.email": 911, "contacts.phone": 911, "contacts.iban": 126},
        "documented_not_delivered": ["contacts.preferred_language"],
        "delivered_not_documented": ["contacts.legacy_crm_ref"],
        "empty_optional_column": {"column": "customers.parent_customer_id", "empty_rows": 614},
        "status_x_rows": 7,
    },
    "source-contract": {
        "contract": "contracts/erp.yaml",
        "deliver_by": "06:00",
        "erp_delivery_days": 31,
        "late_days": 23,
        "late_arrivals_between": ("07:06", "07:37"),
        "on_time_days": 8,  # the Saturdays and Sundays
        "amount_in_contract": "integer cents",
        "amount_format": {"2026-11-02": "1234.50", "2026-11-03": "1234,50", "2026-11-04": "1234,50"},
        "missing_column": "sales_rep_code",
        "missing_from": "sources/erp/2026-11-04/orders.csv",
        "owner": "TBD",
        "change_process": "TBD",
        "on_hold_rows": 3,
        "crm_contract": None,
    },
    "pipeline-incident": {
        "job": "load_erp_orders",
        "run_id": "load_erp_orders-2026-11-03-1",
        "failed_task": "silver.orders",
        "layer": "silver",
        "error_value": "18846,00",
        "cast_at": "pipeline/silver/orders.sql:18",
        "failed_runs": ["load_erp_orders-2026-11-03-1", "load_erp_orders-2026-11-03-2", "load_erp_orders-2026-11-04-1"],
        "last_good_delivery": "2026-11-02",
        "first_bad_delivery": "2026-11-03",
        "rows_in_bad_delivery": 1038,
        "past_incident": "2026-09-14",
        "safe_parse": "util.parse_amount",
        "same_weakness": ["pipeline/silver/payments.sql", "pipeline/silver/returns.sql"],
        "already_safe": "pipeline/silver/invoices.sql",
        "gold_last_built": "2026-11-02T07:35:14+01:00",
        "gold_skipped": ["2026-11-03", "2026-11-04"],
        "late_file": {"arrived": "07:37", "minutes_after_start": 67},
    },
    "data-quality": {
        "period": ("2026-10-05", "2026-11-04"),
        "results": 330,
        "always_warns": {"check": "customers_email_format", "days": 31, "failing_rows": (37, 41)},
        "cannot_fail": {"check": "orders_amount_positive", "results": 29, "failures": 0},
        "never_failed": [
            "customers_id_unique",
            "erp_orders_key_unique",
            "erp_orders_not_empty",
            "invoices_amount_parsed",
            "orders_amount_positive",
            "sales_daily_key_unique",
            "stock_levels_fresh",
            "stock_levels_non_negative",
        ],
        "without_a_test_case": ["orders_amount_positive"],
        "freshness": {"table": "gold.sales_daily", "sla": "08:00", "failed_on": ["2026-11-03", "2026-11-04"]},
        "quarantine": {
            "rule": "unknown_store_id",
            "days_before": 23,
            "rows_before": 117,
            "max_a_day_before": 7,
            "from": "2026-10-28",
            "days_from": 6,
            "rows_from": 693,
            "min_a_day_from": 107,
            "store": "S-031",
        },
        "verdicts": {
            "gold.sales_daily": "do not use",
            "silver.customers": "use with care",
            "gold.stock_levels": "safe",
        },
        "holiday": {
            "check": "orders_every_store_ordered",
            "failed_on": "2026-10-24",
            "orders_of": "2026-10-23",
            "failing_rows": 4,
            "passed_on": "2026-10-25",
        },
    },
    "data-cost": {
        "period_days": 31,
        "compute_eur": {
            "dev-adhoc": Decimal("892.80"),
            "build_sales_daily": Decimal("182.36"),
            "refresh_stock": Decimal("133.92"),
            "rebuild_customers": Decimal("46.14"),
            "load_erp_orders": Decimal("21.50"),
            "load_erp_finance": Decimal("13.00"),
        },
        "compute_total": Decimal("1289.72"),
        "storage_gb": Decimal("925.50"),
        "storage_total": Decimal("37.02"),
        "total": Decimal("1326.74"),
        "unread_table": {
            "table": "bronze.erp_orders_history_full",
            "gb": Decimal("812.00"),
            "eur_per_month": Decimal("32.48"),
            "queries": 0,
        },
        "full_reload": {
            "job": "rebuild_customers",
            "eur": Decimal("46.14"),
            "rows_written": 750_333,
            "rows_changed": 347,
            "max_changed_a_day": 17,
        },
        "too_frequent": {
            "job": "refresh_stock",
            "runs_a_day": 288,
            "runs": 8_928,
            "eur": Decimal("133.92"),
            "table": "gold.stock_levels",
            "queries": 54,
        },
        "never_stops": {
            "cluster": "dev-adhoc",
            "hours": Decimal("744.00"),
            "eur": Decimal("892.80"),
            "weekend_days": 8,
            "weekend_eur": Decimal("230.40"),
            "jobs": 0,
        },
        "decoy": {
            "job": "build_sales_daily",
            "eur": Decimal("182.36"),
            "table": "gold.sales_daily",
            "queries": 3_007,
            "consumers": 5,
            "hourly_consumers": 4,
        },
    },
    "data-migration": {
        "inventory": "legacy/inventory.csv",
        "as_of": "2026-11-04",
        "jobs": 17,
        "dead_after_days": 180,
        "dead": [
            "cleanup_tmp_tables",
            "fax_order_import",
            "old_loyalty_points",
            "promo_export_2025",
            "store_kpi_v1",
            "supplier_scorecard",
        ],
        "identical_sql": ["export_sales_by_store", "export_store_sales"],
        "undeclared_file_dependency": {
            "writer": "stage_price_list",
            "reader": "load_price_list",
            "path": "/data/staging/price_list.csv",
        },
        "outside_consumer": {
            "job": "send_partner_orders",
            "host": "sftp.partner.example.org",
            "secret": "${SFTP_PASSWORD}",
        },
        "same_minute_same_table": {
            "jobs": ["fix_stock_snapshot", "load_stock_snapshot"],
            "schedule": "0 3 * * *",
            "table": "dw.stock_snapshot",
        },
        "monthly_on_schedule": {
            "job": "month_end_margin",
            "schedule": "30 2 15 * *",
            "last_run": "2026-10-15",
            "next_run": "2026-11-15",
        },
    },
    "data-product": {
        "table": "gold.sales_daily",
        "document": "docs/products/sales_daily.md",
        "documented_grain": ["store_id", "sales_date"],
        "real_grain": ["sales_date", "store_id", "currency"],
        "sample": "samples/gold/sales_daily.csv",
        "sample_rows": 904,
        "store_days": 862,
        "store_days_with_two_rows": 42,
        "rows_by_currency": {"RSD": 754, "EUR": 108, "HUF": 42},
        "personal_column": "customer_email",
        "net_revenue": {
            "docs/products/sales_daily.md": "without returns",
            "reports/bi/metrics.md": "with returns",
            "pipeline/gold/sales_daily.sql": "without returns",
        },
        "owner": None,
        "sla_in_document": None,
        "sla_in_job": "08:00",
        "consumers": [
            "bi_sales_board",
            "finance_cash_plan",
            "franchise_portal",
            "regional_managers_report",
            "store_ops_app",
        ],
        "queries": 3_007,
    },
    "runbook": {
        "documents": [
            "docs/howto/add-a-source.md",
            "docs/howto/backfill.md",
            "docs/howto/rerun-a-failed-job.md",
            "docs/runbook.md",
        ],
        "renamed_job": ("load_crm", "ingest_crm"),
        "renamed_target": ("backfill", "backfill-day"),
        "renamed_setting": ("ACME_WAREHOUSE_URL", "WAREHOUSE_DSN"),
        "missing_step": "write contracts/<source>.yaml and register it in pipeline/config/sources.yaml",
        "schedule": {"job": "load_erp_orders", "runbook": "05:00", "cron": "30 6 * * *", "time": "06:30"},
        "alias": ("dq", "checks"),
        "jobs": [
            "build_sales_daily",
            "ingest_crm",
            "load_erp_finance",
            "load_erp_orders",
            "rebuild_customers",
            "refresh_stock",
        ],
        "make_targets": ["backfill-day", "checks", "dq", "run", "samples", "status"],
        "settings_read": ["ACME_ALERT_EMAIL", "ACME_OPS_DIR", "ACME_SOURCES_DIR", "WAREHOUSE_DSN"],
    },
}

HEAD = "703a806"
COMMITS = 12
FIXTURE = ROOT / "fixtures" / "acme-pipeline"
FILES = FIXTURE / "files"
EXTRAS = FIXTURE / "extras"
MAKE_DATA = FIXTURE / "make_data.py"
AS_OF = date(2026, 11, 4)
PERIOD = [date(2026, 10, 5) + timedelta(days=n) for n in range(31)]


@pytest.fixture(scope="module")
def repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The acme-pipeline fixture, built once for this module. Tests must not change it."""
    target = tmp_path_factory.mktemp("fixture") / "acme-pipeline"
    build_fixture.build("acme-pipeline", target)
    return target


def read_csv(path: Path, delimiter: str = ",") -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=delimiter))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def header(path: Path) -> list[str]:
    first = path.read_text(encoding="utf-8").split("\n", 1)[0]
    return first.split(max(",;", key=first.count))


def tracked(repo: Path) -> list[str]:
    return git(repo, "ls-files").splitlines()


def line_of(repo: Path, rel: str, pattern: str) -> int:
    """The 1-based line of repo/rel that pattern matches; it must match exactly one line."""
    lines = (repo / rel).read_text(encoding="utf-8").splitlines()
    hits = [n for n, line in enumerate(lines, start=1) if re.search(pattern, line)]
    assert len(hits) == 1, f"{pattern!r} matches lines {hits} of {rel}, expected exactly one"
    return hits[0]


def crm(repo: Path, day: str, name: str) -> list[dict[str, str]]:
    return read_csv(repo / "sources" / "crm" / day / name, ";" if name == "activities.csv" else ",")


NUMBER = re.compile(r"[+-]?\d+(\.\d+)?")


def naive_cast(raw: str) -> Decimal:
    """cast(amount as numeric(12, 2)) as the warehouse runs it: a plain number with a decimal point, nothing else."""
    if not NUMBER.fullmatch(raw.strip()):
        raise InvalidOperation(f'invalid input syntax for type numeric: "{raw}"')
    return Decimal(raw.strip())


def parse_amount(raw: str) -> Decimal | None:
    """util.parse_amount of pipeline/functions/parse_amount.sql."""
    text = raw.strip()
    if not text:
        return None
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    return naive_cast(text)


def documented_columns(repo: Path) -> dict[str, list[str]]:
    """The columns the CRM vendor's document lists, per file."""
    columns: dict[str, list[str]] = {}
    current = ""
    for line in (repo / "sources/crm/README-vendor.md").read_text(encoding="utf-8").splitlines():
        if line.startswith("## ") and line.endswith(".csv"):
            current = line[3:]
            columns[current] = []
        match = re.match(r"^\| `(\w+)` \|", line)
        if current and match:
            columns[current].append(match.group(1))
    return columns


def contract_columns(text: str) -> dict[str, dict[str, str]]:
    """The `columns:` list of a contract as {name: {key: value}}."""
    columns: dict[str, dict[str, str]] = {}
    current = ""
    inside = False
    for line in text.splitlines():
        if not line.startswith(" "):
            inside = line == "columns:"
            continue
        if inside and line.startswith("  - name: "):
            current = line.removeprefix("  - name: ")
            columns[current] = {}
        elif inside and current:
            key, _, value = line.strip().partition(": ")
            columns[current][key] = value
    return columns


def search(pattern: str, text: str) -> re.Match[str]:
    match = re.search(pattern, text, re.MULTILINE)
    assert match, pattern
    return match


EXTRA_FILES = sorted(p.relative_to(EXTRAS).as_posix() for p in EXTRAS.rglob("*") if p.is_file())
ENTRIES = [(skill, "planted", *entry) for skill, entries in PLANTED.items() for entry in entries] + [
    (skill, "decoy", *entry) for skill, entries in DECOYS.items() for entry in entries
]


def test_builds_deterministically_with_the_same_head(tmp_path: Path) -> None:
    heads = {build_fixture.build("acme-pipeline", tmp_path / name) for name in ("one", "two")}
    assert heads == {HEAD}


def test_history_has_three_authors_and_tells_the_story(repo: Path) -> None:
    log = [line.split("|") for line in git(repo, "log", "--format=%h|%ad|%ae|%s", "--date=short").splitlines()]
    assert len(log) == COMMITS
    assert log[0][:3] == [HEAD, "2026-11-04", "dragana.vujic@example.com"]
    assert log[0][3].startswith("Migration: inventory and scripts of the old cron estate")
    assert log[-1][1] == "2026-06-08" and log[-1][3].startswith("Start the platform")
    assert {entry[2] for entry in log} == {
        "bogdan.stanar@example.com",
        "dragana.vujic@example.com",
        "tijana.krsmanovic@example.com",
    }
    assert all("2026-06-01" <= entry[1] <= "2026-11-04" for entry in log)
    # The runbook was right when it was written; the code moved on after it.
    written = git(repo, "log", "--format=%h", "--diff-filter=A", "--", "docs/runbook.md").strip()
    assert "\nbackfill:" in git(repo, "show", f"{written}:Makefile")
    assert 'os.environ["ACME_WAREHOUSE_URL"]' in git(repo, "show", f"{written}:pipeline/config/settings.py")
    assert 'schedule: "0 5 * * *"' in git(repo, "show", f"{written}:jobs/load_erp_orders.yaml")
    assert "contract" not in git(repo, "show", f"{written}:pipeline/loaders/common.py")
    # Invoices cast naively until the incident of 2026-09-14; the fix came the next day, for invoices only.
    fix, day = git(repo, "log", "--format=%h %ad", "--date=short", "--", "pipeline/functions/parse_amount.sql").split()
    assert day == "2026-09-15"
    assert "cast(amount as numeric(12, 2))" in git(repo, "show", f"{fix}~1:pipeline/silver/invoices.sql")
    # The CRM job was born as ingest_crm: no jobs/load_crm.yaml ever existed.
    assert git(repo, "log", "--format=%h", "--", "jobs/load_crm.yaml") == ""


def test_layout_and_the_last_commit_equal_the_stored_files(repo: Path) -> None:
    stored = build_fixture.final_files("acme-pipeline")
    assert sorted(tracked(repo)) == sorted(stored)
    for rel, content in stored.items():
        assert git(repo, "show", f"HEAD:{rel}") == content, rel


def test_extras_are_on_disk_but_not_committed(repo: Path) -> None:
    assert len(EXTRA_FILES) == 26
    files = set(tracked(repo))
    for rel in EXTRA_FILES:
        assert (repo / rel).read_bytes() == (EXTRAS / rel).read_bytes(), rel
        assert rel not in files, rel
    assert git(repo, "status", "--porcelain", "--untracked-files=all") == ""
    assert "sources/crm/README-vendor.md" in files
    assert not [rel for rel in files if re.match(r"sources/\w+/20", rel) or rel.startswith("samples/")]


def test_the_generator_reproduces_the_data(tmp_path: Path) -> None:
    extras, ref = tmp_path / "extras", tmp_path / "ref"
    command = [sys.executable, str(MAKE_DATA), "--extras", str(extras), "--ref", str(ref)]
    subprocess.run(command, check=True, capture_output=True, timeout=120)
    assert sorted(p.relative_to(extras).as_posix() for p in extras.rglob("*") if p.is_file()) == EXTRA_FILES
    for rel in EXTRA_FILES:
        assert (extras / rel).read_bytes() == (EXTRAS / rel).read_bytes(), rel
    assert (ref / "stores.csv").read_bytes() == (FILES / "ref" / "stores.csv").read_bytes()


def test_the_fixture_is_small() -> None:
    total = sum(p.stat().st_size for p in [*FILES.rglob("*"), *EXTRAS.rglob("*")] if p.is_file())
    assert total < 3_000_000
    for rel in EXTRA_FILES:
        assert len((EXTRAS / rel).read_text(encoding="utf-8").splitlines()) <= 2_000, rel


@pytest.mark.parametrize(
    ("skill", "kind", "key", "name", "rel", "pattern"), ENTRIES, ids=[e[2] + " " + e[3] for e in ENTRIES]
)
def test_each_entry_matches_one_line_at_its_pin(
    repo: Path, skill: str, kind: str, key: str, name: str, rel: str, pattern: str
) -> None:
    pins = PLANTED_AT if kind == "planted" else DECOYS_AT
    assert line_of(repo, rel, pattern) == pins[(key, name)], f"{skill}: {key} {name}"


def test_the_answer_key_is_complete() -> None:
    skills = [
        "source-profile",
        "source-contract",
        "pipeline-incident",
        "data-quality",
        "data-cost",
        "data-migration",
        "data-product",
        "runbook",
    ]
    assert list(PLANTED) == list(DECOYS) == list(FACTS) == skills
    prefixes = {"source-profile": ("SP", 9), "source-contract": ("SC", 4), "pipeline-incident": ("PI", 4)}
    prefixes |= {"data-quality": ("DQ", 5), "data-cost": ("DC", 4), "data-migration": ("DM", 5)}
    prefixes |= {"data-product": ("DPR", 4), "runbook": ("RB", 5)}
    for skill, (prefix, count) in prefixes.items():
        assert list(dict.fromkeys(e[0] for e in PLANTED[skill])) == [f"{prefix}{n}" for n in range(1, count + 1)]
        assert DECOYS[skill] and all(e[0].startswith(f"{prefix}-D") for e in DECOYS[skill]), skill
    keys = [(e[0], e[1]) for table in (PLANTED, DECOYS) for entries in table.values() for e in entries]
    assert len(keys) == len(set(keys))
    assert set(PLANTED_AT) == {(e[0], e[1]) for entries in PLANTED.values() for e in entries}
    assert set(DECOYS_AT) == {(e[0], e[1]) for entries in DECOYS.values() for e in entries}


def test_source_profile_facts(repo: Path) -> None:
    facts = FACTS["source-profile"]
    data_profile = load(ROOT / "shared" / "data_profile.py")
    new, old = facts["delivery"].rsplit("/", 1)[1], facts["previous"].rsplit("/", 1)[1]
    for name, rows in facts["rows"].items():
        assert len(crm(repo, new, name)) == rows, name
        assert len(crm(repo, old, name)) == facts["rows_previous"][name], name
        first = (repo / facts["delivery"] / name).read_text(encoding="utf-8").split("\n", 1)[0]
        assert max(",;", key=first.count) == facts["delimiters"][name], name
    customers, contacts, activities = (crm(repo, new, n) for n in ("customers.csv", "contacts.csv", "activities.csv"))

    comma = [r for r in activities if re.fullmatch(r"\d{1,3}(\.\d{3})*,\d{2}", r["deal_value"])]
    assert len(comma) == facts["decimal_comma_values"] == sum(r["type"] == "offer" for r in activities)
    assert sum(bool(re.fullmatch(r"\d+\.\d{2}", r["credit_limit"])) for r in customers) == facts["decimal_point_values"]

    def shape(value: str) -> str:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return "YYYY-MM-DD"
        return "DD.MM.YYYY" if re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", value) else "other"

    assert Counter(shape(r["consent_date"]) for r in contacts) == facts["consent_date_formats"]
    tokens = facts["null_tokens"]["tokens"]
    assert Counter(r["job_title"] for r in contacts if r["job_title"] in tokens) == tokens

    ids = Counter(r["customer_id"] for r in customers)
    assert (len(customers), len(ids)) == (facts["customer_ids"]["rows"], facts["customer_ids"]["distinct"])
    duplicated = sorted(k for k, v in ids.items() if v > 1)
    assert duplicated == facts["customer_ids"]["duplicated"]
    for customer_id in duplicated:
        one, two = (r for r in customers if r["customer_id"] == customer_id)
        assert one["city"] != two["city"] and one["credit_limit"] != two["credit_limit"], customer_id
    assert sum(r["customer_id"] not in ids for r in contacts) == facts["orphan_contacts"]

    placeholders = facts["placeholder_dates"]
    assert sum(r["closed_on"] == "9999-12-31" for r in customers) == placeholders["customers.closed_on 9999-12-31"]
    assert sum(r["created_on"] == "1900-01-01" for r in customers) == placeholders["customers.created_on 1900-01-01"]
    assert all(r["closed_on"] == "9999-12-31" for r in customers if r["status"] == "A")

    added = facts["added_column"]
    before, after = header(repo / facts["previous"] / added["file"]), header(repo / facts["delivery"] / added["file"])
    assert set(after) - set(before) == {added["column"]} and set(before) < set(after)
    for name in ("customers.csv", "contacts.csv"):
        assert header(repo / facts["previous"] / name) == header(repo / facts["delivery"] / name), name

    personal = facts["personal_data"]
    assert sum(data_profile.is_email(r["email"]) for r in contacts) == personal["contacts.email"]
    assert sum(bool(re.fullmatch(r"\+381 6\d 555 \d{4}", r["phone"])) for r in contacts) == personal["contacts.phone"]
    assert sum(data_profile.is_iban(r["iban"]) for r in contacts if r["iban"]) == personal["contacts.iban"]
    assert sum(bool(r["iban"]) for r in contacts) == personal["contacts.iban"]

    documented = documented_columns(repo)
    delivered = {name: header(repo / facts["delivery"] / name) for name in documented}
    missing = [f"{n.removesuffix('.csv')}.{c}" for n, cols in documented.items() for c in cols if c not in delivered[n]]
    extra = [f"{n.removesuffix('.csv')}.{c}" for n, cols in delivered.items() for c in cols if c not in documented[n]]
    assert sorted(missing) == facts["documented_not_delivered"]
    assert sorted(extra) == facts["delivered_not_documented"]

    vendor = (repo / facts["vendor_document"]).read_text(encoding="utf-8")
    optional = facts["empty_optional_column"]
    assert sum(r["parent_customer_id"] == "" for r in customers) == optional["empty_rows"] == len(customers)
    assert "| `parent_customer_id` | text | optional:" in vendor
    assert sum(r["status"] == "X" for r in customers) == facts["status_x_rows"]
    assert set(ids) and {r["status"] for r in customers} == {"A", "I", "X"}
    assert "X closed by credit control" in vendor


def test_source_contract_facts(repo: Path) -> None:
    facts = FACTS["source-contract"]
    text = (repo / facts["contract"]).read_text(encoding="utf-8")
    assert f'  deliver_by: "{facts["deliver_by"]}"' in text
    assert f"\nowner: {facts['owner']}\n" in text and f"\nchange_process: {facts['change_process']}\n" in text
    columns = contract_columns(text)
    assert (columns["amount"]["type"], columns["amount"]["unit"]) == tuple(facts["amount_in_contract"].split())

    arrivals = [
        r
        for r in read_jsonl(repo / "ops/deliveries.jsonl")
        if r["source"] == "erp" and r["file"].endswith("/orders.csv")
    ]
    assert len(arrivals) == facts["erp_delivery_days"]
    late = [r for r in arrivals if r["arrived_at"][11:16] > facts["deliver_by"]]
    assert len(late) == facts["late_days"]
    window = (min(r["arrived_at"][11:16] for r in late), max(r["arrived_at"][11:16] for r in late))
    assert window == facts["late_arrivals_between"]
    on_time = [r for r in arrivals if r not in late]
    assert len(on_time) == facts["on_time_days"]
    assert all(date.fromisoformat(r["arrived_at"][:10]).weekday() >= 5 for r in on_time)

    shapes = {"1234.50": r"\d+\.\d{2}", "1234,50": r"\d+,\d{2}"}
    for day, shape in facts["amount_format"].items():
        rows = read_csv(repo / "sources" / "erp" / day / "orders.csv")
        assert all(re.fullmatch(shapes[shape], r["amount"]) for r in rows), day

    latest = repo / facts["missing_from"]
    assert set(columns) - set(header(latest)) == {facts["missing_column"]}
    assert set(header(latest)) < set(columns)
    assert facts["missing_column"] in header(repo / "sources/erp/2026-11-03/orders.csv")

    statuses = Counter(r["status"] for r in read_csv(latest))
    assert statuses["on_hold"] == facts["on_hold_rows"]
    allowed = re.findall(r"\w+", columns["status"]["allowed"])
    assert set(statuses) <= set(allowed) and "on_hold" in allowed
    assert facts["crm_contract"] is None and sorted(p.name for p in (repo / "contracts").iterdir()) == ["erp.yaml"]


def test_pipeline_incident_facts(repo: Path) -> None:
    facts = FACTS["pipeline-incident"]
    runs = read_jsonl(repo / "ops/runs.jsonl")
    failed = [r for r in runs if r["status"] == "failed"]
    assert [r["run_id"] for r in failed] == facts["failed_runs"]
    first = failed[0]
    expected = (facts["run_id"], facts["job"], facts["failed_task"], facts["layer"])
    assert (first["run_id"], first["job"], first["task"], first["layer"]) == expected
    value = search(r'numeric: "([^"]+)"', first["error"]).group(1)
    assert value == facts["error_value"]

    bad = repo / "sources" / "erp" / facts["first_bad_delivery"] / "orders.csv"
    good = repo / "sources" / "erp" / facts["last_good_delivery"] / "orders.csv"
    rows = read_csv(bad)
    assert len(rows) == facts["rows_in_bad_delivery"] == first["rows_read"]
    assert rows[0]["amount"] == value
    assert header(good) == header(bad)  # between the good and the bad delivery only the number format changed
    rel, line = facts["cast_at"].split(":")
    assert f"({rel} line {line}, column amount)" in first["error"]
    assert "cast(amount as numeric(12, 2))" in (repo / rel).read_text(encoding="utf-8").splitlines()[int(line) - 1]
    good_runs = [r for r in runs if r["task"] == facts["failed_task"] and r["status"] == "success"]
    assert good_runs[-1]["run_id"] == f"{facts['job']}-{facts['last_good_delivery']}-1"

    log = (repo / "ops/incident-log.md").read_text(encoding="utf-8")
    entry = log.split(f"## {facts['past_incident']}:", 1)[1].split("\n## ", 1)[0]
    assert "invalid input syntax for type numeric" in entry and facts["safe_parse"] in entry
    assert facts["first_bad_delivery"] not in log  # the new incident is not written down yet

    silver = {
        p.relative_to(repo).as_posix(): p.read_text(encoding="utf-8") for p in (repo / "pipeline/silver").glob("*")
    }
    naive = sorted(path for path, sql in silver.items() if "cast(amount as numeric(12, 2))" in sql)
    assert naive == sorted([rel, *facts["same_weakness"]])
    assert [path for path, sql in silver.items() if facts["safe_parse"] in sql] == [facts["already_safe"]]

    gold = [r for r in runs if r["job"] == "build_sales_daily"]
    built = [r for r in gold if r["status"] == "success"]
    assert built[-1]["end"] == facts["gold_last_built"]
    assert all(r["end"][11:16] < "08:00" for r in built)
    assert [r["start"][:10] for r in gold if r["status"] == "skipped"] == facts["gold_skipped"]

    wait = next(r for r in runs if r["run_id"] == facts["run_id"] and r["task"] == "wait_for_file")
    late = facts["late_file"]
    assert wait["status"] == "warning" and wait["error"] is None
    assert f"arrived {late['arrived']}, {late['minutes_after_start']} minutes after the 06:30 start" in wait["message"]
    # The late file is not the cause: the same warning came on 23 days, 21 of which loaded fine.
    warned = {r["run_id"] for r in runs if r["task"] == "wait_for_file" and r["status"] == "warning"}
    loaded = {r["run_id"] for r in runs if r["task"] == facts["failed_task"] and r["status"] == "success"}
    assert (len(warned), len(warned & loaded)) == (23, 21)


def test_the_naive_cast_fails_on_a_decimal_comma_and_the_safe_parse_does_not(repo: Path) -> None:
    with pytest.raises(InvalidOperation):
        naive_cast("12,50")
    assert naive_cast("12.50") == Decimal("12.50")
    assert parse_amount("12,50") == parse_amount("12.50") == Decimal("12.50")
    assert parse_amount("1.234,50") == Decimal("1234.50")
    function = (repo / "pipeline/functions/parse_amount.sql").read_text(encoding="utf-8")
    assert "cast(replace(replace(trim(raw), '.', ''), ',', '.') as numeric(12, 2))" in function
    erp = repo / "sources" / "erp"
    for day in ("2026-11-02", "2026-11-03", "2026-11-04"):
        orders = read_csv(erp / day / "orders.csv")
        failing = 0
        for row in orders:
            try:
                naive_cast(row["amount"])
            except InvalidOperation:
                failing += 1
        assert failing == (0 if day == "2026-11-02" else len(orders)), day
        assert all(parse_amount(r["amount"]) == Decimal(r["amount"].replace(",", ".")) for r in orders), day
        for name in ("returns.csv", "payments.csv"):  # still plain numbers: the same weakness, waiting
            assert all(naive_cast(r["amount"]) > 0 for r in read_csv(erp / day / name)), (day, name)
        invoices = read_csv(erp / day / "invoices.csv")
        assert all("," in r["amount"] for r in invoices), day  # the Serbian format since September
        assert all((parse_amount(r["amount"]) or 0) > 0 for r in invoices), day


def test_data_quality_facts(repo: Path) -> None:
    facts = FACTS["data-quality"]
    checks = read_jsonl(repo / "ops/checks.jsonl")
    assert len(checks) == facts["results"]
    days = sorted({c["date"] for c in checks})
    assert (days[0], days[-1]) == facts["period"] and days == [d.isoformat() for d in PERIOD]
    by_check: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in checks:
        by_check[result["check"]].append(result)

    warns = facts["always_warns"]
    email = by_check[warns["check"]]
    assert len(email) == warns["days"] == len(days) and {c["status"] for c in email} == {"warn"}
    assert (min(c["failing_rows"] for c in email), max(c["failing_rows"] for c in email)) == warns["failing_rows"]

    cannot = facts["cannot_fail"]
    results = by_check[cannot["check"]]
    assert len(results) == cannot["results"] and sum(c["status"] != "pass" for c in results) == cannot["failures"]
    assert all(c["failing_rows"] == 0 for c in results)
    never = sorted(name for name, found in by_check.items() if all(c["status"] == "pass" for c in found))
    assert never == facts["never_failed"]
    yaml_text = "".join(
        p.read_text(encoding="utf-8") for p in (repo / "checks").glob("*.yaml") if p.stem != "quarantine"
    )
    defined = set(re.findall(r"^  - name: (\w+)$", yaml_text, re.MULTILINE))
    assert defined == set(by_check)
    cases = (repo / "checks/tests/cases.yaml").read_text(encoding="utf-8")
    tried = set(re.findall(r"^  - check: (\w+)$", cases, re.MULTILINE))
    assert sorted(defined - tried) == facts["without_a_test_case"] and tried <= defined

    fresh = facts["freshness"]
    assert f'sla: "{fresh["sla"]}"' in (repo / "jobs/build_sales_daily.yaml").read_text(encoding="utf-8")
    assert [c["date"] for c in checks if c["table"] == fresh["table"] and c["status"] == "fail"] == fresh["failed_on"]

    rule = facts["quarantine"]
    rows = [r for r in read_jsonl(repo / "ops/quarantine.jsonl") if r["rule"] == rule["rule"]]
    per_day = Counter(r["date"] for r in rows)
    before = [n for d, n in per_day.items() if d < rule["from"]]
    after = [n for d, n in per_day.items() if d >= rule["from"]]
    assert (len(before), sum(before), max(before)) == (
        rule["days_before"],
        rule["rows_before"],
        rule["max_a_day_before"],
    )
    assert (len(after), sum(after), min(after)) == (rule["days_from"], rule["rows_from"], rule["min_a_day_from"])
    assert min(r["date"] for r in rows if r["value"] == rule["store"]) == rule["from"]
    stores = {r["store_id"] for r in read_csv(repo / "ref/stores.csv")}
    assert rule["store"] not in stores and all(r["value"] not in stores for r in rows)
    assert not [name for name in by_check if "quarantine" in name]  # no check watches the quarantine

    rank = {"pass": 0, "warn": 1, "fail": 2}
    worst: dict[str, str] = {}
    for result in checks:
        if result["date"] == facts["period"][1]:
            worst[result["table"]] = max(worst.get(result["table"], "pass"), result["status"], key=lambda s: rank[s])
    verdict = {"pass": "safe", "warn": "use with care", "fail": "do not use"}
    assert {table: verdict[worst[table]] for table in facts["verdicts"]} == facts["verdicts"]

    holiday = facts["holiday"]
    store_check = {c["date"]: c for c in by_check[holiday["check"]]}
    failed = store_check[holiday["failed_on"]]
    day = date.fromisoformat(holiday["orders_of"])
    assert (failed["status"], failed["failing_rows"]) == ("fail", holiday["failing_rows"])
    assert f"{day:%A} {day.day} {day:%B}" in failed["note"] and "Hungarian national holiday" in failed["note"]
    assert store_check[holiday["passed_on"]]["status"] == "pass"
    assert [d for d, c in store_check.items() if c["status"] == "fail"] == [holiday["failed_on"]]
    hungarian = [r["store_id"] for r in read_csv(repo / "ref/stores.csv") if r["country"] == "HU"]
    assert len(hungarian) == holiday["failing_rows"]
    sample = read_csv(repo / "samples/gold/sales_daily.csv")
    assert not [r for r in sample if r["sales_date"] == holiday["orders_of"] and r["store_id"] in hungarian]


def test_the_amount_check_can_never_fail(repo: Path) -> None:
    text = (repo / "checks/silver.yaml").read_text(encoding="utf-8")
    block = text.split("  - name: orders_amount_positive\n", 1)[1].split("\n  - name: ", 1)[0]
    query = search(r'^    query: "(.*)"$', block).group(1)
    left, operator, right = search(r"\band (\w+) (<|<=|>|>=|=|<>) (\w+)$", query).groups()
    assert (left, operator, right) == ("amount", "<", "amount")
    amounts = [Decimal(r["amount"]) for r in read_csv(repo / "sources/erp/2026-11-02/orders.csv")]
    for amount in [*amounts, Decimal("-12.50"), Decimal(0)]:
        assert not amount < amount  # false for every number, bad or good, so the check passes whatever comes
    assert "orders_amount_positive" not in (repo / "checks/tests/cases.yaml").read_text(encoding="utf-8")


def test_data_cost_facts(repo: Path) -> None:
    facts = FACTS["data-cost"]
    usage = read_csv(repo / "ops/usage.csv")
    assert len({r["date"] for r in usage}) == facts["period_days"]
    eur: dict[str, Decimal] = defaultdict(Decimal)
    hours: dict[str, Decimal] = defaultdict(Decimal)
    for row in usage:
        eur[row["resource"]] += Decimal(row["compute_eur"])
        hours[row["resource"]] += Decimal(row["compute_hours"])
        rate = Decimal("1.20") if row["cluster"] == "dev-adhoc" else Decimal("2.00")
        assert Decimal(row["compute_hours"]) * rate == Decimal(row["compute_eur"]), row
    assert dict(eur) == facts["compute_eur"]
    assert sum(eur.values()) == facts["compute_total"]
    storage = read_csv(repo / "ops/storage.csv")
    assert sum(Decimal(r["gb"]) for r in storage) == facts["storage_gb"]
    assert sum(Decimal(r["eur_per_month"]) for r in storage) == facts["storage_total"]
    assert all(Decimal(r["gb"]) * Decimal("0.04") == Decimal(r["eur_per_month"]) for r in storage)
    assert facts["compute_total"] + facts["storage_total"] == facts["total"]

    queries = read_csv(repo / "ops/query_log.csv")
    reads: dict[str, int] = defaultdict(int)
    for row in queries:
        reads[row["table"]] += int(row["queries"])
    unread = facts["unread_table"]
    largest = max(storage, key=lambda r: Decimal(r["gb"]))
    expected = (unread["table"], unread["gb"], unread["eur_per_month"])
    assert (largest["table"], Decimal(largest["gb"]), Decimal(largest["eur_per_month"])) == expected
    assert reads.get(unread["table"], 0) == unread["queries"]

    runs = read_jsonl(repo / "ops/runs.jsonl")
    full = facts["full_reload"]
    reloads = [r for r in runs if r["job"] == full["job"]]
    assert len(reloads) == facts["period_days"]
    assert sum(r["rows_written"] for r in reloads) == full["rows_written"]
    assert sum(r["rows_changed"] for r in reloads) == full["rows_changed"]
    assert max(r["rows_changed"] for r in reloads) == full["max_changed_a_day"]
    assert all(r["rows_changed"] * 1000 < r["rows_written"] for r in reloads)  # under 0.1% on every day
    assert eur[full["job"]] == full["eur"]

    frequent = facts["too_frequent"]
    job = (repo / "jobs" / f"{frequent['job']}.yaml").read_text(encoding="utf-8")
    minutes = int(search(r'^schedule: "\*/(\d+) \* \* \* \*"$', job).group(1))
    assert 24 * 60 // minutes == frequent["runs_a_day"]
    assert frequent["runs_a_day"] * facts["period_days"] == frequent["runs"]
    assert "record_runs: failures" in job and not [r for r in runs if r["job"] == frequent["job"]]
    assert hours[frequent["job"]] == Decimal("2.16") * facts["period_days"]  # 288 runs of 27 node seconds a day
    assert eur[frequent["job"]] == frequent["eur"]
    assert reads[frequent["table"]] == frequent["queries"]
    assert max(int(r["queries"]) for r in queries if r["table"] == frequent["table"]) == 2

    never = facts["never_stops"]
    dev = [r for r in usage if r["resource"] == never["cluster"]]
    assert len(dev) == facts["period_days"] and all(r["compute_hours"] == "24.00" for r in dev)
    assert (hours[never["cluster"]], eur[never["cluster"]]) == (never["hours"], never["eur"])
    weekend = [r for r in dev if date.fromisoformat(r["date"]).weekday() >= 5]
    assert (len(weekend), sum(Decimal(r["compute_eur"]) for r in weekend)) == (
        never["weekend_days"],
        never["weekend_eur"],
    )
    clusters = Counter(
        search(r"^cluster: (\S+)$", p.read_text(encoding="utf-8")).group(1) for p in (repo / "jobs").glob("*")
    )
    assert clusters[never["cluster"]] == never["jobs"] and set(clusters) == {"etl"}

    decoy = facts["decoy"]
    jobs_eur = {name: value for name, value in eur.items() if name != never["cluster"]}
    assert max(jobs_eur, key=lambda name: jobs_eur[name]) == decoy["job"] and jobs_eur[decoy["job"]] == decoy["eur"]
    readers = {r["consumer"] for r in queries if r["table"] == decoy["table"]}
    assert len(readers) == decoy["consumers"] and reads[decoy["table"]] == decoy["queries"]
    hourly = {r["consumer"] for r in queries if r["table"] == decoy["table"] and r["queries"] == "24"}
    assert len(hourly) == decoy["hourly_consumers"]


def test_data_migration_facts(repo: Path) -> None:
    facts = FACTS["data-migration"]
    inventory = read_csv(repo / facts["inventory"])
    assert len(inventory) == facts["jobs"]
    assert f"on {facts['as_of']}" in (repo / "legacy/README.md").read_text(encoding="utf-8")
    as_of = date.fromisoformat(facts["as_of"])
    assert as_of == AS_OF
    age = {r["job"]: (as_of - date.fromisoformat(r["last_run"][:10])).days for r in inventory}
    assert sorted(job for job, days in age.items() if days > facts["dead_after_days"]) == facts["dead"]
    assert min(age[job] for job in facts["dead"]) > facts["dead_after_days"] + 30  # no case near the line
    assert all(days <= 20 for job, days in age.items() if job not in facts["dead"])

    scripts = {r["job"]: (repo / "legacy" / r["script"]).read_text(encoding="utf-8") for r in inventory}
    assert len({r["script"] for r in inventory}) == facts["jobs"]
    by_text: dict[str, list[str]] = defaultdict(list)
    for job, text in scripts.items():
        by_text[text].append(job)
    assert [sorted(jobs) for jobs in by_text.values() if len(jobs) > 1] == [facts["identical_sql"]]
    assert len({r["target"] for r in inventory if r["job"] in facts["identical_sql"]}) == 2

    depends = {r["job"]: set(filter(None, r["depends_on"].split(";"))) for r in inventory}
    writes = {job: set(re.findall(r"(?:> |to ')(/data/[\w./]+)", text)) for job, text in scripts.items()}
    reads = {job: set(re.findall(r"(?:from '|put )(/data/[\w./]+)", text)) for job, text in scripts.items()}
    links = [
        (writer, reader, path)
        for reader, paths in reads.items()
        for path in sorted(paths)
        for writer, written in writes.items()
        if path in written
    ]
    hidden = facts["undeclared_file_dependency"]
    assert len(links) == 3
    assert [link for link in links if link[0] not in depends[link[1]]] == [
        (hidden["writer"], hidden["reader"], hidden["path"])
    ]

    outside = facts["outside_consumer"]
    assert [job for job, text in scripts.items() if "sftp://" in text] == [outside["job"]]
    assert outside["host"] in scripts[outside["job"]] and outside["secret"] in scripts[outside["job"]]

    together: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in inventory:
        together[(row["schedule"], row["target"])].append(row["job"])
    same = facts["same_minute_same_table"]
    clashes = [(key, sorted(jobs)) for key, jobs in together.items() if len(jobs) > 1]
    assert clashes == [((same["schedule"], same["table"]), same["jobs"])]

    monthly = facts["monthly_on_schedule"]
    row = next(r for r in inventory if r["job"] == monthly["job"])
    _, _, day_of_month, month, weekday = row["schedule"].split()
    assert row["schedule"] == monthly["schedule"] and (month, weekday) == ("*", "*")
    this_month = date(as_of.year, as_of.month, int(day_of_month))
    last_due = this_month if as_of >= this_month else date(as_of.year, as_of.month - 1, int(day_of_month))
    assert row["last_run"][:10] == monthly["last_run"] == last_due.isoformat()
    assert this_month.isoformat() == monthly["next_run"] and age[monthly["job"]] == 20


def test_data_product_facts(repo: Path) -> None:
    facts = FACTS["data-product"]
    sample = read_csv(repo / facts["sample"])
    assert len(sample) == facts["sample_rows"]
    store_days = Counter((r["store_id"], r["sales_date"]) for r in sample)
    assert len(store_days) == facts["store_days"]
    assert (
        sum(n > 1 for n in store_days.values()) == facts["store_days_with_two_rows"] and max(store_days.values()) == 2
    )
    assert max(Counter(tuple(r[c] for c in facts["real_grain"]) for r in sample).values()) == 1
    assert Counter(r["currency"] for r in sample) == facts["rows_by_currency"]

    doc = (repo / facts["document"]).read_text(encoding="utf-8")
    assert "Grain: one row per store and day." in doc and "currency" not in doc.split("## Columns")[0]
    assert facts["documented_grain"] == ["store_id", "sales_date"]
    column = facts["personal_column"]
    assert column in header(repo / facts["sample"]) and all("@" in r[column] for r in sample)
    assert f"c.email as {column}" in (repo / "pipeline/gold/sales_daily.sql").read_text(encoding="utf-8")
    assert not re.search(r"(?i)\bowner\b", doc) and facts["owner"] is None
    assert not re.search(r"\d{2}:\d{2}", doc) and facts["sla_in_document"] is None
    assert f'sla: "{facts["sla_in_job"]}"' in (repo / "jobs/build_sales_daily.yaml").read_text(encoding="utf-8")

    net = facts["net_revenue"]
    metrics = (repo / "reports/bi/metrics.md").read_text(encoding="utf-8")
    sql = (repo / "pipeline/gold/sales_daily.sql").read_text(encoding="utf-8")
    assert "returns are not deducted" in doc and net["docs/products/sales_daily.md"] == "without returns"
    assert "minus cancellations minus returns" in metrics and net["reports/bi/metrics.md"] == "with returns"
    assert "return" not in sql and net["pipeline/gold/sales_daily.sql"] == "without returns"
    for row in sample:
        assert Decimal(row["gross_revenue"]) - Decimal(row["cancelled_amount"]) == Decimal(row["net_revenue"])

    queries = [r for r in read_csv(repo / "ops/query_log.csv") if r["table"] == facts["table"]]
    assert sorted({r["consumer"] for r in queries}) == facts["consumers"]
    assert sum(int(r["queries"]) for r in queries) == facts["queries"]
    assert "| `kg_eq` | kilogram equivalent" in doc and "kg_eq" in header(repo / facts["sample"])


def test_runbook_facts(repo: Path) -> None:
    facts = FACTS["runbook"]
    found = sorted(p.relative_to(repo).as_posix() for p in (repo / "docs").rglob("*.md") if "products" not in p.parts)
    assert found == facts["documents"]
    docs = {rel: (repo / rel).read_text(encoding="utf-8") for rel in facts["documents"]}
    runbook = docs["docs/runbook.md"]

    jobs: dict[str, str] = {}
    for path in (repo / "jobs").glob("*.yaml"):
        text = path.read_text(encoding="utf-8")
        assert search(r"^name: (\w+)$", text).group(1) == path.stem
        jobs[path.stem] = text
    assert sorted(jobs) == facts["jobs"]
    old, new = facts["renamed_job"]
    assert f"`{old}`" in runbook and old not in jobs and new in jobs
    assert [rel for rel in tracked(repo) if old in (repo / rel).read_text(encoding="utf-8")] == ["docs/runbook.md"]

    makefile = (repo / "Makefile").read_text(encoding="utf-8")
    targets = set(re.findall(r"^([\w-]+):(?!=)", makefile, re.MULTILINE))
    assert sorted(targets) == facts["make_targets"]
    used = {rel: set(re.findall(r"`make ([\w-]+)", text)) for rel, text in docs.items()}
    old, new = facts["renamed_target"]
    assert {rel: sorted(names - targets) for rel, names in used.items() if names - targets} == {
        "docs/runbook.md": [old]
    }
    assert new in targets and new in used["docs/howto/backfill.md"]
    alias, real = facts["alias"]
    assert alias in used["docs/runbook.md"] and re.search(rf"^{alias}: {real}\b", makefile, re.MULTILINE)

    code = "".join(p.read_text(encoding="utf-8") for p in sorted((repo / "pipeline").rglob("*.py")))
    read = set(re.findall(r'os\.environ(?:\.get\(|\[)"(\w+)"', code))
    assert sorted(read) == facts["settings_read"]
    documented = set(re.findall(r"^- `([A-Z][A-Z0-9_]+)`:", runbook, re.MULTILINE))
    old, new = facts["renamed_setting"]
    assert (documented - read, read - documented) == ({old}, {new})

    assert "contract" not in docs["docs/howto/add-a-source.md"]
    assert "    require_contract(source)\n" in (repo / "pipeline/loaders/common.py").read_text(encoding="utf-8")
    assert "contract: contracts/erp.yaml" in (repo / "pipeline/config/sources.yaml").read_text(encoding="utf-8")
    assert "pipeline/config/sources.yaml" in facts["missing_step"]

    schedule = facts["schedule"]
    assert f'schedule: "{schedule["cron"]}"' in jobs[schedule["job"]]
    minute, hour = schedule["cron"].split()[:2]
    assert f"{int(hour):02d}:{int(minute):02d}" == schedule["time"]
    rows = dict(re.findall(r"^\| `(\w+)` \| ([^|]+) \|", runbook, re.MULTILINE))
    assert rows[schedule["job"]].strip() == f"daily at {schedule['runbook']}"
    for job, when in rows.items():  # every other time in the runbook's table is the job's cron
        times = re.findall(r"\d{2}:\d{2}", when)
        if job in jobs and job != schedule["job"] and times:
            minute, hour = search(r'^schedule: "(.+)"$', jobs[job]).group(1).split()[:2]
            assert times == [f"{int(hour):02d}:{int(minute):02d}"], job


def test_the_records_agree_with_the_files_on_disk(repo: Path) -> None:
    runs = read_jsonl(repo / "ops/runs.jsonl")
    deliveries = {r["file"]: r for r in read_jsonl(repo / "ops/deliveries.jsonl")}
    on_disk = sorted(p.relative_to(repo).as_posix() for p in (repo / "sources").rglob("*.csv"))
    assert len(on_disk) == 18
    for rel in on_disk:
        assert deliveries[rel]["rows"] == len(read_csv(repo / rel, ";" if rel.endswith("activities.csv") else ",")), rel
    tasks = {
        "orders.csv": "bronze.erp_orders",
        "invoices.csv": "bronze.erp_invoices",
        "returns.csv": "bronze.erp_returns",
        "payments.csv": "bronze.erp_payments",
    }
    for rel in [r for r in on_disk if r.startswith("sources/erp/")]:
        day, name = rel.split("/")[2:]
        loaded = [r["rows_read"] for r in runs if r["task"] == tasks[name] and r["run_id"].endswith(f"-{day}-1")]
        assert loaded == [deliveries[rel]["rows"]], rel
    for record in runs:
        offset = "+02:00" if record["start"][:10] < "2026-10-25" else "+01:00"
        assert record["start"].endswith(offset) and record["end"].endswith(offset) and record["start"] <= record["end"]

    stores = {r["store_id"] for r in read_csv(repo / "ref/stores.csv")}
    orders = read_csv(repo / "sources/erp/2026-11-02/orders.csv")
    unknown = {f"{r['order_id']}/{r['line_no']}" for r in orders if r["store_id"] not in stores}
    quarantined = {
        r["row_id"]
        for r in read_jsonl(repo / "ops/quarantine.jsonl")
        if r["date"] == "2026-11-02" and r["rule"] == "unknown_store_id"
    }
    assert quarantined == unknown
    silver = next(r for r in runs if r["run_id"] == "load_erp_orders-2026-11-02-1" and r["task"] == "silver.orders")
    assert silver["rows_written"] == len(orders) - len(unknown)

    groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in orders:
        if row["store_id"] in stores:
            groups[(row["store_id"], row["currency"])].append(row)
    sample = read_csv(repo / "samples/gold/sales_daily.csv")
    last_day = {(r["store_id"], r["currency"]): r for r in sample if r["sales_date"] == "2026-11-01"}
    assert set(last_day) == set(groups)
    for key, lines in groups.items():
        row = last_day[key]
        assert (int(row["orders"]), int(row["order_lines"])) == (len({r["order_id"] for r in lines}), len(lines))
        assert Decimal(row["gross_revenue"]) == sum(Decimal(r["amount"]) for r in lines)
        assert Decimal(row["cancelled_amount"]) == sum(
            Decimal(r["amount"]) for r in lines if r["status"] == "cancelled"
        )
        assert Decimal(row["kg_eq"]) == Decimal(sum(int(r["weight_g"]) for r in lines)) / 1000
    assert {r["built_at"] for r in sample} == {FACTS["pipeline-incident"]["gold_last_built"]}


def test_personal_data_looks_real_and_everything_is_fictional(repo: Path) -> None:
    guard = load(ROOT / "shared" / "guard.py")
    contacts = repo / "sources/crm/2026-11-04/contacts.csv"
    ibans = [r["iban"] for r in read_csv(contacts) if r["iban"]]
    assert all(re.fullmatch(r"RS\d{2}999\d{15}", value) and guard.iban_ok(value) for value in ibans)
    _, found = guard.redact(contacts.read_text(encoding="utf-8"))
    assert found == {"e-mail": 911, "IBAN": 126}
    _, found = guard.redact((repo / "samples/gold/sales_daily.csv").read_text(encoding="utf-8"))
    assert found == {"e-mail": 904}
    for path in repo.rglob("*"):
        if path.is_file() and ".git" not in path.parts:
            text = path.read_text(encoding="utf-8")
            for domain in re.findall(r"[\w.+-]+@([\w-]+(?:\.[\w-]+)+)", text):
                assert domain in ("example.com", "example.org"), (path, domain)
            for host in re.findall(r"\b(?:sftp|https?)://([\w.-]+)", text):
                assert host.endswith((".example.org", ".example.com")), (path, host)


def test_credentials_are_only_placeholders(repo: Path) -> None:
    for path in repo.rglob("*"):
        if path.is_file() and ".git" not in path.parts:
            for line in path.read_text(encoding="utf-8").splitlines():
                if re.search(r"(?i)passw(or)?d|api_?key|secret_?key", line):
                    assert re.search(r"\$\{[A-Z_]+\}", line), (path, line)
                assert not re.search(r"://[^/\s:@]+:[^@\s]+@", line), (path, line)
    assert "${SFTP_PASSWORD}" in (repo / "legacy/jobs/send_partner_orders.sh").read_text(encoding="utf-8")


def test_the_python_code_compiles(repo: Path, tmp_path: Path) -> None:
    for path in sorted((repo / "pipeline").rglob("*.py")):
        target = tmp_path / path.relative_to(repo).with_suffix(".pyc")
        py_compile.compile(str(path), cfile=str(target), doraise=True)
