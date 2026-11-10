"""The git history of the acme-pipeline fixture.

The files under files/ are the state after the last commit. Each commit lists the files it adds and the edits it
makes, as (path, before, after); the builder undoes the edits backwards to recover each earlier state.

The story: Acme Foods, a food distributor in Novi Sad, starts a small data platform in June 2026. Bogdan loads the
ERP order lines into bronze and silver and copies the old warehouse's history once for a reconciliation; customers
and stock follow. Tijana builds gold.sales_daily for finance and the BI board. Dragana adds the ERP finance files and
writes the runbook and the how-to guides in August. In September the invoice export switches to a decimal comma and
silver.invoices fails; Dragana adds a safe parse for invoices and logs the incident. Then the platform moves under
the documents: the loaders start to require a contract, load_erp_orders moves to 06:30, the warehouse setting and the
backfill target are renamed, the CRM job is built as ingest_crm, and none of it reaches the runbook. On 4 November
Dragana commits the inventory of the old cron estate for the migration. The 3 November failure of load_erp_orders is
in the run records but not yet in the incident log. Everything here is fictional.
"""

BOGDAN = ("Bogdan Stanar", "bogdan.stanar@example.com")
DRAGANA = ("Dragana Vujić", "dragana.vujic@example.com")
TIJANA = ("Tijana Krsmanović", "tijana.krsmanovic@example.com")

MAKEFILE_CHECKS = "\tpython3 -m pipeline.runner checks --layer $(LAYER)\n"
MAKEFILE_SAMPLES = "samples:  ## CSV copies of the served tables into samples/\n"

REGISTRY_CODE = '''from pipeline.config import settings

REGISTRY = Path(__file__).resolve().parent.parent / "config" / "sources.yaml"


def registered_sources() -> dict[str, dict[str, str]]:
    """The sources of pipeline/config/sources.yaml as {name: {key: value}}."""
    sources: dict[str, dict[str, str]] = {}
    current = ""
    for raw in REGISTRY.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip() or line == "sources:":
            continue
        if not line.startswith("    "):
            current = line.strip().removesuffix(":")
            sources[current] = {}
        else:
            key, _, value = line.strip().partition(":")
            sources[current][key] = value.strip()
    return sources


def require_contract(source: str) -> Path:
    """The contract of a source. A source without a registered contract is not loaded."""
    entry = registered_sources().get(source, {})
    if not entry.get("contract"):
        raise SystemExit(f"source {source} has no contract registered in pipeline/config/sources.yaml")
    return Path(entry["contract"])


def read_delivery'''

CUSTOMER_CHECKS = """  - name: customers_email_format
    table: silver.customers
    runs: after_task
    query: "select customer_id from silver.customers where email is not null and email not like '%_@_%._%'"
    warn_if: "rows > 0"
    fail_if: "rows > 500"
  - name: customers_id_unique
    table: silver.customers
    runs: after_task
    query: "select customer_id from silver.customers group by customer_id having count(*) > 1"
    fail_if: "rows > 0"
"""

INVOICE_CHECK = """  - name: invoices_amount_parsed
    table: silver.invoices
    runs: after_task
    query: "select invoice_id from silver.invoices where load_date = :run_date and amount is null"
    fail_if: "rows > 0"
"""

SALES_DAILY_CHECKS = (
    "  - name: sales_daily_fresh\n"
    "    table: gold.sales_daily\n"
    '    runs: "0 8 * * *"\n'
    "    freshness: built_at\n"
    '    fail_if: "not built today by 08:00"\n'
    "  - name: sales_daily_key_unique\n"
    "    table: gold.sales_daily\n"
    "    runs: after_task\n"
    '    query: "select sales_date, store_id, currency from gold.sales_daily'
    ' group by sales_date, store_id, currency having count(*) > 1"\n'
    '    fail_if: "rows > 0"\n'
)

STORE_RULE = '    condition: "store_id not in (select store_id from ref.stores)"\n'
TAX_ID_RULE = """  - name: missing_tax_id
    table: silver.customers
    source: erp_replica.customers
    column: tax_id
    condition: "nullif(trim(tax_id), '') is null"
"""

LAST_STOCK_CASE = '    bad_rows: "1 row with on_hand -4"\n    result: fail\n'
INVOICE_CASE = """  - check: invoices_amount_parsed
    tried_on: "2026-09-15"
    bad_rows: "amounts 1.234,50 and 1234,50 and an empty amount"
    result: fail
"""

LEGACY_JOBS = [
    "legacy/jobs/cleanup_tmp_tables.sql",
    "legacy/jobs/daily_customer_sync.sql",
    "legacy/jobs/export_sales_by_store.sql",
    "legacy/jobs/export_store_sales.sql",
    "legacy/jobs/fax_order_import.sh",
    "legacy/jobs/fix_stock_snapshot.sql",
    "legacy/jobs/load_dw_orders.sql",
    "legacy/jobs/load_price_list.sql",
    "legacy/jobs/load_stock_snapshot.sql",
    "legacy/jobs/month_end_margin.sql",
    "legacy/jobs/nightly_orders_extract.sh",
    "legacy/jobs/old_loyalty_points.sql",
    "legacy/jobs/promo_export_2025.sh",
    "legacy/jobs/send_partner_orders.sh",
    "legacy/jobs/stage_price_list.sh",
    "legacy/jobs/store_kpi_v1.sql",
    "legacy/jobs/supplier_scorecard.sql",
]

COMMITS = [
    {
        "date": "2026-06-08T10:15:00+02:00",
        "author": BOGDAN,
        "message": "Start the platform: ERP order lines into bronze and silver",
        "add": [
            ".gitignore",
            "Makefile",
            "pipeline/__init__.py",
            "pipeline/config/__init__.py",
            "pipeline/config/settings.py",
            "pipeline/warehouse.py",
            "pipeline/runner.py",
            "pipeline/loaders/__init__.py",
            "pipeline/loaders/common.py",
            "pipeline/loaders/erp.py",
            "pipeline/bronze/erp_orders.sql",
            "pipeline/silver/orders.sql",
            "jobs/load_erp_orders.yaml",
            "ref/stores.csv",
            "checks/bronze.yaml",
            "checks/silver.yaml",
            "checks/quarantine.yaml",
        ],
    },
    {
        "date": "2026-06-22T16:40:00+02:00",
        "author": BOGDAN,
        "message": "One-off copy of the old warehouse's order history, for the reconciliation",
        "add": ["pipeline/bronze/erp_orders_history_full.sql"],
    },
    {
        "date": "2026-07-06T11:05:00+02:00",
        "author": BOGDAN,
        "message": "Customers and stock: rebuild_customers every morning, refresh_stock every 5 minutes",
        "add": [
            "pipeline/silver/customers.sql",
            "pipeline/gold/stock_levels.sql",
            "jobs/rebuild_customers.yaml",
            "jobs/refresh_stock.yaml",
            "checks/gold.yaml",
        ],
        "edit": [
            (
                "checks/silver.yaml",
                'o.order_date = :data_date)"\n    fail_if: "rows > 0"\n',
                'o.order_date = :data_date)"\n    fail_if: "rows > 0"\n' + CUSTOMER_CHECKS,
            ),
            ("checks/quarantine.yaml", STORE_RULE, STORE_RULE + TAX_ID_RULE),
        ],
    },
    {
        "date": "2026-07-20T14:30:00+02:00",
        "author": TIJANA,
        "message": "gold.sales_daily for finance and the BI sales board; bad-data cases for the checks",
        "add": [
            "pipeline/gold/sales_daily.sql",
            "pipeline/tools/__init__.py",
            "pipeline/tools/export_samples.py",
            "jobs/build_sales_daily.yaml",
            "docs/products/sales_daily.md",
            "reports/bi/metrics.md",
            "checks/tests/cases.yaml",
        ],
        "edit": [
            (
                "checks/gold.yaml",
                "checks:\n  - name: stock_levels_fresh\n",
                "checks:\n" + SALES_DAILY_CHECKS + "  - name: stock_levels_fresh\n",
            ),
            ("Makefile", ".PHONY: run status backfill checks\n", ".PHONY: run status backfill checks samples\n"),
            (
                "Makefile",
                MAKEFILE_CHECKS,
                MAKEFILE_CHECKS + "\n" + MAKEFILE_SAMPLES + "\tpython3 -m pipeline.tools.export_samples --days 29\n",
            ),
        ],
    },
    {
        "date": "2026-08-10T09:50:00+02:00",
        "author": DRAGANA,
        "message": "ERP finance files: invoices, returns and payments into bronze and silver",
        "add": [
            "pipeline/bronze/erp_invoices.sql",
            "pipeline/bronze/erp_returns.sql",
            "pipeline/bronze/erp_payments.sql",
            "pipeline/silver/invoices.sql",
            "pipeline/silver/returns.sql",
            "pipeline/silver/payments.sql",
            "jobs/load_erp_finance.yaml",
        ],
        "edit": [
            (
                "pipeline/loaders/erp.py",
                '    "orders": ("erp_orders", "orders.csv"),\n}\n',
                '    "orders": ("erp_orders", "orders.csv"),\n'
                '    "invoices": ("erp_invoices", "invoices.csv"),\n'
                '    "returns": ("erp_returns", "returns.csv"),\n'
                '    "payments": ("erp_payments", "payments.csv"),\n'
                "}\n",
            ),
        ],
    },
    {
        "date": "2026-08-24T15:20:00+02:00",
        "author": DRAGANA,
        "message": "Runbook, how-to guides and READMEs for whoever is on call",
        "add": [
            "README.md",
            "ops/README.md",
            "docs/runbook.md",
            "docs/howto/add-a-source.md",
            "docs/howto/backfill.md",
            "docs/howto/rerun-a-failed-job.md",
        ],
    },
    {
        "date": "2026-09-15T10:40:00+02:00",
        "author": DRAGANA,
        "message": "Parse amounts safely: silver.invoices failed on a decimal comma",
        "add": ["pipeline/functions/parse_amount.sql", "ops/incident-log.md"],
        "edit": [
            (
                "pipeline/silver/invoices.sql",
                "-- silver.invoices: the ERP invoices of one delivery, typed.\n",
                "-- silver.invoices: the ERP invoices of one delivery, typed.\n"
                "-- The amount goes through util.parse_amount (pipeline/functions/parse_amount.sql): see the incident"
                " of 2026-09-14.\n",
            ),
            (
                "pipeline/silver/invoices.sql",
                "  cast(amount as numeric(12, 2)) as amount,\n",
                "  util.parse_amount(amount) as amount,\n",
            ),
            (
                "checks/silver.yaml",
                'having count(*) > 1"\n    fail_if: "rows > 0"\n',
                'having count(*) > 1"\n    fail_if: "rows > 0"\n' + INVOICE_CHECK,
            ),
            ("checks/tests/cases.yaml", LAST_STOCK_CASE, LAST_STOCK_CASE + INVOICE_CASE),
        ],
    },
    {
        "date": "2026-09-28T13:10:00+02:00",
        "author": TIJANA,
        "message": "Contract for the ERP orders feed; the loaders refuse a source without a contract",
        "add": ["contracts/erp.yaml", "pipeline/config/sources.yaml"],
        "edit": [
            (
                "pipeline/loaders/common.py",
                '"""Shared code of the loaders: reading a delivery, writing bronze rows."""\n',
                '"""Shared code of the loaders: the source registry, reading a delivery, writing bronze rows."""\n',
            ),
            (
                "pipeline/loaders/common.py",
                "from pipeline.config import settings\n\n\ndef read_delivery",
                REGISTRY_CODE,
            ),
            (
                "pipeline/loaders/common.py",
                "-> int:\n    rows = read_delivery(source, day, name, delimiter)\n",
                "-> int:\n    require_contract(source)\n    rows = read_delivery(source, day, name, delimiter)\n",
            ),
            (
                "README.md",
                "| `sources/` | the deliveries, the last three per source (not in git), and the vendors' documents |\n",
                "| `sources/` | the deliveries, the last three per source (not in git), and the vendors' documents |\n"
                "| `contracts/` | data contracts with the source systems |\n",
            ),
        ],
    },
    {
        "date": "2026-10-05T08:55:00+02:00",
        "author": BOGDAN,
        "message": "load_erp_orders starts at 06:30 and waits for the file: the ERP delivers late on working days",
        "edit": [
            ("jobs/load_erp_orders.yaml", 'schedule: "0 5 * * *"\n', 'schedule: "30 6 * * *"\n'),
            (
                "jobs/load_erp_orders.yaml",
                "steps:\n  - task: bronze.erp_orders\n",
                "steps:\n"
                "  - task: wait_for_file\n"
                "    layer: landing\n"
                '    path: "sources/erp/{date}/orders.csv"\n'
                "    timeout_minutes: 180\n"
                "  - task: bronze.erp_orders\n",
            ),
        ],
    },
    {
        "date": "2026-10-12T17:25:00+02:00",
        "author": BOGDAN,
        "message": "WAREHOUSE_DSN like the other services; Makefile: backfill-day takes JOB and DATE, dq is an alias",
        "edit": [
            (
                "pipeline/config/settings.py",
                'WAREHOUSE_URL = os.environ["ACME_WAREHOUSE_URL"]\n',
                'WAREHOUSE_DSN = os.environ["WAREHOUSE_DSN"]\n',
            ),
            ("pipeline/warehouse.py", "settings.WAREHOUSE_URL", "settings.WAREHOUSE_DSN"),
            (
                "Makefile",
                ".PHONY: run status backfill checks samples\n",
                ".PHONY: run status backfill-day checks dq samples\n",
            ),
            (
                "Makefile",
                "backfill:  ## load one past delivery of the ERP orders again: make backfill DATE=2026-10-01\n"
                "\tpython3 -m pipeline.runner run load_erp_orders --date $(DATE)\n",
                "backfill-day:  ## run a job again for one past delivery: make backfill-day JOB=load_erp_orders"
                " DATE=2026-10-01\n"
                "\tpython3 -m pipeline.runner run $(JOB) --date $(DATE)\n",
            ),
            (
                "Makefile",
                MAKEFILE_CHECKS + "\n" + MAKEFILE_SAMPLES,
                MAKEFILE_CHECKS + "\ndq: checks  ## alias of checks\n\n" + MAKEFILE_SAMPLES,
            ),
            (
                "docs/howto/backfill.md",
                "2. Load the day again: `make backfill DATE=2026-10-01`.\n",
                "2. Run the job for that day: `make backfill-day JOB=load_erp_orders DATE=2026-10-01`.\n",
            ),
        ],
    },
    {
        "date": "2026-10-21T11:45:00+02:00",
        "author": TIJANA,
        "message": "CRM: the vendor's document, bronze tables and ingest_crm, disabled until there is a contract",
        "add": [
            "sources/crm/README-vendor.md",
            "pipeline/loaders/crm.py",
            "pipeline/bronze/crm_customers.sql",
            "pipeline/bronze/crm_contacts.sql",
            "pipeline/bronze/crm_activities.sql",
            "jobs/ingest_crm.yaml",
        ],
        "edit": [
            (
                "README.md",
                "  of the previous day.\n",
                "  of the previous day. The CRM is being added as a second source,"
                " see `sources/crm/README-vendor.md`.\n",
            ),
        ],
    },
    {
        "date": "2026-11-04T10:30:00+01:00",
        "author": DRAGANA,
        "message": "Migration: inventory and scripts of the old cron estate, exported on 4 November",
        "add": ["legacy/README.md", "legacy/inventory.csv", *LEGACY_JOBS],
        "edit": [
            (
                "README.md",
                "| `reports/bi/` | the BI team's metric definitions |\n",
                "| `reports/bi/` | the BI team's metric definitions |\n"
                "| `legacy/` | the old cron estate that is being moved onto the platform |\n",
            ),
        ],
    },
]
