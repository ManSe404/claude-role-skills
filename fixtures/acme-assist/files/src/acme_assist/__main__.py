"""Command line: index the knowledge folder or the stock export, or serve the chat API."""

import argparse
import logging


def main() -> None:
    parser = argparse.ArgumentParser(prog="acme_assist")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("index", help="index the knowledge folder into Qdrant")
    sub.add_parser("index-stock", help="index the nightly stock export into Qdrant")
    serve = sub.add_parser("serve", help="run the chat API")
    serve.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    if args.command == "index":
        from acme_assist import knowledge

        print(f"indexed {knowledge.index_folder()} chunks")
    elif args.command == "index-stock":
        from acme_assist import stock

        print(f"indexed {stock.index_stock()} stock rows")
    elif args.command == "serve":
        import uvicorn

        uvicorn.run("acme_assist.app:app", host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    main()
