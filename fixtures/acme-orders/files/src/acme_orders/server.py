"""Read-only HTTP API: GET /orders/<id> and GET /health."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from acme_orders import storage


class Handler(BaseHTTPRequestHandler):
    db_path = "acme.db"

    def do_GET(self):
        if self.path == "/health":
            return self._send(200, {"status": "ok"})
        if self.path.startswith("/orders/"):
            db = storage.connect(self.db_path)
            try:
                order = storage.get_order(db, self.path.removeprefix("/orders/"))
            finally:
                db.close()
            if order is None:
                return self._send(404, {"error": "not found"})
            order["total"] = order.pop("total_cents") / 100
            return self._send(200, order)
        return self._send(404, {"error": "not found"})

    def _send(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def serve(port, db_path):
    Handler.db_path = db_path
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
