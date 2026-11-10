#!/usr/bin/env python3
"""List the places a review of design documents should look at: parts, calls, shared data, promises, goals, open items.

Usage: python3 design_inventory.py PATH [PATH ...]

PATH is a document or a folder of them (.md, .markdown, .txt, .adoc). Files named .env* are never opened; they are
listed under skipped by name only. File paths in the output are relative to the folder the arguments share.

The inventory finds places to look, not findings. Every entry carries the file and line it came from, and the model
confirms each one by reading that line and what is around it. What a design leaves out (no timeout on a call, no
mechanism behind a promise, no number behind a goal) cannot be listed: the reader judges it.

documents      title, headings and word count of every document
adrs           number, title, status, date, supersedes and superseded_by of every ADR-like file: a name that starts
               with 3 or 4 digits and a dash, or a Status line or section near the top
parts          candidate components with how often and where first they are mentioned: mermaid nodes, the first
               column of a table headed component, service or part, bold list leads (- **Name**:) and headings that
               end in service, gateway, broker, database and the like
links          mermaid edges and sentences such as "X calls Y", "X publishes ... to Y", "X polls Y", "X reads from Y",
               each with a style: sync (REST, HTTP, gRPC, calls, waits, polls), async (event, queue, broker,
               publish, subscribe) or unknown. In a sentence the subject is the nearest part named before the verb.
data_writes    tables or entities in backticks with the parts said to write, update or own them, from sentences and
               from tables with a "written by" or "owner" column; shared_write when two or more parts do
promises       sentences with never, always, every, must, guarantee, exactly once, at most, at least, idempotent,
               atomic or "no data loss"
quality_goals  sentences about availability, latency, response time, percentiles, throughput, scale, peak, uptime,
               RTO, RPO, durability or consistency, with has_number and the numbers found
latencies      every stated duration (400-800 ms, 50 ms, 15 minutes) with its sentence and the parts it names
open           TBD, TODO, "to be decided", "decide later", "open question", list items that end in "?" and ADRs whose
               status is Proposed or Draft

Mermaid: flowchart and graph blocks only. Read-only, standard library only, JSON on stdout.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

SUFFIXES = (".md", ".markdown", ".txt", ".adoc")
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", "target", "bin", "obj"}
MAX_BYTES = 2_000_000
MAX_TEXT = 300
NOTE = (
    "Places to look, not findings: confirm each entry by reading its line. What is missing (a timeout, a fallback, "
    "an idempotency key, a number behind a goal) is judged by reading; an inventory cannot list absences."
)

# Markdown structure
FENCE = re.compile(r"^(`{3,}|~{3,})\s*([\w-]*)")
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*$")
ADOC_HEADING = re.compile(r"^(={1,6})\s+(.+?)\s*$")
ITEM = re.compile(r"^(?:[-*+]|\d+[.)])\s+(.*)$")
ROW = re.compile(r"^\|.*\|$")
RULE_ROW = re.compile(r"^\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)*\|?$")
SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9`\"'(\[])")
MD_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
WORD = re.compile(r"\w[\w'\u2019-]*")

# Parts
COMPONENT_HEADER = re.compile(
    r"^(?:components?|services?|parts?|containers?|systems?|building blocks?|modules?|elements?)$", re.I
)
PART_WORDS = {
    "service", "gateway", "validator", "broker", "database", "db", "store", "queue", "cache", "worker", "adapter",
    "api", "bus", "proxy", "registry", "scheduler",
}  # fmt: skip
GENERIC = {"service", "services", "api", "apis", "app", "application", "component", "module", "system", "server"}
STOP = {
    "data", "web", "mobile", "message", "address", "event", "order", "customer", "user", "core", "main", "platform",
    "central", "admin", "front", "back", "common", "shared", "internal", "external", "public", "private",
}  # fmt: skip
THE_ALIAS = {"broker", "gateway", "validator"}
BOLD_LEAD = re.compile(r"^\*\*([^*]+?)(?::\*\*|\*\*\s*(?::|\u2014|\u2013|-\s))")
HEADING_PREFIX = re.compile(r"^(?:ADR[- ]?\d+\s*[:.\u2013-]?\s*|\d+(?:\.\d+)*[.)]?\s+)", re.I)

# Mermaid
MERMAID_SKIP = re.compile(r"^(?:flowchart|graph|subgraph|end|classDef|class|style|linkStyle|click|direction)\b")
NODE = (
    r"\b([A-Za-z_]\w*)\s*(\[\[|\[\(|\(\(|\(\[|\{\{|\[|\(|\{)\s*\"?([^\"\[\](){}|]*?)\"?\s*"
    r"(\]\]|\)\]|\)\)|\]\)|\}\}|\]|\)|\})"
)
NODE_OR_LABEL = re.compile(r"(\|[^|]*\|)|" + NODE)
ARROW = (
    r"(?:--\s*(?P<l1>[^->|][^>|]*?)\s*-->|-\.\s*(?P<l2>[^.>|][^>|]*?)\s*\.->|==\s*(?P<l4>[^=>|][^>|]*?)\s*==>"
    r"|(?P<arrow><?(?:-{2,}>|-\.+->|={2,}>|-{3,}|-\.+-|={3,})))\s*(?:\|(?P<l3>[^|]*)\|)?"
)
ENDS = r"\w+(?:\s*&\s*\w+)*"
EDGE = re.compile(rf"(?P<a>{ENDS})\s*{ARROW}\s*(?=(?P<b>{ENDS}))")

# Links and their style
LINK_VERB = re.compile(
    r"\b(calls?|called|sends?|publish(?:es)?|polls?|reads from|reads|writes to|writes|subscribes? to|consumes?|"
    r"quer(?:y|ies)|fetch(?:es)?|requests|asks|notif(?:y|ies)|emits?|receives?|forwards?|pushes|invokes?)\b",
    re.I,
)
SYNC_VERBS = {"call", "calls", "called", "poll", "polls", "query", "queries", "fetch", "fetches", "invoke", "invokes"}
ASYNC_VERBS = {"publish", "publishes", "subscribe", "subscribes", "consume", "consumes", "emit", "emits"}
SYNC_ACRONYMS = re.compile(r"\b(?:REST|HTTPS?|gRPC|GraphQL|SOAP)\b")
SYNC_WORDS = re.compile(
    r"\b(?:synchronous(?:ly)?|calls?|called|calling|waits?|waiting|polls?|polled|polling|blocking)\b", re.I
)
ASYNC_WORDS = re.compile(
    r"\b(?:asynchronous(?:ly)?|events?|queues?|queued|brokers?|publish(?:es|ed|ing)?|subscri(?:be|bes|bed|ption)|"
    r"topics?|messages?)\b",
    re.I,
)
AND_JOINER = re.compile(r"\s*,?\s*(?:and|or|&)\s+(?:both\s+)?(?:the\s+)?", re.I)
COMMA_JOINER = re.compile(r"\s*,\s*(?:the\s+)?", re.I)
CLAUSE_END = re.compile(r"\s*(?:(?:also|then|only|now|still|\w+ly)\s+)?", re.I)

# Data
WRITE_VERB = re.compile(
    r"\b(writes?|wrote|written|updates?|updated|sets?|inserts?|inserted|deletes?|deleted|changes?|changed|"
    r"modif(?:y|ies|ied)|owns?|owned)\b",
    re.I,
)
PASSIVE = {"written", "updated", "set", "inserted", "deleted", "changed", "modified", "owned"}
ENTITY = re.compile(r"`([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)`")
ENTITY_LIST = r"`[^`]+`(?:\s*(?:,\s*and|,\s*or|,|and|or)\s*`[^`]+`)*"
AFTER_VERB = re.compile(rf"(?:\s+[a-z][\w'-]*){{0,4}}?\s+({ENTITY_LIST})")
BEFORE_PASSIVE = re.compile(rf"({ENTITY_LIST})\s+(?:is|are|was|were|gets?|got)\s+(?:\w+\s+)?$")
WRITER_HEADER = re.compile(r"\b(?:written|writes?|writers?|updated|updates?|owners?|owned|owns?)\b", re.I)

# Promises, goals, numbers, open items
PROMISE = re.compile(
    r"\b(never|always|every|must|guarantee[sd]?|exactly[- ]once|at[- ]most|at[- ]least|idempotent(?:ly)?|"
    r"atomic(?:ally)?|no data loss)\b",
    re.I,
)
QUALITY = re.compile(
    r"\b(availab\w*|latenc\w*|response times?|p\d{2}(?:\.\d+)?|percentiles?|throughput|"
    r"scal(?:e|es|ed|ing|able|ability)|peaks?|uptime|rto|rpo|durab\w*|consisten\w*)\b",
    re.I,
)
NUM = r"\d+(?:[.,]\d+)?"
SPAN = rf"{NUM}(?:\s*(?:[-\u2013\u2014]|to)\s*{NUM})?"
DURATION = re.compile(
    rf"(?<![\w.,]){SPAN}\s*-?\s*(?:ms|milliseconds?|s|secs?|seconds?|mins?|minutes?|h|hrs?|hours?|days?|weeks?)\b",
    re.I,
)
RATE = re.compile(
    rf"(?<![\w.,]){SPAN}\s*(?:%|percent\b|(?:[a-z]+\s+)?(?:per|/|an?)\s*(?:second|sec|s|minute|min|hour|h|day)\b"
    r"|req/s\b|rps\b|tps\b)",
    re.I,
)
PERCENTILE = re.compile(r"\bp\d{2}(?:\.\d+)?\b", re.I)
OPEN_MARK = re.compile(r"\b(TBD|TBC|TODO|FIXME)\b")
OPEN_PHRASE = re.compile(
    r"\b(to be (?:decided|determined|defined|confirmed|agreed)|decided? later|open questions?|not (?:yet )?decided|"
    r"undecided|not chosen yet)\b",
    re.I,
)

# ADRs
ADR_NAME = re.compile(r"^(\d{3,4})-")
STATUS_LINE = re.compile(r"^\s*(?:[-*]\s+)?(?:\*\*)?status(?:\*\*)?\s*:{1,2}\s*(?:\*\*)?\s*(.+?)\s*$", re.I)
STATUS_HEADING = re.compile(r"^(?:#{1,6}|={1,6})\s*status\s*:?\s*$", re.I)
DATE_LINE = re.compile(r"^\s*(?:[-*]\s+)?(?:\*\*)?date(?:\*\*)?\s*:{1,2}\s*(?:\*\*)?\s*(\d{4}-\d{2}-\d{2})", re.I)
ADR_REF = re.compile(r"\bADR[- ]?0*(\d{1,4})\b|(?<![\w-])0*(\d{1,4})-[\w-]+\.(?:md|markdown|adoc|txt)\b", re.I)
OPEN_STATUSES = {"proposed", "draft", "pending", "open", "review"}
STATUS_LINES = 40


@dataclass
class Unit:
    """A paragraph, a list item or a table row, with the line it starts on."""

    line: int
    kind: str
    lines: list[str]
    cells: list[str] = field(default_factory=list)
    header: list[str] = field(default_factory=list)


@dataclass
class Doc:
    file: str
    text: str
    title: str = ""
    title_line: int = 1
    words: int = 0
    headings: list[tuple[int, int, str]] = field(default_factory=list)
    units: list[Unit] = field(default_factory=list)
    diagrams: list[list[tuple[int, str]]] = field(default_factory=list)
    lines: list[tuple[int, str]] = field(default_factory=list)  # every line outside code, mermaid included


@dataclass
class Sentence:
    file: str
    line: int
    text: str
    kind: str
    cells: list[str] = field(default_factory=list)
    header: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Mention:
    start: int
    end: int
    name: str


@dataclass
class Link:
    verb: str
    subjects: list[Mention]
    objects: list[Mention]
    style: str


@dataclass
class Part:
    name: str
    file: str
    line: int
    sources: list[str] = field(default_factory=list)
    mentions: int = 0
    first: tuple[str, int] | None = None


def clean(text: str) -> str:
    text = MD_LINK.sub(r"\1", text).replace("**", "")
    return " ".join(text.split())


def short(text: str) -> str:
    return text if len(text) <= MAX_TEXT else text[: MAX_TEXT - 3] + "..."


def split_row(line: str) -> list[str]:
    return [cell.strip() for cell in re.split(r"(?<!\\)\|", line.strip()[1:-1])]


def parse(file: str, text: str) -> Doc:
    """Split a document into headings, paragraphs, list items, table rows and mermaid blocks, keeping line numbers."""
    doc = Doc(file, text)
    lines = text.splitlines()
    adoc = file.lower().endswith(".adoc")
    first = 0
    if lines and lines[0].strip() == "---":  # front matter
        end = next((i for i in range(1, len(lines)) if lines[i].strip() in ("---", "...")), None)
        first = end + 1 if end is not None else 0
    current: Unit | None = None
    fence, lang = "", ""
    block: list[tuple[int, str]] = []
    header: list[str] = []
    last_row = -1

    def close() -> None:
        nonlocal current
        if current is not None:
            doc.units.append(current)
            current = None

    for number, raw in enumerate(lines[first:], start=first + 1):
        stripped = raw.strip()
        if fence:
            if stripped.startswith(fence) and not stripped.strip(fence[0]):
                if lang == "mermaid":
                    doc.diagrams.append(block)
                fence, lang, block = "", "", []
            elif lang == "mermaid":
                block.append((number, raw))
                doc.lines.append((number, raw))
            continue
        opened = FENCE.match(stripped)
        if opened or (adoc and stripped in ("----", "....")):
            close()
            fence = opened.group(1) if opened else stripped
            lang = opened.group(2).lower() if opened else ""
            continue
        doc.lines.append((number, raw))
        doc.words += len(WORD.findall(stripped))
        if stripped.startswith(">"):
            stripped = stripped.lstrip("> ").strip()
        if not stripped:
            close()
            continue
        heading = HEADING.match(stripped) or (ADOC_HEADING.match(stripped) if adoc else None)
        if heading:
            close()
            title = clean(heading.group(2))
            doc.headings.append((number, len(heading.group(1)), title))
            if not doc.title:
                doc.title, doc.title_line = title, number
            continue
        if ROW.match(stripped):
            close()
            if RULE_ROW.match(stripped):
                if doc.units and doc.units[-1].kind == "row" and doc.units[-1].line == last_row == number - 1:
                    header = doc.units.pop().cells
                last_row = number
                continue
            if last_row != number - 1:
                header = []
            doc.units.append(Unit(number, "row", [stripped], split_row(stripped), header))
            last_row = number
            continue
        item = ITEM.match(stripped)
        if item:
            close()
            current = Unit(number, "item", [item.group(1)])
        elif current is None:
            current = Unit(number, "para", [stripped])
        else:
            current.lines.append(stripped)
    close()
    if fence and lang == "mermaid":
        doc.diagrams.append(block)
    if not doc.title:
        doc.title = PurePosixPath(file).stem
    return doc


def sentences(doc: Doc) -> list[Sentence]:
    """Paragraphs and list items split into sentences; a table row is one sentence."""
    found: list[Sentence] = []
    for unit in doc.units:
        if unit.kind == "row":
            cells = [clean(cell) for cell in unit.cells]
            found.append(
                Sentence(doc.file, unit.line, " | ".join(cells), "row", cells, [clean(h) for h in unit.header])
            )
            continue
        raw = "\n".join(unit.lines)
        start = 0
        for end in [*SENTENCE_END.finditer(raw), None]:
            text = clean(raw[start : end.start() if end else len(raw)])
            if text:
                found.append(Sentence(doc.file, unit.line + raw.count("\n", 0, start), text, unit.kind))
            if end:
                start = end.end()
    return found


# ---------------------------------------------------------------------------- parts


def norm(name: str) -> str:
    return " ".join(re.sub(r"^the\s+", "", name.strip(), flags=re.I).lower().split())


def part_name(raw: str) -> str | None:
    name = re.sub(r"<br\s*/?>", " ", raw, flags=re.I).replace("`", "")
    name = clean(name).strip(" :.;,-\u2013\u2014\"'")
    words = name.split()
    if not 1 <= len(words) <= 5 or len(name) > 50 or not name[0].isalpha() or "?" in name:
        return None
    return name


def short_name(name: str) -> str | None:
    """'Booking service' is also called 'Booking': a capitalised first word before a generic one."""
    words = name.split()
    if len(words) != 2 or words[1].lower() not in GENERIC:
        return None
    first = words[0]
    if len(first) < 4 or not first[0].isupper() or first.lower() in STOP:
        return None
    return first


class Catalogue:
    """Finds the parts named in a piece of text, longest name first."""

    def __init__(self, names: list[str]) -> None:
        self.patterns: list[tuple[re.Pattern[str], str]] = []
        shorts: dict[str, list[str]] = {}
        ends: dict[str, list[str]] = {}
        known = {norm(name) for name in names}
        for name in names:
            body = r"\s+".join(re.escape(word) for word in name.split())
            self.patterns.append((re.compile(rf"(?<![\w-]){body}(?![\w-])", re.I), name))
            alias = short_name(name)
            if alias:
                shorts.setdefault(alias, []).append(name)
            words = name.split()
            if len(words) > 1 and words[-1].lower() in THE_ALIAS:
                ends.setdefault(words[-1].lower(), []).append(name)
        for alias, owners in shorts.items():
            if len(owners) == 1 and alias.lower() not in known:
                self.patterns.append((re.compile(rf"(?<![\w-]){re.escape(alias)}(?![\w-])"), owners[0]))
        for word, owners in ends.items():
            if len(owners) == 1:
                self.patterns.append((re.compile(rf"(?<=\bthe ){word}\b", re.I), owners[0]))

    def find(self, text: str) -> list[Mention]:
        found = [Mention(m.start(), m.end(), name) for pattern, name in self.patterns for m in pattern.finditer(text)]
        found.sort(key=lambda m: (m.start, m.start - m.end))
        taken: list[Mention] = []
        for mention in found:
            if not taken or mention.start >= taken[-1].end:
                taken.append(mention)
        return taken


def read_diagram(
    block: list[tuple[int, str]],
) -> tuple[dict[str, tuple[str, int]], list[tuple[str, str, str, str, int]]]:
    """Nodes (id -> label, line) and edges (from id, to id, label, arrow, line) of a mermaid flowchart."""
    nodes: dict[str, tuple[str, int]] = {}
    edges: list[tuple[str, str, str, str, int]] = []
    body = [(number, raw.split("%%")[0].strip()) for number, raw in block]
    body = [(number, line) for number, line in body if line]
    if not body or body[0][1].split()[0].lower() not in ("flowchart", "graph"):
        return nodes, edges
    body = [(number, line) for number, line in body if not MERMAID_SKIP.match(line)]
    for number, line in body:
        for match in NODE_OR_LABEL.finditer(line):
            label = (match.group(4) or "").strip()
            if match.group(2) and label and match.group(2) not in nodes:
                nodes[match.group(2)] = (clean(re.sub(r"<br\s*/?>", " ", label, flags=re.I)), number)
    for number, line in body:
        flat = NODE_OR_LABEL.sub(lambda m: m.group(1) or m.group(2), line)
        for edge in EDGE.finditer(flat):
            label = next((edge.group(g) for g in ("l1", "l2", "l3", "l4") if edge.group(g) is not None), "")
            arrow = edge.group("arrow") or ("-.->" if edge.group("l2") else "==>" if edge.group("l4") else "-->")
            for a in re.split(r"\s*&\s*", edge.group("a")):
                for b in re.split(r"\s*&\s*", edge.group("b")):
                    edges.append((a, b, clean(label), arrow, number))
    return nodes, edges


def collect_parts(docs: list[Doc]) -> dict[str, Part]:
    parts: dict[str, Part] = {}

    def add(raw: str, source: str, file: str, line: int) -> None:
        name = part_name(raw)
        if name:
            part = parts.setdefault(norm(name), Part(name, file, line))
            if source not in part.sources:
                part.sources.append(source)

    for doc in docs:
        for block in doc.diagrams:
            for label, number in read_diagram(block)[0].values():
                add(label, "diagram", doc.file, number)
        for unit in doc.units:
            if unit.kind == "row" and unit.header and COMPONENT_HEADER.match(clean(unit.header[0])):
                add(unit.cells[0], "table", doc.file, unit.line)
            elif unit.kind == "item" and (lead := BOLD_LEAD.match(unit.lines[0])):
                add(lead.group(1), "list", doc.file, unit.line)
    for doc in docs:
        for number, _, text in doc.headings:
            name = part_name(HEADING_PREFIX.sub("", text))
            if name and (norm(name) in parts or name.split()[-1].lower() in PART_WORDS):
                add(name, "heading", doc.file, number)
    return parts


# ---------------------------------------------------------------------------- sentences


def coordinated(text: str, mentions: list[Mention], index: int, step: int) -> list[Mention]:
    """The mention at index and the list it ends (step -1) or starts (step +1): "A, B and C".

    A list closes with 'and' or 'or', so "From the Payment provider, the Billing service sets" is no list.
    """
    chain = [mentions[index]]
    closing: list[bool] = []
    i = index
    while 0 <= i + step < len(mentions):
        a, b = (mentions[i + step], mentions[i]) if step < 0 else (mentions[i], mentions[i + step])
        gap = text[a.end : b.start]
        if not (AND_JOINER.fullmatch(gap) or COMMA_JOINER.fullmatch(gap)):
            break
        closing.append(bool(AND_JOINER.fullmatch(gap)))
        i += step
        chain.append(mentions[i])
    if step < 0:
        return chain[::-1] if closing and closing[0] else chain[:1]
    last = max((k for k, joined in enumerate(closing) if joined), default=-1)
    return chain[: last + 2]


def subjects_before(
    text: str, mentions: list[Mention], position: int, objects_of: dict[int, list[Mention]]
) -> list[Mention]:
    """The parts doing the verb at position: the nearest named before it, or, in "X calls Y and writes Z", X."""
    before = [i for i, m in enumerate(mentions) if m.end <= position]
    if not before:
        return []
    nearest = mentions[before[-1]]
    gap = text[nearest.end : position]
    if nearest.start in objects_of and re.search(r"\band\b", gap) and not re.search(r"\b(?:which|that|who)\b", gap):
        return objects_of[nearest.start]
    chain = coordinated(text, mentions, before[-1], -1)
    # "X reads from A, and B polls C": A belongs to the clause before, so B alone does the polling.
    cut = max((k + 1 for k, m in enumerate(chain[:-1]) if m.start in objects_of), default=0)
    return chain[cut:]


def style_of(text: str) -> str:
    sync = bool(SYNC_ACRONYMS.search(text) or SYNC_WORDS.search(text))
    asynchronous = bool(ASYNC_WORDS.search(text))
    if sync == asynchronous:
        return "unknown"
    return "sync" if sync else "async"


def sentence_links(text: str, mentions: list[Mention]) -> list[Link]:
    links: list[Link] = []
    verbs = list(LINK_VERB.finditer(text))
    objects_of: dict[int, list[Mention]] = {}
    for i, verb in enumerate(verbs):
        limit = verbs[i + 1].start() if i + 1 < len(verbs) else len(text)
        subjects = subjects_before(text, mentions, verb.start(), objects_of)
        after = [k for k, m in enumerate(mentions) if verb.end() <= m.start and m.end <= limit]
        if not subjects or not after:
            continue
        names = {s.name for s in subjects}
        chain = coordinated(text, mentions, after[0], 1)
        # A part right before the next verb is that verb's subject, not one more object of this one.
        if i + 1 < len(verbs):
            chain = chain[:1] + [m for m in chain[1:] if not CLAUSE_END.fullmatch(text[m.end : limit])]
        objects = [m for m in chain if m.end <= limit and m.name not in names]
        if not objects:
            continue
        word = verb.group(1).lower().split()[0]
        if word in SYNC_VERBS:
            style = "sync"
        elif word in ASYNC_VERBS:
            style = "async"
        else:
            style = style_of(text[subjects[0].start : limit])
        links.append(Link(verb.group(1), subjects, objects, style))
        for mention in objects:
            objects_of[mention.start] = subjects
    return links


def sentence_writes(text: str, mentions: list[Mention], links: list[Link]) -> list[tuple[str, str, str]]:
    """(entity, part, verb) for "X writes `t`", "X updates `t.c` to ..." and "`t` is written by X"."""
    found: list[tuple[str, str, str]] = []
    objects_of = {m.start: link.subjects for link in links for m in link.objects}
    for verb in WRITE_VERB.finditer(text):
        word = verb.group(1).lower()
        rest = text[verb.end() :]
        if word in PASSIVE and re.match(r"\s+by\b", rest):
            listed = BEFORE_PASSIVE.search(text[: verb.start()])
            after = [i for i, m in enumerate(mentions) if m.start >= verb.end()]
            if not listed or not after:
                continue
            writers = coordinated(text, mentions, after[0], 1)
            entities = ENTITY.findall(listed.group(1))
        else:
            listed = AFTER_VERB.match(rest)
            if not listed:
                continue
            writers = subjects_before(text, mentions, verb.start(), objects_of)
            entities = ENTITY.findall(listed.group(1))
        found.extend((entity, writer.name, word) for entity in entities for writer in writers)
    return found


def row_writes(sentence: Sentence, catalogue: Catalogue) -> list[tuple[str, str, str]]:
    """(entity, part, column) from a table with a 'written by', 'writer' or 'owner' column."""
    columns = [i for i, head in enumerate(sentence.header) if WRITER_HEADER.search(head)]
    found: list[tuple[str, str, str]] = []
    for i in columns:
        if i >= len(sentence.cells):
            continue
        cell = sentence.cells[i]
        verb = sentence.header[i].lower()
        writers = [m.name for m in catalogue.find(cell)]
        others = [c for j, c in enumerate(sentence.cells) if j not in columns]
        if writers:
            entities = ENTITY.findall(others[0]) if others else []
        else:
            entities = ENTITY.findall(cell)
            writers = [m.name for m in catalogue.find(others[0])] if others else []
        found.extend((entity, writer, verb) for entity in entities for writer in writers)
    return found


def numbers_in(text: str) -> list[str]:
    found: list[str] = []
    for pattern in (DURATION, RATE, PERCENTILE):
        for match in pattern.finditer(text):
            value = match.group(0).strip()
            if value not in found:
                found.append(value)
    return found


# ---------------------------------------------------------------------------- ADRs


def first_word(text: str) -> str:
    word = re.split(r"[\s(,;:.]", clean(text).strip(" *_`"), maxsplit=1)[0]
    return word.strip("*_`[]").capitalize()


def refs(line: str) -> list[int]:
    return [int(a or b) for a, b in ADR_REF.findall(line)]


def read_adr(doc: Doc) -> dict[str, Any] | None:
    lines = doc.text.splitlines()
    status: str | None = None
    status_line: int | None = None
    for number, raw in enumerate(lines[:STATUS_LINES], start=1):
        found = STATUS_LINE.match(raw)
        if found:
            status, status_line = found.group(1), number
            break
        if STATUS_HEADING.match(raw.strip()):
            following = next(((n, x.strip()) for n, x in enumerate(lines[number:], number + 1) if x.strip()), None)
            if following:
                status_line, status = following
            break
    named = ADR_NAME.match(PurePosixPath(doc.file).name)
    if not named and status is None:
        return None
    number_of: int | None = int(named.group(1)) if named else None
    if number_of is None:
        titled = refs(doc.title) or [int(n) for n in re.findall(r"^(\d+)\.", doc.title)]
        number_of = titled[0] if titled else None
    supersedes: list[int] = []
    superseded_by: list[int] = []
    for raw in lines:
        by = re.search(r"\bsuperseded by\b", raw, re.I)
        if by:
            superseded_by += refs(raw[by.end() :])
        elif re.search(r"\bsupersedes\b", raw, re.I):
            supersedes += [n for n in refs(raw) if n != number_of]
    supersedes, superseded_by = list(dict.fromkeys(supersedes)), list(dict.fromkeys(superseded_by))
    date = next((m.group(1) for raw in lines[:STATUS_LINES] if (m := DATE_LINE.match(raw))), None)
    return {
        "file": doc.file,
        "line": doc.title_line,
        "number": number_of,
        "title": HEADING_PREFIX.sub("", doc.title) or doc.title,
        "status": first_word(status) if status else None,
        "status_line": status_line,
        "date": date,
        "supersedes": supersedes,
        "superseded_by": superseded_by,
    }


# ---------------------------------------------------------------------------- the inventory


def scan(texts: dict[str, str], skipped: list[str] | None = None) -> dict[str, Any]:
    """The inventory of documents given as {relative path: text}."""
    docs = [parse(file, texts[file]) for file in sorted(texts)]
    parts = collect_parts(docs)
    catalogue = Catalogue([part.name for part in parts.values()])
    for doc in docs:
        for number, raw in doc.lines:
            for mention in catalogue.find(clean(raw)):
                part = parts[norm(mention.name)]
                part.mentions += 1
                part.first = part.first or (doc.file, number)

    adrs = [adr for doc in docs if (adr := read_adr(doc))]
    links: list[dict[str, Any]] = []
    writes: dict[str, dict[str, Any]] = {}
    promises: list[dict[str, Any]] = []
    goals: list[dict[str, Any]] = []
    latencies: list[dict[str, Any]] = []
    open_items: list[dict[str, Any]] = []

    def display(name: str) -> str:
        part = parts.get(norm(name))
        return part.name if part else name

    def add_write(entity: str, part: str, verb: str, file: str, line: int) -> None:
        entry = writes.setdefault(entity, {"entity": entity, "file": file, "line": line, "written_by": [], "where": []})
        if part not in entry["written_by"]:
            entry["written_by"].append(part)
        place = {"part": part, "verb": verb, "file": file, "line": line}
        if place not in entry["where"]:
            entry["where"].append(place)

    for doc in docs:
        for block in doc.diagrams:
            nodes, edges = read_diagram(block)
            for a, b, label, arrow, number in edges:
                links.append(
                    {
                        "from": display(nodes[a][0] if a in nodes else a),
                        "to": display(nodes[b][0] if b in nodes else b),
                        "style": style_of(label),
                        "source": "diagram",
                        "label": label,
                        "arrow": arrow,
                        "file": doc.file,
                        "line": number,
                    }
                )
        for number, _, text in doc.headings:
            if OPEN_MARK.search(text) or OPEN_PHRASE.search(text):
                open_items.append({"file": doc.file, "line": number, "kind": "heading", "text": short(text)})
        for unit in doc.units:
            if unit.kind == "item" and clean(" ".join(unit.lines)).endswith("?"):
                open_items.append(
                    {
                        "file": doc.file,
                        "line": unit.line,
                        "kind": "question",
                        "text": short(clean(" ".join(unit.lines))),
                    }
                )
        for sentence in sentences(doc):
            where = {"file": sentence.file, "line": sentence.line}
            text = sentence.text
            mentions = catalogue.find(text)
            named = list(dict.fromkeys(m.name for m in mentions))
            found_links = sentence_links(text, mentions)
            for link in found_links:
                for subject in link.subjects:
                    for target in link.objects:
                        links.append(
                            {
                                "from": subject.name,
                                "to": target.name,
                                "style": link.style,
                                "source": "text",
                                "verb": link.verb,
                                **where,
                                "text": short(text),
                            }
                        )
            if sentence.kind == "row":
                written = row_writes(sentence, catalogue)
            else:
                written = sentence_writes(text, mentions, found_links)
            for entity, writer, verb in written:
                add_write(entity, writer, verb, sentence.file, sentence.line)
            words = sorted({w.lower().replace("-", " ") for w in PROMISE.findall(text)})
            if words:
                promises.append({**where, "text": short(text), "words": words})
            if QUALITY.search(text):
                numbers = numbers_in(text)
                goals.append({**where, "text": short(text), "has_number": bool(numbers), "numbers": numbers})
            for duration in DURATION.finditer(text):
                latencies.append({**where, "value": duration.group(0).strip(), "text": short(text), "parts": named})
            marks = [m.group(0) for m in [*OPEN_MARK.finditer(text), *OPEN_PHRASE.finditer(text)]]
            if marks:
                open_items.append({**where, "kind": "marker", "text": short(text), "marks": marks})
    for adr in adrs:
        if adr["status"] and adr["status"].lower() in OPEN_STATUSES:
            open_items.append(
                {
                    "file": adr["file"],
                    "line": adr["status_line"],
                    "kind": "adr",
                    "text": f"ADR {adr['number']} {adr['title']}: status {adr['status']}",
                }
            )

    unique_links = list({json.dumps(link, sort_keys=True): link for link in links}.values())
    unique_links.sort(key=lambda link: (link["file"], link["line"]))
    data_writes = []
    for entry in writes.values():
        writers = len(entry["written_by"])
        data_writes.append({**entry, "writers": writers, "shared_write": writers >= 2})
    data_writes.sort(key=lambda entry: (-entry["writers"], entry["entity"]))
    open_items.sort(key=lambda item: (item["file"], item["line"]))
    part_list: list[dict[str, Any]] = []
    for part in sorted(parts.values(), key=lambda p: (-p.mentions, p.name.lower())):
        file, line = part.first or (part.file, part.line)
        part_list.append(
            {"name": part.name, "file": file, "line": line, "mentions": part.mentions, "sources": part.sources}
        )
    return {
        "counts": {
            "documents": len(docs),
            "adrs": len(adrs),
            "parts": len(part_list),
            "links": len(unique_links),
            "links_sync": sum(link["style"] == "sync" for link in unique_links),
            "links_async": sum(link["style"] == "async" for link in unique_links),
            "links_unknown": sum(link["style"] == "unknown" for link in unique_links),
            "data_writes": len(data_writes),
            "shared_writes": sum(entry["shared_write"] for entry in data_writes),
            "promises": len(promises),
            "quality_goals": len(goals),
            "quality_goals_without_number": sum(not goal["has_number"] for goal in goals),
            "latencies": len(latencies),
            "open": len(open_items),
        },
        "note": NOTE,
        "documents": [
            {
                "file": doc.file,
                "line": doc.title_line,
                "title": doc.title,
                "headings": [{"line": n, "level": level, "text": text} for n, level, text in doc.headings],
                "words": doc.words,
            }
            for doc in docs
        ],
        "adrs": adrs,
        "parts": part_list,
        "links": unique_links,
        "data_writes": data_writes,
        "promises": promises,
        "quality_goals": goals,
        "latencies": latencies,
        "open": open_items,
        "skipped": skipped or [],
    }


# ---------------------------------------------------------------------------- files


def is_env(name: str) -> bool:
    return name.lower().startswith(".env")


def collect(paths: list[Path]) -> tuple[list[tuple[str, Path]], list[str]]:
    """The documents under paths, by path relative to the folder they share, and the files left unopened."""
    roots = [Path(os.path.abspath(p)) for p in paths]
    base = Path(os.path.commonpath([str(r if r.is_dir() else r.parent) for r in roots]))
    found: dict[str, Path] = {}
    skipped: set[str] = set()

    def take(path: Path, named: bool) -> None:
        rel = path.relative_to(base).as_posix()
        if is_env(path.name) or is_env(Path(os.path.realpath(path)).name):
            skipped.add(rel)
        elif not path.name.lower().endswith(SUFFIXES):
            if named:
                skipped.add(rel)
        elif path.stat().st_size > MAX_BYTES:
            skipped.add(rel)
        else:
            found[rel] = path

    for root in roots:
        if root.is_dir():
            for current, dirs, names in os.walk(root):
                dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
                for name in sorted(names):
                    take(Path(current) / name, False)
        else:
            take(root, True)
    return sorted(found.items()), sorted(skipped)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="List what a review of design documents should look at.")
    parser.add_argument("paths", nargs="+", type=Path, help="documents, or folders of them")
    args = parser.parse_args(argv)
    missing = [str(p) for p in args.paths if not p.exists()]
    if missing:
        print(f"not found: {', '.join(missing)}", file=sys.stderr)
        return 2
    files, skipped = collect(args.paths)
    texts: dict[str, str] = {}
    for rel, path in files:
        try:
            texts[rel] = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            skipped.append(rel)
    json.dump(scan(texts, sorted(skipped)), sys.stdout, indent=1, ensure_ascii=False)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
