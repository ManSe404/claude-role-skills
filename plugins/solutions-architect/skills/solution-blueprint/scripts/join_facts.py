#!/usr/bin/env python3
"""Join the `facts` of several specialist pages and list where they contradict each other.

Usage: python3 join_facts.py PATH [PATH ...] [--today YYYY-MM-DD] [--stale-days N] [--expect SKILL,SKILL]

PATH is a page JSON file or a folder of them (not searched below the first level). The output has the
pages read, the facts merged with their source page, the costs per currency, and the conflicts.

A conflict is a place to read, not a verdict: the script shows where two pages say different things and
Claude reads them and decides what is real. Costs are never added across currencies and never converted.
Read-only, standard library only, JSON on stdout.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Page JSON is untyped by nature: everything read from it is checked where it is used.
Json = dict[str, Any]

STALE_COST_DAYS = 90
# Without a brief page saying who had to run, these are the skills that decide something a join needs.
DECIDING_SKILLS = ("ai-pattern", "ai-stack", "data-platform", "arch-style", "cloud-design")
BRIEF_SKILL = "solution-brief"
# A blueprint written earlier is the join of the same pages: reading it would double everything.
OWN_SKILL = "solution-blueprint"

# Area names found in region names and data rules. Words, not a provider's region table, so a new cloud
# needs no change here. Short words match whole tokens only; long ones also inside a joined name ("westeurope").
REGION_AREAS: dict[str, tuple[str, ...]] = {
    "EU": (
        "eu",
        "eea",
        "europe",
        "european",
        "germany",
        "france",
        "sweden",
        "ireland",
        "netherlands",
        "italy",
        "spain",
        "poland",
        "austria",
        "belgium",
        "denmark",
        "finland",
        "frankfurt",
        "paris",
        "amsterdam",
        "stockholm",
        "milan",
        "dublin",
    ),
    "UK": ("uk", "britain", "london"),
    "CH": ("switzerland", "zurich"),
    "NO": ("norway", "oslo"),
    "US": ("us", "usa", "united states"),
    "CA": ("canada", "montreal", "toronto"),
    "APAC": ("ap", "apac", "asia", "india", "japan", "korea", "singapore", "australia", "tokyo", "sydney", "seoul"),
    "GLOBAL": ("global", "worldwide", "anywhere"),
}
JOINED_US = re.compile(r"^(?:east|west|north|south|central)+us\d*$")
JOINED_UK = re.compile(r"^uk(?:south|west)$")
SHORT_AREA = 3  # an area word this short matches a whole token only, and in a rule only in capitals
CONFINE = re.compile(r"\b(only|stays?|remains?|must be|kept|within|inside|leaves?|residency)\b", re.IGNORECASE)
REFUSE = re.compile(r"\b(not|never|no|forbidden|banned|without)\b", re.IGNORECASE)

PLACEHOLDER_TECH = ("", "not chosen", "not decided", "not stated", "unknown", "tbd", "none", "n/a", "open")
TECH_NOISE = {"a", "an", "the", "for", "on", "of", "with", "managed", "database", "service", "server"}
TECH_ALIASES = {"postgres": "postgresql"}
# Numbers about the same thing, compared only where a pattern can tell what the number counts.
ASSUMPTION_TOPICS: dict[str, re.Pattern[str]] = {
    "team_size": re.compile(
        r"\bteam (?:size )?(?:of |is )?(\d[\d,]*)\b|\b(\d[\d,]*) (?:engineers?|developers?|devs?)\b", re.I
    ),
    "users": re.compile(r"\b(\d[\d,]*)(?:\s*k|\s*thousand|\s*million)?\s+(?:\w+\s+)?users?\b", re.I),
    "requests_per_month": re.compile(r"\b(\d[\d,]*)\s+(?:requests?|calls?|queries)\s+(?:a|per)\s+month\b", re.I),
}
TOTAL_WORD = re.compile(r"\btotal\b", re.I)
VARIANT_WORD = re.compile(r"\b(variant|alternative|option)\b", re.I)
DATE_IN_NAME = re.compile(r"(\d{4}-\d{2}-\d{2})")


@dataclass
class Page:
    file: str
    path: str
    skill: str
    date: str
    facts: Json | None


def _str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _strings(value: Any) -> list[str]:
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


def _dicts(value: Any) -> list[Json]:
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def _list_files(paths: Iterable[Path]) -> Iterator[Path]:
    for path in paths:
        if path.is_dir():
            yield from sorted(path.glob("*.json"))
        elif path.is_file():
            yield path


def read_pages(paths: list[Path], expect: list[str] | None) -> tuple[list[Page], Json]:
    """Read every page and report what was read, skipped, missing or superseded, with the reason."""
    raw: list[Page] = []
    skipped: list[Json] = []
    invalid: list[Json] = []
    files = sorted(set(_list_files(paths)))
    repeated = {f.name for f in files if sum(g.name == f.name for g in files) > 1}
    for file in files:
        name = file.as_posix() if file.name in repeated else file.name
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            invalid.append({"file": name, "error": str(exc)})
            continue
        if not isinstance(data, dict) or not isinstance(data.get("skill"), str) or "sections" not in data:
            skipped.append({"file": name, "why": "not a page: no skill or sections"})
            continue
        if data["skill"] == OWN_SKILL:
            skipped.append({"file": name, "why": "an earlier blueprint is not an input"})
            continue
        meta = data.get("meta")
        match = DATE_IN_NAME.search(file.name)
        date = _str(meta.get("date")) if isinstance(meta, dict) else ""
        date = date or (match.group(1) if match else "")
        facts = data.get("facts") if isinstance(data.get("facts"), dict) else None
        raw.append(Page(name, file.as_posix(), data["skill"], date, facts))
    newest: dict[str, Page] = {}
    superseded: list[Json] = []
    for page in sorted(raw, key=lambda p: (p.date, p.file)):
        if page.skill in newest:
            older = newest[page.skill]
            superseded.append({"file": older.file, "by": page.file, "skill": page.skill})
        newest[page.skill] = page
    pages = sorted(newest.values(), key=lambda p: p.file)
    brief = next((p for p in pages if p.skill == BRIEF_SKILL), None)
    named = _strings(brief.facts.get("specialists")) if brief and brief.facts else []
    wanted = expect or named or list(DECIDING_SKILLS)
    source = "--expect" if expect else (f"specialists on {brief.file}" if named and brief else "the deciding skills")
    seen = {p.skill for p in pages}
    report = {
        "read": [
            {"file": p.file, "path": p.path, "skill": p.skill, "date": p.date, "has_facts": p.facts is not None}
            for p in pages
        ],
        "no_facts": [p.file for p in pages if p.facts is None],
        "missing_skills": [s for s in wanted if s not in seen],
        "expected_skills": wanted,
        "expected_from": source,
        "brief_page": brief.file if brief else None,
        "superseded": superseded,
        "skipped": skipped,
        "invalid": invalid,
    }
    return pages, report


def merge(pages: list[Page]) -> Json:
    """Every fact with the page it came from, in one place."""
    merged: Json = {k: [] for k in ("components", "regions", "data", "decisions", "assumptions", "open", "budgets")}
    for page in pages:
        facts = page.facts or {}
        origin = {"page": page.file, "skill": page.skill}
        for key in ("components", "regions", "data", "decisions"):
            merged[key] += [{**item, **origin} for item in _dicts(facts.get(key))]
        for key in ("assumptions", "open"):
            merged[key] += [{"text": text, **origin} for text in _strings(facts.get(key))]
        budget = facts.get("budget")
        if isinstance(budget, dict) and isinstance(budget.get("monthly"), int | float):
            merged["budgets"].append({**budget, "currency": _str(budget.get("currency")).upper(), **origin})
    return merged


def _page_total(items: list[Json], labelled: bool) -> tuple[float | None, str]:
    """A page's number for one cloud and variant: its stated total, or its lines added up."""
    stated = [i for i in items if TOTAL_WORD.search(_str(i.get("item")))]
    if len(stated) == 1:
        return float(stated[0]["monthly"]), f"stated on the page: {stated[0]['item']}"
    if stated:
        return None, f"{len(stated)} lines say total on one page: they may be alternatives"
    if not labelled and any(VARIANT_WORD.search(_str(i.get("item"))) for i in items):
        return None, "lines name variants without a variant field: they may be alternatives"
    return round(sum(float(i["monthly"]) for i in items), 2), "sum of its lines"


def group_costs(pages: list[Page]) -> Json:
    """Costs per currency, then per cloud and variant. A sum exists only inside one group."""
    lines: list[Json] = []
    for page in pages:
        for cost in _dicts((page.facts or {}).get("costs")):
            monthly = cost.get("monthly")
            if not isinstance(monthly, int | float) or isinstance(monthly, bool):
                continue
            lines.append(
                {
                    "item": _str(cost.get("item")),
                    "monthly": float(monthly),
                    "currency": _str(cost.get("currency")).upper(),
                    "as_of": _str(cost.get("as_of")),
                    "source": _str(cost.get("source")),
                    "cloud": _str(cost.get("cloud")) or None,
                    "variant": _str(cost.get("variant")) or None,
                    "page": page.file,
                    "skill": page.skill,
                }
            )
    keys = sorted({(line["currency"], line["cloud"] or "", line["variant"] or "") for line in lines})
    groups = []
    for currency, cloud, variant in keys:
        items = [
            line
            for line in lines
            if (line["currency"], line["cloud"] or "", line["variant"] or "") == (currency, cloud, variant)
        ]
        per_page = []
        for name in sorted({line["page"] for line in items}):
            own = [line for line in items if line["page"] == name]
            total, basis = _page_total(own, bool(cloud or variant))
            per_page.append({"page": name, "total": total, "basis": basis})
        totals = [p["total"] for p in per_page]
        blocked = next((p["basis"] for p in per_page if p["total"] is None), None)
        dates = sorted(line["as_of"] for line in items if line["as_of"])
        groups.append(
            {
                "currency": currency,
                "cloud": cloud or None,
                "variant": variant or None,
                "total": None if blocked else round(sum(t for t in totals if t is not None), 2),
                "not_added_because": blocked,
                "added_across_pages": [p["page"] for p in per_page] if len(per_page) > 1 and not blocked else [],
                "per_page": per_page,
                "oldest_as_of": dates[0] if dates else None,
                "newest_as_of": dates[-1] if dates else None,
                "items": items,
            }
        )
    return {
        "currencies": sorted({line["currency"] for line in lines}),
        "groups": groups,
        "note": (
            "Grouped per currency, then per cloud and variant. A total exists only inside one group and is never "
            "added across currencies. When added_across_pages has several pages, check they did not price the same "
            "thing twice; a variant name is compared literally."
        ),
    }


def areas_of(text: str, *, rule: bool = False) -> set[str]:
    """The areas a region name or a rule names. In a rule, short words count only in capitals ("US", not "us")."""
    found: set[str] = set()
    tokens = re.findall(r"[A-Za-z0-9]+", text)
    lowered = [t.lower() for t in tokens]
    joined = "".join(lowered)
    prose = f" {' '.join(lowered)} "
    for area, words in REGION_AREAS.items():
        for word in words:
            if len(word) <= SHORT_AREA:
                hit = word.upper() in tokens if rule else word in lowered
            else:
                # Prose words must stand alone ("comparison" holds "paris"); a joined name need not ("westeurope").
                hit = f" {word} " in prose if rule else word.replace(" ", "") in joined
            if hit:
                found.add(area)
    if not rule and any(JOINED_US.match(t) for t in lowered):
        found.add("US")
    if not rule and any(JOINED_UK.match(t) for t in lowered):
        found.add("UK")
    return found


def area_of(name: str) -> str | None:
    areas = areas_of(name)
    return sorted(areas)[0] if len(areas) == 1 else None


def rule_areas(rule: str) -> tuple[set[str], set[str]]:
    """(areas a rule confines data to, areas it keeps data out of). Both empty when it names neither."""
    confined: set[str] = set()
    refused: set[str] = set()
    for clause in re.split(r"[;,.]", rule):
        areas = areas_of(clause, rule=True)
        if not areas:
            continue
        if CONFINE.search(clause):
            confined |= areas
        elif REFUSE.search(clause):
            refused |= areas
    return confined, refused


def _page_regions(page: Page) -> list[str]:
    """Every region a page names, on the page or on a component."""
    facts = page.facts or {}
    named = [_str(r.get("name")) for r in _dicts(facts.get("regions"))]
    named += [_str(c.get("region")) for c in _dicts(facts.get("components"))]
    return [n for n in dict.fromkeys(named) if n]


def _region_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _is_area_only(name: str) -> bool:
    """True for "EU" or "Europe": a place too wide to disagree with a named region inside it."""
    return _region_key(name) in {w for words in REGION_AREAS.values() for w in words}


def region_conflicts(pages: list[Page], merged: Json) -> tuple[list[Json], list[Json]]:
    """Regions a data rule forbids, regions that disagree across pages, and names not placed in any area."""
    conflicts: list[Json] = []
    rules: list[Json] = []
    for item in merged["data"]:
        rule = _str(item.get("rule"))
        confined, refused = rule_areas(rule)
        if confined or refused:
            rules.append(
                {
                    "data": _str(item.get("name")),
                    "rule": rule,
                    "page": item["page"],
                    "where": _strings(item.get("where")),
                    "confined": confined,
                    "refused": refused,
                }
            )
    unplaced: list[Json] = []
    for page in pages:
        facts = page.facts or {}
        components = _dicts(facts.get("components"))
        for region in _page_regions(page):
            area = area_of(region)
            if area is None:
                unplaced.append({"region": region, "page": page.file})
                continue
            against = [r for r in rules if (r["confined"] and area not in r["confined"]) or area in r["refused"]]
            if not against:
                continue
            placed = [c for c in components if _str(c.get("region")) == region]
            stated = [_str(r.get("name")) for r in _dicts(facts.get("regions"))]
            conflicts.append(
                {
                    "type": "region_forbidden",
                    "pages": sorted({page.file, *(r["page"] for r in against)}),
                    "values": {
                        "region": region,
                        "area": area,
                        "named_by": page.file,
                        "page_level_region": region in stated,
                        "components": [
                            {
                                "id": _str(c.get("id")),
                                "label": _str(c.get("label")),
                                "kind": _str(c.get("kind")),
                                "named_in_rule": any(_text_names(where, c) for r in against for where in r["where"]),
                            }
                            for c in placed
                        ],
                        "rules": [{"data": r["data"], "rule": r["rule"], "page": r["page"]} for r in against],
                    },
                    "read": "Does this component or region carry the data the rule protects?",
                }
            )
    per_page = {
        p.file: sorted({_region_key(n) for n in _page_regions(p) if not _is_area_only(n)})
        for p in pages
        if any(not _is_area_only(n) for n in _page_regions(p))
    }
    names = list(per_page)
    disjoint = [[a, b] for i, a in enumerate(names) for b in names[i + 1 :] if not set(per_page[a]) & set(per_page[b])]
    if disjoint:
        conflicts.append(
            {
                "type": "regions_disagree",
                "pages": sorted({p for pair in disjoint for p in pair}),
                "values": {
                    "by_page": {p: [n for n in _page_regions(_find(pages, p)) if not _is_area_only(n)] for p in names},
                    "no_region_in_common": disjoint,
                },
                "read": "Are these pages the same deployment? If they are, one region must change; if not, say so.",
            }
        )
    return conflicts, unplaced


def _find(pages: list[Page], file: str) -> Page:
    return next(p for p in pages if p.file == file)


def _text_names(text: str, component: Json) -> bool:
    """True when a `where` entry of a data rule names this component, so the link is stated, not assumed."""
    wanted = [_str(component.get("id")).lower(), _str(component.get("label")).lower()]
    return any(w and w in text.lower() for w in wanted)


def decision_conflicts(merged: Json) -> list[Json]:
    """The same decision title with different choices, across pages."""
    by_title: dict[str, list[Json]] = {}
    for item in merged["decisions"]:
        key = _key(_str(item.get("title")))
        if key:
            by_title.setdefault(key, []).append(item)
    conflicts: list[Json] = []
    for items in by_title.values():
        pages = {item["page"] for item in items}
        choices = {_key(_str(item.get("chosen"))) for item in items} - {""}
        if len(pages) > 1 and len(choices) > 1:
            conflicts.append(
                {
                    "type": "decision_differs",
                    "pages": sorted(pages),
                    "values": {
                        "title": _str(items[0].get("title")),
                        "choices": [
                            {"page": i["page"], "chosen": _str(i.get("chosen")), "because": _str(i.get("because"))}
                            for i in items
                        ],
                    },
                    "read": "Do the pages decide the same thing? If so one must change; name the side you recommend.",
                }
            )
    return conflicts


def _key(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def stale_conflicts(costs: Json, today: dt.date, stale_days: int) -> list[Json]:
    """Costs dated too far back to trust without a fresh look at the price."""
    by_page: dict[tuple[str, str], list[Json]] = {}
    for group in costs["groups"]:
        for item in group["items"]:
            when = _date(item["as_of"])
            if when is not None and (today - when).days > stale_days:
                by_page.setdefault((item["page"], item["as_of"]), []).append(item)
    return [
        {
            "type": "stale_cost",
            "pages": [page],
            "values": {
                "as_of": as_of,
                "age_days": (today - dt.date.fromisoformat(as_of)).days,
                "threshold_days": stale_days,
                "items": [
                    {"item": i["item"], "monthly": i["monthly"], "currency": i["currency"], "source": i["source"]}
                    for i in items
                ],
            },
            "read": "Is the price still right? Check the source before this number is used.",
        }
        for (page, as_of), items in sorted(by_page.items())
    ]


def _date(text: str) -> dt.date | None:
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        return None


def currency_conflicts(costs: Json) -> list[Json]:
    """More than one currency among the costs: they cannot be added or compared here."""
    if len(costs["currencies"]) < 2:
        return []
    per_currency = []
    for currency in costs["currencies"]:
        groups = [g for g in costs["groups"] if g["currency"] == currency]
        per_currency.append(
            {
                "currency": currency,
                "pages": sorted({p["page"] for g in groups for p in g["per_page"]}),
                "group_totals": [{"cloud": g["cloud"], "variant": g["variant"], "total": g["total"]} for g in groups],
            }
        )
    return [
        {
            "type": "mixed_currencies",
            "pages": sorted({p for c in per_currency for p in c["pages"]}),
            "values": {"per_currency": per_currency},
            "read": "These cannot be added or compared here: report each currency apart, never converted.",
        }
    ]


def budget_conflicts(merged: Json, costs: Json) -> list[Json]:
    """A total over the stated budget, or budgets and totals that cannot be compared."""
    conflicts: list[Json] = []
    budgets: dict[tuple[float, str], list[Json]] = {}
    for budget in merged["budgets"]:
        budgets.setdefault((float(budget["monthly"]), budget["currency"]), []).append(budget)
    if len(budgets) > 1:
        conflicts.append(
            {
                "type": "budgets_differ",
                "pages": sorted({b["page"] for items in budgets.values() for b in items}),
                "values": {
                    "budgets": [
                        {"monthly": monthly, "currency": currency, "pages": [b["page"] for b in items]}
                        for (monthly, currency), items in budgets.items()
                    ]
                },
                "read": "Which budget is the brief's? Compare totals against that one.",
            }
        )
    for (monthly, currency), items in budgets.items():
        pages = [b["page"] for b in items]
        for group in costs["groups"]:
            if group["currency"] == currency and group["total"] is not None and group["total"] > monthly:
                conflicts.append(
                    {
                        "type": "over_budget",
                        "pages": sorted({*pages, *(p["page"] for p in group["per_page"])}),
                        "values": {
                            "budget": monthly,
                            "currency": currency,
                            "budget_pages": pages,
                            "cloud": group["cloud"],
                            "variant": group["variant"],
                            "total": group["total"],
                            "over_by": round(group["total"] - monthly, 2),
                            "added_across_pages": group["added_across_pages"],
                        },
                        "read": "Is everything in this total meant to be paid together? Check before calling it over.",
                    }
                )
        others = sorted({g["currency"] for g in costs["groups"]} - {currency})
        for other in others:
            groups = [g for g in costs["groups"] if g["currency"] == other]
            conflicts.append(
                {
                    "type": "budget_other_currency",
                    "pages": sorted({*pages, *(p["page"] for g in groups for p in g["per_page"])}),
                    "values": {
                        "budget": monthly,
                        "budget_currency": currency,
                        "other_currency": other,
                        "group_totals": [
                            {"cloud": g["cloud"], "variant": g["variant"], "total": g["total"]} for g in groups
                        ],
                    },
                    "read": "Not compared with the budget: other currency, never converted. Say so on the page.",
                }
            )
    return conflicts


def _tech_words(tech: str) -> frozenset[str]:
    # What follows the first comma is usually configuration ("Azure SQL, GP_Gen5_2"), not another technology.
    head = tech.split(",")[0].lower()
    words = [TECH_ALIASES.get(w, w) for w in re.findall(r"[a-z0-9+#.]+", head)]
    return frozenset(w.removesuffix("s") if len(w) > 3 else w for w in words if w not in TECH_NOISE)


def _is_placeholder(tech: str) -> bool:
    return tech.strip().lower() in PLACEHOLDER_TECH or tech.strip().lower().startswith("not ")


def tech_conflicts(merged: Json) -> list[Json]:
    """The same component (same id or same label) under different technologies across pages."""
    groups: list[list[Json]] = []
    for item in merged["components"]:
        if _is_placeholder(_str(item.get("tech"))):
            continue
        keys = {_key(_str(item.get("id"))), _key(_str(item.get("label")))} - {""}
        for group in groups:
            if keys & {_key(_str(i.get(f))) for i in group for f in ("id", "label")}:
                group.append(item)
                break
        else:
            groups.append([item])
    conflicts: list[Json] = []
    for group in groups:
        pages = {i["page"] for i in group}
        techs = list(dict.fromkeys(_str(i.get("tech")) for i in group))
        words = [_tech_words(t) for t in techs]
        # One name inside the other ("PostgreSQL", "Azure Database for PostgreSQL") is a refinement, not a conflict.
        clash = any(not (a <= b or b <= a) for i, a in enumerate(words) for b in words[i + 1 :])
        if len(pages) > 1 and clash:
            conflicts.append(
                {
                    "type": "component_technology",
                    "pages": sorted(pages),
                    "values": {
                        "component": _str(group[0].get("id")) or _str(group[0].get("label")),
                        "versions": [
                            {
                                "page": i["page"],
                                "id": _str(i.get("id")),
                                "label": _str(i.get("label")),
                                "tech": _str(i.get("tech")),
                                "kind": _str(i.get("kind")),
                            }
                            for i in group
                        ],
                    },
                    "read": "Is this one component? If so one technology must win; name the side and why.",
                }
            )
    return conflicts


def _numbers_in(text: str, pattern: re.Pattern[str]) -> list[float]:
    found = []
    for match in pattern.finditer(text):
        raw = next((g for g in match.groups() if g), "")
        if not raw:
            continue
        value = float(raw.replace(",", ""))
        scale = re.search(rf"{re.escape(raw)}\s*(k|thousand|million)\b", match.group(0), re.I)
        if scale:
            value *= 1_000_000 if scale.group(1).lower() == "million" else 1000
        found.append(value)
    return found


def assumption_conflicts(merged: Json) -> list[Json]:
    """Numbers about the same thing that differ across pages. Everything else is left for Claude to read."""
    conflicts: list[Json] = []
    for topic, pattern in ASSUMPTION_TOPICS.items():
        said: list[Json] = []
        for item in merged["assumptions"]:
            said += [
                {"page": item["page"], "number": number, "text": item["text"]}
                for number in _numbers_in(item["text"], pattern)
            ]
        if len({s["page"] for s in said}) > 1 and len({s["number"] for s in said}) > 1:
            conflicts.append(
                {
                    "type": "assumption_numbers",
                    "pages": sorted({s["page"] for s in said}),
                    "values": {"topic": topic, "said": said},
                    "read": "Different numbers for the same thing. Which is right? It may change a decision.",
                }
            )
    return conflicts


def join(paths: list[Path], today: dt.date, stale_days: int, expect: list[str] | None) -> Json:
    pages, report = read_pages(paths, expect)
    merged = merge(pages)
    costs = group_costs(pages)
    region_found, unplaced = region_conflicts(pages, merged)
    conflicts = (
        region_found
        + decision_conflicts(merged)
        + stale_conflicts(costs, today, stale_days)
        + currency_conflicts(costs)
        + budget_conflicts(merged, costs)
        + tech_conflicts(merged)
        + assumption_conflicts(merged)
    )
    return {
        "pages": report,
        "thresholds": {
            "today": today.isoformat(),
            "stale_cost_days": stale_days,
            "assumption_topics": list(ASSUMPTION_TOPICS),
            "placeholder_tech": list(PLACEHOLDER_TECH),
            "region_area_words": {area: list(words) for area, words in REGION_AREAS.items()},
        },
        "merged": merged,
        "costs": costs,
        "regions_not_placed": unplaced,
        "conflicts": conflicts,
        "conflict_counts": {t: sum(c["type"] == t for c in conflicts) for t in sorted({c["type"] for c in conflicts})},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Join the facts of specialist pages and list their conflicts.")
    parser.add_argument("paths", nargs="+", type=Path, help="page JSON files or folders of them")
    parser.add_argument("--today", help="YYYY-MM-DD, for staleness; defaults to today")
    parser.add_argument("--stale-days", type=int, default=STALE_COST_DAYS, help="a cost older than this is stale")
    parser.add_argument("--expect", help="comma-separated skills that must have run")
    args = parser.parse_args(argv)
    try:
        today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    except ValueError:
        print(f"not a date: {args.today}", file=sys.stderr)
        return 2
    missing = [str(p) for p in args.paths if not p.exists()]
    if missing:
        print(f"not found: {', '.join(missing)}", file=sys.stderr)
        return 2
    expect = [s.strip() for s in args.expect.split(",") if s.strip()] if args.expect else None
    json.dump(join(args.paths, today, args.stale_days, expect), sys.stdout, indent=1, ensure_ascii=False)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
