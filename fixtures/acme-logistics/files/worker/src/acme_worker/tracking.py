"""Ask the carrier where a parcel is and record the answer."""

import json
import logging
import os

import pika
import requests

from acme_worker.api_client import report_tracking
from acme_worker.db import set_shipment_status
from acme_worker.notifications import send_delivery_notice

CARRIER_URL = os.environ.get("ACME_CARRIER_URL", "https://carrier.example.com/v1/parcels")
log = logging.getLogger(__name__)


def track_shipment(shipment_id: str) -> dict[str, str]:
    response = requests.get(f"{CARRIER_URL}/{shipment_id}", timeout=10)
    response.raise_for_status()
    body = response.json()
    status, location = body["status"], body["location"]
    if status == "delivered":
        set_shipment_status(shipment_id, "Delivered")
        send_delivery_notice(shipment_id)
    report_tracking(shipment_id, status, location)
    return {"status": status, "location": location}


def consume_booked_shipments() -> None:
    connection = pika.BlockingConnection(pika.URLParameters(os.environ["ACME_QUEUE_URL"]))
    channel = connection.channel()
    channel.exchange_declare("acme.events", exchange_type="topic", durable=True)
    queue = channel.queue_declare("worker.booked", durable=True).method.queue
    channel.queue_bind(queue, "acme.events", routing_key="shipment.booked")

    def on_message(ch, method, properties, body) -> None:
        log.info("Now following shipment %s", json.loads(body)["id"])
        ch.basic_ack(method.delivery_tag)

    channel.basic_consume(queue, on_message)
    channel.start_consuming()
