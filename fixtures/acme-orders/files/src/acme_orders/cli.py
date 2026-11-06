"""Command line: import, check, report, serve."""

import argparse
import sys

from acme_orders import importer, notify, pricing, report, server, storage
from acme_orders.config import load_settings


def main(argv=None):
    parser = argparse.ArgumentParser(prog="acme-orders")
    sub = parser.add_subparsers(dest="command", required=True)
    imp = sub.add_parser("import", help="import a daily order export")
    imp.add_argument("file")
    imp.add_argument("--notify", action="store_true", help="send receipts")
    chk = sub.add_parser("check", help="price an export without saving it")
    chk.add_argument("file")
    rep = sub.add_parser("report", help="daily totals report as HTML")
    rep.add_argument("file")
    rep.add_argument("--day", required=True)
    rep.add_argument("--adjustments")
    srv = sub.add_parser("serve", help="serve the read-only API")
    srv.add_argument("--port", type=int, default=8080)
    args = parser.parse_args(argv)
    settings = load_settings()

    if args.command == "import":
        db = storage.connect(settings.db_path)
        count = importer.import_file(args.file, db)
        if args.notify:
            for order in importer.read_orders(args.file):
                notify.send_receipt(order, pricing.order_total(order))
        print(f"imported {count} orders")
    elif args.command == "check":
        for order in importer.read_orders(args.file):
            print(order.order_id, pricing.order_total(order))
    elif args.command == "report":
        orders = importer.read_orders(args.file)
        sys.stdout.write(report.daily_report(orders, args.day, args.adjustments))
    elif args.command == "serve":
        server.serve(args.port, settings.db_path)
