# Orders API

Read-only. The shop's admin panel calls it to show one order.

## GET /orders/<order_id>

    {"order_id": "A-1041", "customer_email": "mia.k@example.com",
     "created_at": "2026-10-01T08:12:00+02:00", "discount_code": null, "total": 20.4,
     "lines": [{"sku": "TEA-01", "quantity": 2, "unit_price": "4.50"}]}

`total` is the order total with VAT, in euros.

## GET /health

    {"status": "ok"}
