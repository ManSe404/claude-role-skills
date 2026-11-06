"""The git history of the acme-orders fixture.

The files under files/ are the state after the last commit. Each commit lists the files it adds
and the edits it makes, as (path, before, after). The builder walks the list backwards, undoing
each edit, to recover the state after every commit, then replays it forwards with git.

The story: the importer used to accept decimal commas ("12,50"). On 2026-09-30 a commit
"simplified" amount parsing and dropped the test that covered commas. The import of 2026-10-02
then failed on an order from the Croatian store. The report's adjustments parser has the same
weakness. Everything here is fictional.
"""

MIA = ("Mia Novak", "mia.novak@example.com")
JON = ("Jon Berg", "jon.berg@example.com")

COMMITS = [
    {
        "date": "2026-05-04T10:12:00+02:00",
        "author": MIA,
        "message": "Initial importer, pricing and storage",
        "add": [
            "README.md",
            "pyproject.toml",
            ".gitignore",
            "src/acme_orders/__init__.py",
            "src/acme_orders/__main__.py",
            "src/acme_orders/cli.py",
            "src/acme_orders/config.py",
            "src/acme_orders/importer.py",
            "src/acme_orders/pricing.py",
            "src/acme_orders/storage.py",
            "tests/test_pricing.py",
            "tests/test_importer.py",
        ],
    },
    {
        "date": "2026-05-12T15:40:00+02:00",
        "author": MIA,
        "message": "Add CI and a Dockerfile",
        "add": [".github/workflows/ci.yml", "Dockerfile"],
    },
    {
        "date": "2026-05-20T11:03:00+02:00",
        "author": JON,
        "message": "Add read-only HTTP API",
        "add": ["src/acme_orders/server.py", "docs/api.md"],
        "edit": [
            (
                "src/acme_orders/cli.py",
                "from acme_orders import importer, pricing, storage\n",
                "from acme_orders import importer, pricing, server, storage\n",
            ),
            (
                "src/acme_orders/cli.py",
                "",
                '    srv = sub.add_parser("serve", help="serve the read-only API")\n'
                '    srv.add_argument("--port", type=int, default=8080)\n',
            ),
            (
                "src/acme_orders/cli.py",
                "",
                '    elif args.command == "serve":\n        server.serve(args.port, settings.db_path)\n',
            ),
        ],
    },
    {
        "date": "2026-06-02T09:25:00+02:00",
        "author": MIA,
        "message": "pricing: discount codes",
        "edit": [
            (
                "src/acme_orders/pricing.py",
                'CENT = Decimal("0.01")\n\n\n',
                'CENT = Decimal("0.01")\n\nDISCOUNTS = {\n    "WELCOME10": Decimal("0.10"),\n}\n\n\n',
            ),
            (
                "src/acme_orders/pricing.py",
                "",
                "def discount_total(order):\n"
                '    rate = DISCOUNTS.get((order.discount_code or "").upper(), Decimal("0"))\n'
                "    return subtotal(order) * rate\n\n\n",
            ),
            (
                "src/acme_orders/pricing.py",
                "    return _round(subtotal(order) * VAT_RATE)",
                "    return _round((subtotal(order) - discount_total(order)) * VAT_RATE)",
            ),
            (
                "src/acme_orders/pricing.py",
                "    return subtotal(order) + vat_total(order)",
                "    return subtotal(order) - discount_total(order) + vat_total(order)",
            ),
            (
                "tests/test_pricing.py",
                "",
                "\n    def test_welcome_discount_before_vat(self):\n"
                '        o = order(Line("TEA-01", 2, Decimal("5.00")), code="WELCOME10")\n'
                '        self.assertEqual(pricing.order_total(o), Decimal("10.80"))\n\n'
                "    def test_unknown_code_gives_no_discount(self):\n"
                '        o = order(Line("TEA-01", 1, Decimal("10.00")), code="NOPE")\n'
                '        self.assertEqual(pricing.order_total(o), Decimal("12.00"))\n',
            ),
        ],
    },
    {
        "date": "2026-06-15T14:02:00+02:00",
        "author": JON,
        "message": "Add daily report for finance",
        "add": ["src/acme_orders/report.py"],
        "edit": [
            ("pyproject.toml", '    "python-dateutil",\n', '    "python-dateutil",\n    "Jinja2>=2.10,<3",\n'),
            ("src/acme_orders/cli.py", "import argparse\n", "import argparse\nimport sys\n"),
            (
                "src/acme_orders/cli.py",
                "from acme_orders import importer, pricing, server, storage\n",
                "from acme_orders import importer, pricing, report, server, storage\n",
            ),
            (
                "src/acme_orders/cli.py",
                "",
                '    rep = sub.add_parser("report", help="daily totals report as HTML")\n'
                '    rep.add_argument("file")\n'
                '    rep.add_argument("--day", required=True)\n',
            ),
            (
                "src/acme_orders/cli.py",
                "",
                '    elif args.command == "report":\n'
                "        orders = importer.read_orders(args.file)\n"
                "        sys.stdout.write(report.daily_report(orders, args.day))\n",
            ),
        ],
    },
    {
        "date": "2026-07-01T10:48:00+02:00",
        "author": JON,
        "message": "notify: send receipts through the mail API",
        "add": ["src/acme_orders/notify.py"],
        "edit": [
            ("pyproject.toml", '    "Jinja2>=2.10,<3",\n', '    "Jinja2>=2.10,<3",\n    "requests==2.19.1",\n'),
            (
                "src/acme_orders/cli.py",
                "from acme_orders import importer, pricing, report, server, storage\n",
                "from acme_orders import importer, notify, pricing, report, server, storage\n",
            ),
            (
                "src/acme_orders/cli.py",
                '    imp.add_argument("file")\n',
                '    imp.add_argument("file")\n'
                '    imp.add_argument("--notify", action="store_true", help="send receipts")\n',
            ),
            (
                "src/acme_orders/cli.py",
                "",
                "        if args.notify:\n"
                "            for order in importer.read_orders(args.file):\n"
                "                notify.send_receipt(order, pricing.order_total(order))\n",
            ),
        ],
    },
    {
        "date": "2026-07-20T16:15:00+02:00",
        "author": MIA,
        "message": "config: optional acme.yaml",
        "add": ["acme.yaml.example"],
        "edit": [
            ("pyproject.toml", '    "requests==2.19.1",\n', '    "requests==2.19.1",\n    "PyYAML==5.3.1",\n'),
            (
                "src/acme_orders/config.py",
                "    values = {}\n    return Settings(",
                "    values = {}\n"
                "    if Path(path).exists():\n"
                "        import yaml\n\n"
                "        with open(path) as fh:\n"
                "            values = yaml.load(fh, Loader=yaml.FullLoader) or {}\n"
                "    return Settings(",
            ),
        ],
    },
    {
        "date": "2026-08-05T09:57:00+02:00",
        "author": MIA,
        "message": "pricing: round once per order, not per line",
        "edit": [
            ("src/acme_orders/pricing.py", "rounded to the cent.", "rounded once per order."),
            (
                "src/acme_orders/pricing.py",
                "    return _round((subtotal(order) - discount_total(order)) * VAT_RATE)",
                "    return (subtotal(order) - discount_total(order)) * VAT_RATE",
            ),
            (
                "src/acme_orders/pricing.py",
                "    return subtotal(order) - discount_total(order) + vat_total(order)",
                "    return _round(subtotal(order) - discount_total(order) + vat_total(order))",
            ),
            (
                "tests/test_pricing.py",
                "",
                "\n    def test_rounds_once_per_order(self):\n"
                '        o = order(Line("MUG-02", 3, Decimal("3.33")))\n'
                '        self.assertEqual(pricing.order_total(o), Decimal("11.99"))\n',
            ),
        ],
    },
    {
        "date": "2026-08-25T13:30:00+02:00",
        "author": JON,
        "message": "importer: accept discount codes in lower case",
        "edit": [
            (
                "src/acme_orders/importer.py",
                '(row.get("discount_code") or "").strip() or None',
                '(row.get("discount_code") or "").strip().upper() or None',
            ),
            ("tests/test_importer.py", "", '        self.assertEqual(orders[0].discount_code, "WELCOME10")\n'),
        ],
    },
    {
        "date": "2026-09-10T11:11:00+02:00",
        "author": MIA,
        "message": "pricing: STAFF25 code for staff orders",
        "edit": [
            (
                "src/acme_orders/pricing.py",
                '    "WELCOME10": Decimal("0.10"),\n}',
                '    "WELCOME10": Decimal("0.10"),\n    "STAFF25": Decimal("0.25"),\n}',
            ),
        ],
    },
    {
        "date": "2026-09-30T17:42:00+02:00",
        "author": JON,
        "message": "importer: simplify amount parsing",
        "edit": [
            (
                "src/acme_orders/importer.py",
                '    return Decimal(value.strip().replace(",", "."))',
                "    return Decimal(value.strip())",
            ),
            (
                "tests/test_importer.py",
                '        self.assertEqual(importer.parse_amount(" 3.00 "), Decimal("3.00"))\n\n'
                "    def test_decimal_comma(self):\n"
                '        self.assertEqual(importer.parse_amount("12,50"), Decimal("12.50"))\n',
                '        self.assertEqual(importer.parse_amount(" 3.00 "), Decimal("3.00"))\n',
            ),
        ],
    },
    {
        "date": "2026-10-01T09:05:00+02:00",
        "author": JON,
        "message": "report: add the manual adjustments file",
        "edit": [
            ("src/acme_orders/report.py", "from decimal import Decimal\n", "import csv\nfrom decimal import Decimal\n"),
            (
                "src/acme_orders/report.py",
                "{% endfor %}</table>\n",
                "{% endfor %}</table>\n<p>Adjustments: {{ adjustments }}</p>\n",
            ),
            (
                "src/acme_orders/report.py",
                "",
                "def read_adjustments(path):\n"
                '    total = Decimal("0")\n'
                '    with open(path, newline="", encoding="utf-8") as fh:\n'
                '        for row in csv.DictReader(fh, delimiter=";"):\n'
                '            total += Decimal(row["amount"].strip())\n'
                "    return total\n\n\n",
            ),
            (
                "src/acme_orders/report.py",
                'def daily_report(orders, day, note=""):',
                'def daily_report(orders, day, adjustments_path=None, note=""):',
            ),
            (
                "src/acme_orders/report.py",
                "    return Template(TEMPLATE).render(day=day, rows=rows, note=note)",
                '    adjustments = read_adjustments(adjustments_path) if adjustments_path else Decimal("0")\n'
                "    return Template(TEMPLATE).render(day=day, rows=rows, adjustments=adjustments, note=note)",
            ),
            (
                "src/acme_orders/cli.py",
                '    rep.add_argument("--day", required=True)\n',
                '    rep.add_argument("--day", required=True)\n    rep.add_argument("--adjustments")\n',
            ),
            (
                "src/acme_orders/cli.py",
                "report.daily_report(orders, args.day)",
                "report.daily_report(orders, args.day, args.adjustments)",
            ),
        ],
    },
    {
        "date": "2026-10-03T08:20:00+02:00",
        "author": MIA,
        "message": "docs: how finance reads the totals",
        "add": ["docs/finance-export.md"],
    },
]
