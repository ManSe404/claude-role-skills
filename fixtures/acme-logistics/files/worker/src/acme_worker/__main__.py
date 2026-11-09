"""Start the worker: the /track endpoint and the consumer of booked shipments."""

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from acme_worker.tracking import consume_booked_shipments, track_shipment

PORT = 8081


class TrackHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        if self.path != "/track":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(length) or b"{}")
        answer = json.dumps(track_shipment(request["shipmentId"])).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(answer)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    threading.Thread(target=consume_booked_shipments, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", PORT), TrackHandler).serve_forever()


if __name__ == "__main__":
    main()
