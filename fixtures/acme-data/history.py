"""The git history of the acme-data fixture.

The files under files/ are the state after the last commit. Each commit lists the files it adds and the edits it
makes, as (path, before, after). The builder walks the list backwards, undoing each edit, to recover the state after
every commit, then replays it forwards with git.

The story: Acme Foods, a food retailer in Novi Sad with 12 stores, built a small sales warehouse by hand between June
and September 2026: dbt models on top of the ERP, T-SQL procedures for the daily tables, a report, a Spark notebook
for shelf stock and a marketing export. In October two briefs arrived for what comes next. Everything here is
fictional.
"""

VESNA = ("Vesna Lipovac", "vesna.lipovac@example.com")
MARKO = ("Marko Javor", "marko.javor@example.com")

COMMITS = [
    {
        "date": "2026-06-09T09:40:00+02:00",
        "author": VESNA,
        "message": "Start the warehouse: ERP sources, staging for orders and order lines",
        "add": [
            "README.md",
            "dbt_project.yml",
            ".gitignore",
            "models/staging/schema.yml",
            "models/staging/stg_orders.sql",
            "models/staging/stg_order_lines.sql",
        ],
    },
    {
        "date": "2026-06-18T14:05:00+02:00",
        "author": VESNA,
        "message": "Staging for customers, products and stores",
        "add": [
            "models/staging/stg_customers.sql",
            "models/staging/stg_products.sql",
            "models/staging/stg_stores.sql",
        ],
        "edit": [
            (
                "models/staging/schema.yml",
                "      - name: order_lines\n",
                "      - name: order_lines\n      - name: customers\n      - name: products\n      - name: stores\n",
            ),
            (
                "models/staging/schema.yml",
                "",
                "  - name: stg_customers\n"
                "    columns:\n"
                "      - name: customer_id\n"
                "        tests:\n"
                "          - not_null\n"
                "  - name: stg_products\n"
                "    columns:\n"
                "      - name: product_id\n"
                "        tests:\n"
                "          - unique\n"
                "          - not_null\n"
                "  - name: stg_stores\n"
                "    columns:\n"
                "      - name: store_id\n"
                "        tests:\n"
                "          - unique\n"
                "          - not_null\n",
            ),
        ],
    },
    {
        "date": "2026-06-30T11:20:00+02:00",
        "author": MARKO,
        "message": "Intermediate order lines, the sales fact and the dimensions",
        "add": [
            "models/intermediate/int_order_lines.sql",
            "models/marts/schema.yml",
            "models/marts/fct_sales.sql",
            "models/marts/dim_customer.sql",
            "models/marts/dim_product.sql",
            "models/marts/dim_store.sql",
        ],
        "edit": [
            (
                "README.md",
                "",
                "- `models/intermediate/`: order lines joined to their orders.\n"
                "- `models/marts/`: the sales fact and the customer, product and store dimensions, schema `marts`.\n",
            ),
        ],
    },
    {
        "date": "2026-07-09T16:45:00+02:00",
        "author": MARKO,
        "message": "Daily sales table and the procedure that loads it",
        "add": ["warehouse/ddl/fct_daily_sales.sql", "warehouse/procs/load_daily_sales.sql"],
        "edit": [
            (
                "README.md",
                "",
                "- `warehouse/ddl/` and `warehouse/procs/`: T-SQL tables and procedures in schema `dw`.\n",
            ),
            ("README.md", "1. `dbt run`\n", "1. `dbt run`\n2. `dw.load_daily_sales` with yesterday's date\n"),
        ],
    },
    {
        "date": "2026-07-23T10:15:00+02:00",
        "author": VESNA,
        "message": "Keep the product list in the warehouse in step with the ERP",
        "add": ["warehouse/ddl/dim_product.sql", "warehouse/procs/merge_dim_product.sql"],
        "edit": [
            (
                "README.md",
                "2. `dw.load_daily_sales` with yesterday's date\n",
                "2. `dw.merge_dim_product`\n3. `dw.load_daily_sales` with yesterday's date\n",
            ),
        ],
    },
    {
        "date": "2026-08-06T13:30:00+02:00",
        "author": MARKO,
        "message": "Promotions: staging model and the discount on the sales fact",
        "add": ["models/staging/stg_promotions.sql"],
        "edit": [
            (
                "models/staging/schema.yml",
                "      - name: stores\n",
                "      - name: stores\n      - name: promotions\n",
            ),
            (
                "models/staging/schema.yml",
                "",
                "  - name: stg_promotions\n"
                "    columns:\n"
                "      - name: promotion_id\n"
                "        tests:\n"
                "          - unique\n"
                "          - not_null\n"
                "      - name: product_id\n"
                "        tests:\n"
                "          - not_null\n",
            ),
            (
                "models/marts/fct_sales.sql",
                "        l.quantity * l.unit_price as net_amount,\n        l.quantity * p.list_price as list_amount\n",
                "        l.quantity * l.unit_price * (1 - coalesce(promo.discount_pct, 0) / 100.0) as net_amount,\n"
                "        l.quantity * p.list_price as list_amount,\n"
                "        promo.promotion_id,\n"
                "        coalesce(promo.discount_pct, 0) as discount_pct\n",
            ),
            (
                "models/marts/fct_sales.sql",
                "    left join products as p on p.product_id = l.product_id\n",
                "    left join products as p on p.product_id = l.product_id\n"
                "    left join {{ ref('stg_promotions') }} as promo on l.product_id = promo.product_id\n",
            ),
        ],
    },
    {
        "date": "2026-08-20T09:10:00+02:00",
        "author": VESNA,
        "message": "Store performance report for the regional managers, campaign mart for the summer review",
        "add": ["reports/store_performance.sql", "models/marts/mart_old_campaigns.sql"],
        "edit": [
            ("README.md", "", "- `reports/`: the store performance report for the regional managers.\n"),
        ],
    },
    {
        "date": "2026-09-10T15:50:00+02:00",
        "author": MARKO,
        "message": "Stock snapshot notebook on the Spark cluster",
        "add": ["notebooks/stock_snapshot.ipynb"],
        "edit": [
            ("README.md", "", "- `notebooks/`: the Spark notebook that writes the stock snapshot.\n"),
            (
                "README.md",
                "3. `dw.load_daily_sales` with yesterday's date\n",
                "3. `dw.load_daily_sales` with yesterday's date\n"
                "\n"
                "The stock snapshot notebook runs as its own Spark job at 06:00.\n",
            ),
        ],
    },
    {
        "date": "2026-09-24T11:05:00+02:00",
        "author": VESNA,
        "message": "Marketing contacts export and the regional export procedure",
        "add": ["exports/marketing_contacts.sql", "warehouse/procs/export_by_region.sql"],
        "edit": [
            ("README.md", "", "- `exports/`: the contact list for the marketing mailing.\n"),
            ("README.md", " at 06:00.\n", " at 06:00. `dw.export_by_region` runs on request.\n"),
        ],
    },
    {
        "date": "2026-10-20T10:00:00+02:00",
        "author": VESNA,
        "message": "Briefs: reporting for Acme Bakery and the next Acme Foods platform",
        "add": ["docs/briefs/reports-only.md", "docs/briefs/new-platform.md"],
        "edit": [
            ("README.md", "", "- `docs/briefs/`: briefs for what comes next.\n"),
        ],
    },
]
