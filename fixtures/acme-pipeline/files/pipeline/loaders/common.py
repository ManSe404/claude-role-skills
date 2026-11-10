"""Shared code of the loaders: the source registry, reading a delivery, writing bronze rows."""

from __future__ import annotations

import csv
from pathlib import Path

from pipeline import warehouse
from pipeline.config import settings

REGISTRY = Path(__file__).resolve().parent.parent / "config" / "sources.yaml"


def registered_sources() -> dict[str, dict[str, str]]:
    """The sources of pipeline/config/sources.yaml as {name: {key: value}}."""
    sources: dict[str, dict[str, str]] = {}
    current = ""
    for raw in REGISTRY.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip() or line == "sources:":
            continue
        if not line.startswith("    "):
            current = line.strip().removesuffix(":")
            sources[current] = {}
        else:
            key, _, value = line.strip().partition(":")
            sources[current][key] = value.strip()
    return sources


def require_contract(source: str) -> Path:
    """The contract of a source. A source without a registered contract is not loaded."""
    entry = registered_sources().get(source, {})
    if not entry.get("contract"):
        raise SystemExit(f"source {source} has no contract registered in pipeline/config/sources.yaml")
    return Path(entry["contract"])


def read_delivery(source: str, day: str, name: str, delimiter: str = ",") -> list[dict[str, str]]:
    path = Path(settings.SOURCES_DIR) / source / day / name
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=delimiter))


def load_bronze(source: str, table: str, day: str, name: str, delimiter: str = ",") -> int:
    require_contract(source)
    rows = read_delivery(source, day, name, delimiter)
    warehouse.replace_partition(f"bronze.{table}", "load_date", day, rows)
    return len(rows)
