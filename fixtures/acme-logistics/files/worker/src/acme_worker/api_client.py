"""Calls from the worker back to the API."""

import requests


def report_tracking(shipment_id: str, status: str, location: str) -> None:
    response = requests.post(
        f"http://api:8080/api/shipments/{shipment_id}/tracking",
        json={"status": status, "location": location},
        timeout=5,
    )
    response.raise_for_status()
