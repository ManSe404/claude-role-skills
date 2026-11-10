"""Settings of the Acme Foods pipeline, read from environment variables."""

import os

WAREHOUSE_DSN = os.environ["WAREHOUSE_DSN"]
SOURCES_DIR = os.environ.get("ACME_SOURCES_DIR", "sources")
OPS_DIR = os.environ.get("ACME_OPS_DIR", "ops")
ALERT_EMAIL = os.environ.get("ACME_ALERT_EMAIL", "data-alerts@example.com")
