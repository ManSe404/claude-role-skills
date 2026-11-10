#!/usr/bin/env python3
"""Price a bill of materials against a provider's list prices.

Usage: python3 cloud_prices.py BOM.json --prices TABLE.json [--prices OTHER.json]
       python3 cloud_prices.py BOM.json --online [--timeout 20] [--max-file-mb 64] [--max-download-seconds 120]

A bill of materials is {"cloud": "azure", "region": "westeurope", "currency": "USD", "items": [...]}. An item is
{"id", "label", "cloud", "variant", "service", "product", "sku", "meter", "region", "unit", "quantity"}: `quantity` is
how many of the price's own unit a month (730 for an hourly meter, a number of GB for storage). `variant` groups items
of one option or cloud. Only `id`, `service` and `quantity` are required; the more of the rest, the fewer ambiguous
matches.

--prices reads a saved, dated table: {"cloud", "as_of", "currency", "source", "rows": [{service, product, sku, meter,
region, unit, unit_price, tier_min, currency, effective_from}]} or a list of such tables; --prices can be given once per
table, so one bill can be priced against two clouds. --online asks the provider's public price list instead
(cloud/<provider>.json says how), with a timeout on every call. A provider that publishes whole price files has them
streamed to a temporary file under a size ceiling: a file too large or too slow is reported, not guessed at.

Output: each item with its price, date and source, or the reason it could not be priced, and a total per cloud and
variant. An item that matches several prices is not priced: it says which, so the bill can be made exact.
Read-only, standard library only, JSON on stdout. Prices move: every row carries its date and source.
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path
from typing import IO, Any

UA = "claude-role-skills cloud_prices (https://github.com/ManSe404/claude-role-skills)"
MAX_PAGES = 5
MAX_FILE_MB = 64
MAX_DOWNLOAD_SECONDS = 120.0
MATCH_FIELDS = ("service", "product", "sku", "meter", "region")
DISPLAY_FIELDS = ("service", "product", "sku", "meter", "region", "unit", "unit_price", "tier_min")


def _unit_key(unit: Any) -> str:
    return re.sub(r"[\s/]+", "", str(unit)).lower()


def _provider_tables() -> dict[str, dict[str, Any]]:
    here = Path(__file__).resolve().parent
    tables: dict[str, dict[str, Any]] = {}
    for directory in (here / "cloud", here.parent / "references" / "cloud"):
        if directory.is_dir():
            for path in sorted(directory.glob("*.json")):
                table = json.loads(path.read_text(encoding="utf-8"))
                tables[table["provider"]] = table.get("prices", {})
    return tables


def _fetch_json(url: str, timeout: float) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


class PriceFileRefused(RuntimeError):
    """A published price file was not read. The message says why and what to do instead."""

    status = "not_priced"


class PriceFileTooLarge(PriceFileRefused):
    status = "too_large"


class PriceFileTooSlow(PriceFileRefused):
    status = "too_slow"


class PriceFileMissing(PriceFileRefused):
    status = "not_found"


def download_file(url: str, dest: Path, timeout: float, max_bytes: int, max_seconds: float) -> int:
    """Stream a price file to disk. `timeout` covers each read; the ceilings cover the whole transfer, because a socket
    timeout alone never fires on a slow but steady download."""
    deadline = time.monotonic() + max_seconds
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        declared = response.headers.get("Content-Length")
        if declared and int(declared) > max_bytes:
            raise PriceFileTooLarge(
                f"{int(declared) / 1_000_000:.0f} MB, over the limit of {max_bytes // 1_000_000} MB"
            )
        total = 0
        with dest.open("wb") as handle:
            while chunk := response.read(1 << 20):
                total += len(chunk)
                if total > max_bytes:
                    raise PriceFileTooLarge(f"over the limit of {max_bytes // 1_000_000} MB")
                if time.monotonic() > deadline:
                    raise PriceFileTooSlow(f"not finished after {max_seconds:.0f} seconds")
                handle.write(chunk)
    return total


class JsonStream:
    """Walks a JSON file one object member at a time, so a very large file costs little memory. The buffer holds only
    the piece being read; a member the caller does not want is skipped without being kept."""

    CHUNK = 1 << 20

    def __init__(self, handle: IO[str]) -> None:
        self.handle = handle
        self.buffer = ""
        self.pos = 0
        self.eof = False
        self.decoder = json.JSONDecoder()

    def _fill(self) -> None:
        chunk = self.handle.read(self.CHUNK)
        if chunk:
            self.buffer = self.buffer[self.pos :] + chunk
            self.pos = 0
        else:
            self.eof = True

    def peek(self) -> str:
        while True:
            while self.pos < len(self.buffer) and self.buffer[self.pos] in " \t\r\n":
                self.pos += 1
            if self.pos < len(self.buffer):
                return self.buffer[self.pos]
            if self.eof:
                return ""
            self._fill()

    def _expect(self, char: str) -> None:
        found = self.peek()
        if found != char:
            raise ValueError(f"expected {char!r} in the price file, found {found!r}")
        self.pos += 1

    def value(self) -> Any:
        """One whole value. Only for values known to be small: a number cut by the buffer's end is read again."""
        self.peek()
        while True:
            try:
                value, end = self.decoder.raw_decode(self.buffer, self.pos)
            except json.JSONDecodeError:
                if self.eof:
                    raise
                self._fill()
                continue
            if end == len(self.buffer) and not self.eof:
                self._fill()
                continue
            self.pos = end
            return value

    def members(self) -> Iterator[str]:
        """The keys of the object here. After each key the caller reads or skips that key's value."""
        self._expect("{")
        while self.peek() != "}":
            key = self.value()
            self._expect(":")
            yield key
            if self.peek() == ",":
                self.pos += 1
        self.pos += 1

    def skip(self) -> None:
        kind = self.peek()
        if kind == "{":
            for _ in self.members():
                self.skip()
        elif kind == "[":
            self.pos += 1
            while self.peek() != "]":
                self.skip()
                if self.peek() == ",":
                    self.pos += 1
            self.pos += 1
        else:
            self.value()


def bulk_row(product: dict[str, Any], service: str, region: str, spec: dict[str, Any]) -> dict[str, Any]:
    """A product of a published price file, in the saved-table shape, without the price yet."""
    attributes = product.get("attributes", {})
    names = spec.get("sku_attrs", {}).get(service, spec.get("sku_default", []))
    values = [str(attributes[name]) for name in names if attributes.get(name)]
    meter = re.sub(spec["meter_strip"], "", str(attributes.get(spec["meter_attr"], "")))
    return {
        "service": service,
        "product": product.get(spec["product_field"]),
        "sku": " / ".join(values),
        "meter": meter,
        "region": region,
    }


def read_bulk_file(
    path: Path, service: str, region: str, items: list[dict[str, Any]], spec: dict[str, Any], currency: str
) -> list[dict[str, Any]]:
    """The rows of a published price file that can serve any of these items. Everything else is dropped as it streams
    past, so memory follows the bill and not the file."""
    wanted = [{f: item.get(f) for f in ("product", "sku", "meter")} for item in items]
    kept: dict[str, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        stream = JsonStream(handle)
        for key in stream.members():
            if key == spec["products_key"]:
                for code in stream.members():
                    row = bulk_row(stream.value(), service, region, spec)
                    if any(_row_fits(row, want) for want in wanted):
                        kept[code] = row
            elif key == spec["terms_key"]:
                for kind in stream.members():
                    if kind != spec["term_kind"]:
                        stream.skip()
                        continue
                    for code in stream.members():
                        term = stream.value()
                        if code in kept:
                            rows += _bulk_prices(term, kept[code], currency)
            else:
                stream.skip()
    return rows


def _row_fits(row: dict[str, Any], want: dict[str, Any]) -> bool:
    return all(not value or str(row.get(field, "")).lower() == str(value).lower() for field, value in want.items())


def _bulk_prices(term: dict[str, Any], base: dict[str, Any], currency: str) -> list[dict[str, Any]]:
    rows = []
    for offer in term.values():
        for dimension in offer.get("priceDimensions", {}).values():
            price = dimension.get("pricePerUnit", {}).get(currency)
            if price is None:
                continue
            rows.append(
                {
                    **base,
                    "unit": dimension.get("unit"),
                    "unit_price": float(price),
                    "tier_min": float(dimension.get("beginRange") or 0),
                    "currency": currency,
                    "effective_from": offer.get("effectiveDate"),
                }
            )
    return rows


class BulkFiles:
    """Published price files for one bill: each file is fetched once, and read for every item that needs it."""

    def __init__(
        self,
        items: list[dict[str, Any]],
        specs: dict[str, dict[str, Any]],
        currency: str,
        timeout: float,
        max_file_mb: int,
        max_seconds: float,
    ) -> None:
        self.items = items
        self.specs = specs
        self.currency = currency
        self.timeout = timeout
        self.max_bytes = max_file_mb * 1_000_000
        self.max_seconds = max_seconds
        self.done: dict[tuple[str, str, str], list[dict[str, Any]] | PriceFileRefused] = {}

    def rows(self, item: dict[str, Any]) -> list[dict[str, Any]]:
        key = (item["cloud"], str(item["service"]), str(item.get("region", "")))
        if key not in self.done:
            self.done[key] = self._read(key)
        found = self.done[key]
        if isinstance(found, PriceFileRefused):
            raise found
        return found

    def _read(self, key: tuple[str, str, str]) -> list[dict[str, Any]] | PriceFileRefused:
        cloud, service, region = key
        spec = self.specs[cloud]
        url = spec["file_url"].format(service=urllib.parse.quote(service), region=urllib.parse.quote(region))
        label = f"the price file of {service} in {region}"
        way_out = "Save the rows you need in a table and give it with --prices TABLE.json"
        try:
            with tempfile.TemporaryDirectory(prefix="cloud-prices-") as directory:
                path = Path(directory) / "prices.json"
                try:
                    download_file(url, path, self.timeout, self.max_bytes, self.max_seconds)
                except PriceFileTooLarge as exc:
                    return PriceFileTooLarge(f"{label} is {exc}. {way_out}, or raise --max-file-mb.")
                except PriceFileTooSlow as exc:
                    return PriceFileTooSlow(f"{label} was {exc}. {way_out}, or raise --max-download-seconds.")
                except urllib.error.HTTPError as exc:
                    if exc.code in (403, 404):
                        return PriceFileMissing(
                            f"{label} does not exist ({exc.code}). Check the service code in {spec['index_url']} "
                            "and the region name."
                        )
                    raise
                items = [i for i in self.items if (i["cloud"], str(i["service"]), str(i.get("region", ""))) == key]
                return read_bulk_file(path, service, region, items, spec, self.currency)
        except TimeoutError as exc:
            return PriceFileTooSlow(f"{label} timed out ({exc}). {way_out}, or raise --timeout.")


def _odata_filter(item: dict[str, Any], spec: dict[str, Any]) -> str:
    clauses = list(spec.get("fixed_filters", []))
    for field, name in spec.get("filter_fields", {}).items():
        value = item.get(field)
        if value:
            clauses.append(f"{name} eq '{str(value).replace(chr(39), chr(39) * 2)}'")
    return " and ".join(clauses)


def fetch_rows(item: dict[str, Any], spec: dict[str, Any], currency: str, timeout: float) -> list[dict[str, Any]]:
    """The list-price rows that may match one item, in the saved-table shape, for a provider with a query API."""
    if spec.get("api") != "odata":
        raise RuntimeError(f"no fetcher for the price list shape {spec.get('api')!r}")
    params = {"$filter": _odata_filter(item, spec)}
    if currency and spec.get("currency_param"):
        params[spec["currency_param"]] = currency
    url: str | None = f"{spec['url']}?{urllib.parse.urlencode(params)}"
    rows: list[dict[str, Any]] = []
    pages = 0
    while url and pages < MAX_PAGES:
        payload = _fetch_json(url, timeout)
        for raw in payload.get(spec["items_key"], []):
            rows.append({k: raw.get(v) for k, v in spec["row"].items()})
        url = payload.get(spec["next_key"])
        pages += 1
    return rows


def _normal_row(row: dict[str, Any], as_of: str, source: str, currency: str) -> dict[str, Any]:
    effective = row.get("effective_from")
    return {
        **row,
        "tier_min": float(row.get("tier_min") or 0),
        "unit_price": float(row["unit_price"]),
        "currency": row.get("currency") or currency,
        "effective_from": str(effective)[:10] if effective else None,
        "as_of": as_of,
        "source": source,
    }


def _rows_for(item: dict[str, Any], table: list[dict[str, Any]]) -> list[dict[str, Any]]:
    found = []
    for row in table:
        if all(
            not item.get(field) or str(row.get(field, "")).lower() == str(item[field]).lower() for field in MATCH_FIELDS
        ):
            found.append(row)
    if item.get("unit"):
        wanted = _unit_key(item["unit"])
        narrowed = [row for row in found if _unit_key(row.get("unit")) == wanted]
        if narrowed:
            found = narrowed
    return found


def _candidates(rows: list[dict[str, Any]]) -> dict[tuple[str, str, str, str], list[dict[str, Any]]]:
    """Distinct prices. The price list repeats a row for each ARM SKU; a true difference in tier or price stays."""
    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    seen: set[tuple[Any, ...]] = set()
    for row in rows:
        key = (row.get("product", ""), row.get("sku", ""), row.get("meter", ""), _unit_key(row.get("unit")))
        fingerprint = (key, row["tier_min"], row["unit_price"])
        if fingerprint not in seen:
            seen.add(fingerprint)
            groups[key].append(row)
    return groups


def price_tiers(rows: list[dict[str, Any]], quantity: float) -> tuple[float, list[dict[str, Any]]]:
    """Graduated: the first units at the first tier's price, the next at the next tier's."""
    rows = sorted(rows, key=lambda r: r["tier_min"])
    total = 0.0
    used = []
    for index, row in enumerate(rows):
        lower = row["tier_min"]
        if quantity <= lower:
            break
        upper = rows[index + 1]["tier_min"] if index + 1 < len(rows) else float("inf")
        billed = min(quantity, upper) - lower
        total += billed * row["unit_price"]
        used.append({"from": lower, "units": round(billed, 6), "unit_price": row["unit_price"]})
    return round(total, 2), used


def _status_row(item: dict[str, Any], status: str, reason: str, cloud: str, **extra: Any) -> dict[str, Any]:
    return {
        "id": item["id"],
        "label": item.get("label", item["id"]),
        "cloud": cloud,
        "variant": item.get("variant", ""),
        "region": item.get("region"),
        "quantity": item["quantity"],
        "status": status,
        "reason": reason,
        "monthly": None,
        **extra,
    }


def price_item(item: dict[str, Any], rows: list[dict[str, Any]], cloud: str) -> dict[str, Any]:
    if not rows:
        return _status_row(item, "not_found", "no price list row matches this item", cloud)
    groups = _candidates(rows)
    if len(groups) > 1:
        names = [
            {"product": k[0], "sku": k[1], "meter": k[2], "unit": group[0].get("unit")} for k, group in groups.items()
        ]
        return _status_row(
            item,
            "ambiguous",
            "several price list rows match; set product, sku, meter or unit to pick one",
            cloud,
            candidates=names[:12],
        )
    group = next(iter(groups.values()))
    tiers = [row["tier_min"] for row in group]
    if len(tiers) != len(set(tiers)):
        # Two prices for the same units: the fields of this row do not tell the options apart. Never pick one.
        return _status_row(
            item, "ambiguous", "two prices for the same tier; this row needs a field that tells them apart", cloud
        )
    quantity = float(item["quantity"])
    wanted_unit = item.get("unit")
    price_unit = group[0].get("unit")
    if wanted_unit and _unit_key(wanted_unit) != _unit_key(price_unit):
        return _status_row(
            item,
            "unit_mismatch",
            f"the price is per {price_unit!r}, the bill says {wanted_unit!r}",
            cloud,
            price_unit=price_unit,
        )
    if quantity < 0:
        return _status_row(item, "bad_quantity", "quantity must not be negative", cloud)
    monthly, tiers = price_tiers(group, quantity)
    first = sorted(group, key=lambda r: r["tier_min"])[0]
    return {
        "id": item["id"],
        "label": item.get("label", item["id"]),
        "cloud": cloud,
        "variant": item.get("variant", ""),
        "region": first.get("region"),
        "service": first.get("service"),
        "product": first.get("product"),
        "sku": first.get("sku"),
        "meter": first.get("meter"),
        "unit": price_unit,
        "unit_price": first["unit_price"],
        "tiers": tiers if len(group) > 1 else [],
        "quantity": quantity,
        "monthly": monthly,
        "currency": first.get("currency"),
        "effective_from": first.get("effective_from"),
        "as_of": first.get("as_of"),
        "source": first.get("source"),
        "status": "priced",
    }


def check_bom(bom: Any) -> list[str]:
    if not isinstance(bom, dict) or not isinstance(bom.get("items"), list) or not bom["items"]:
        return ["the bill of materials needs an `items` list"]
    errs = []
    seen = set()
    for index, item in enumerate(bom["items"]):
        if not isinstance(item, dict):
            errs.append(f"items[{index}]: must be an object")
            continue
        for key in ("id", "service", "quantity"):
            if item.get(key) in (None, ""):
                errs.append(f"items[{index}]: {key} is required")
        if isinstance(item.get("quantity"), bool) or not isinstance(item.get("quantity", 0), int | float):
            errs.append(f"items[{index}].quantity: must be a number")
        if item.get("id") in seen:
            errs.append(f"items[{index}].id: duplicate id {item['id']!r}")
        seen.add(item.get("id"))
        if not item.get("cloud") and not bom.get("cloud"):
            errs.append(f"items[{index}]: needs a cloud (or set `cloud` on the bill)")
    return errs


def load_tables(paths: list[Path]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path in paths:
        doc = json.loads(path.read_text(encoding="utf-8"))
        for table in doc if isinstance(doc, list) else [doc]:
            for key in ("cloud", "as_of", "source", "rows"):
                if key not in table:
                    raise SystemExit(f"{path}: a saved price table needs `{key}`")
            for row in table["rows"]:
                out[table["cloud"]].append(_normal_row(row, table["as_of"], table["source"], table.get("currency", "")))
    return out


def run(
    bom: dict[str, Any],
    prices: Path | list[Path] | None,
    online: bool,
    timeout: float,
    max_file_mb: int = MAX_FILE_MB,
    max_seconds: float = MAX_DOWNLOAD_SECONDS,
) -> dict[str, Any]:
    defaults = {k: bom[k] for k in ("region", "cloud") if bom.get(k)}
    currency = str(bom.get("currency", "USD"))
    today = datetime.date.today().isoformat()
    paths = [prices] if isinstance(prices, Path) else (prices or [])
    tables = load_tables(paths)
    specs = _provider_tables() if online else {}
    items = [{**defaults, **raw_item} for raw_item in bom["items"]]
    bulk = BulkFiles(items, specs, currency, timeout, max_file_mb, max_seconds)
    results = []
    errors = []
    for item in items:
        cloud = item["cloud"]
        try:
            if online:
                spec = specs.get(cloud)
                if not spec:
                    results.append(_status_row(item, "not_found", f"no price list known for {cloud!r}", cloud))
                    continue
                fetched = (
                    bulk.rows(item) if spec.get("api") == "bulk_file" else fetch_rows(item, spec, currency, timeout)
                )
                rows = [_normal_row(r, today, spec["source"], currency) for r in fetched]
            else:
                rows = tables.get(cloud, [])
            results.append(price_item(item, _rows_for(item, rows), cloud))
        except PriceFileRefused as exc:
            errors.append({"id": item["id"], "error": str(exc)})
            results.append(_status_row(item, exc.status, str(exc), cloud))
        except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
            errors.append({"id": item["id"], "error": f"{type(exc).__name__}: {exc}"})
            results.append(_status_row(item, "error", f"the price list could not be read: {type(exc).__name__}", cloud))
    totals = _totals(results)
    return {
        "as_of": today if online else None,
        "mode": "online" if online else "saved table",
        "items": results,
        "totals": totals,
        "not_priced": [r["id"] for r in results if r["status"] != "priced"],
        "errors": errors,
        "note": "A total covers only priced items; `not_priced` lists the rest. List prices without discounts or "
        "reservations, in the given currency, before tax. Quantities are monthly: they are the estimate this bill "
        "stands on.",
    }


def _totals(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in results:
        groups[(row["cloud"], row["variant"])].append(row)
    out = []
    for (cloud, variant), rows in sorted(groups.items()):
        priced = [r for r in rows if r["status"] == "priced"]
        currencies = sorted({r["currency"] for r in priced if r.get("currency")})
        out.append(
            {
                "cloud": cloud,
                "variant": variant,
                "monthly": round(sum(r["monthly"] for r in priced), 2) if len(currencies) <= 1 else None,
                "currency": currencies[0] if len(currencies) == 1 else None,
                "currencies": currencies if len(currencies) > 1 else [],
                "items_priced": len(priced),
                "items_not_priced": len(rows) - len(priced),
                "as_of": sorted({str(r["as_of"]) for r in priced}),
                "source": sorted({str(r["source"]) for r in priced}),
            }
        )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Price a bill of materials against a provider's list prices.")
    parser.add_argument("bom", help="a bill of materials JSON file, or - for stdin")
    parser.add_argument("--prices", type=Path, action="append", help="a saved, dated price table; can be repeated")
    parser.add_argument("--online", action="store_true", help="ask the provider's public price list")
    parser.add_argument("--timeout", type=float, default=20.0, help="seconds per request or read (default 20)")
    parser.add_argument(
        "--max-file-mb", type=int, default=MAX_FILE_MB, help=f"largest price file to fetch (default {MAX_FILE_MB})"
    )
    parser.add_argument(
        "--max-download-seconds",
        type=float,
        default=MAX_DOWNLOAD_SECONDS,
        help=f"longest one price file may take (default {MAX_DOWNLOAD_SECONDS:.0f})",
    )
    args = parser.parse_args(argv)
    if bool(args.prices) == bool(args.online):
        parser.error("give either --prices FILE or --online")
    try:
        text = sys.stdin.read() if args.bom == "-" else Path(args.bom).read_text(encoding="utf-8")
        bom = json.loads(text)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"cannot read the input: {exc}", file=sys.stderr)
        return 2
    problems = check_bom(bom)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    for path in args.prices or []:
        if not path.is_file():
            print(f"not a file: {path}", file=sys.stderr)
            return 2
    result = run(bom, args.prices, args.online, args.timeout, args.max_file_mb, args.max_download_seconds)
    json.dump(result, sys.stdout, indent=1, ensure_ascii=False)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
