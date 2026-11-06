"""Settings from the environment and an optional acme.yaml."""

import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    db_path: str
    mail_api_url: str
    mail_api_key: str
    vat_rate: Decimal


def load_settings(path="acme.yaml"):
    values = {}
    if Path(path).exists():
        import yaml

        with open(path) as fh:
            values = yaml.load(fh, Loader=yaml.FullLoader) or {}
    return Settings(
        db_path=os.environ.get("ACME_DB_PATH", values.get("db_path", "acme.db")),
        mail_api_url=os.environ.get("ACME_MAIL_API_URL", values.get("mail_api_url", "")),
        mail_api_key=os.environ.get("ACME_MAIL_API_KEY", ""),
        vat_rate=Decimal(os.environ.get("ACME_VAT_RATE", str(values.get("vat_rate", "0.20")))),
    )
