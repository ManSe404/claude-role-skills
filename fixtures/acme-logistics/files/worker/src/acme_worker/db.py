"""Database access of the worker."""

import os

import psycopg


def set_shipment_status(shipment_id: str, status: str) -> None:
    with psycopg.connect(os.environ["ACME_DATABASE_URL"], connect_timeout=5) as connection:
        connection.execute(
            "UPDATE shipments SET status = %s WHERE id = %s",
            (status, shipment_id),
        )
