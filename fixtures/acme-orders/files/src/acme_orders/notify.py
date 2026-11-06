"""Sends the order receipt through the mail API."""

from acme_orders.config import load_settings


def send_receipt(order, total):
    import requests

    settings = load_settings()
    response = requests.post(
        settings.mail_api_url,
        json={"to": order.customer_email, "template": "receipt", "order_id": order.order_id, "total": str(total)},
        headers={"Authorization": f"Bearer {settings.mail_api_key}"},
    )
    response.raise_for_status()
