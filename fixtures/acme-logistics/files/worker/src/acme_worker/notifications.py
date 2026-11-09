"""Tell the customer that a parcel has arrived."""

import os

import requests

NOTIFY_URL = os.environ.get("ACME_NOTIFY_URL", "https://notify.example.com/v1/messages")


def send_delivery_notice(shipment_id: str) -> None:
    body = {"shipmentId": shipment_id, "template": "parcel-delivered"}
    response = requests.post(NOTIFY_URL, json=body, timeout=5)
    response.raise_for_status()
