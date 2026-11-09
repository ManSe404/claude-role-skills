#!/usr/bin/env python3
"""Count a folder of documents before deciding how a model should reach them.

Usage: python3 corpus_stats.py FOLDER [--window TOKENS] [--top 10]

Prints JSON: files and bytes per type, characters and an estimated token count, pages of PDFs,
the script of each text (Latin, Serbian Latin, Cyrillic, mixed), byte-identical duplicates, files
it could not read (scanned PDFs, binaries) and when the files last changed (from git when the folder
is in a repository, otherwise from the file times).

The token estimate is rough: characters / 4 for Latin script and / 2.5 for Cyrillic, which most
tokenizers split finer. Count with the model's own tokenizer before a number goes into a quote.
Text comes out of .md, .txt, .html, .csv, .json, .docx and simple PDFs (text operators, plain or
Flate-compressed streams); anything else is counted by size only. Read-only, standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
import zipfile
import zlib
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

TEXT = {".md", ".markdown", ".txt", ".rst", ".csv", ".json", ".yaml", ".yml", ".xml"}
HTML = {".html", ".htm"}
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".mypy_cache", ".pytest_cache"}
CYRILLIC = re.compile(r"[Ѐ-ӿ]")
LATIN = re.compile(r"[A-Za-zÀ-ɏ]")
SERBIAN_LATIN = re.compile(r"[čćšžđČĆŠŽĐ]")
PDF_PAGE = re.compile(rb"/Type\s*/Page(?![a-zA-Z])")
PDF_STREAM = re.compile(rb"<<(.*?)>>\s*stream\r?\n(.*?)\r?\nendstream", re.S)
PDF_TEXT = re.compile(rb"\((.*?)(?<!\\)\)\s*(?:Tj|')|\[(.*?)\]\s*TJ", re.S)
PDF_STRING = re.compile(rb"\((.*?)(?<!\\)\)", re.S)


def _pdf(data: bytes) -> tuple[str, int]:
    """The text of the text operators in a PDF, and its page count. Good enough to size a corpus, not to read it."""
    pages = len(PDF_PAGE.findall(data))
    chunks: list[str] = []
    for header, body in PDF_STREAM.findall(data):
        if b"FlateDecode" in header:
            try:
                body = zlib.decompress(body)
            except zlib.error:
                continue
        for single, array in PDF_TEXT.findall(body):
            parts = [single] if single else PDF_STRING.findall(array)
            for part in parts:
                text = part.replace(rb"\(", b"(").replace(rb"\)", b")").replace(rb"\\", b"\\")
                chunks.append(text.decode("latin-1"))
    return " ".join(chunks), pages


def _docx(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml").decode("utf-8", errors="replace")
    return re.sub(r"<[^>]+>", " ", xml.replace("</w:p>", "\n"))


def read_text(path: Path, data: bytes) -> tuple[str | None, int | None]:
    """The text of a file and, for a PDF, its pages. None when the type is not read."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _pdf(data)
    if suffix == ".docx":
        try:
            return _docx(path), None
        except (zipfile.BadZipFile, KeyError):
            return None, None
    if suffix in TEXT or suffix in HTML:
        text = data.decode("utf-8", errors="replace")
        if suffix in HTML:
            text = re.sub(r"<(script|style)\b.*?</\1>|<[^>]+>", " ", text, flags=re.S | re.I)
        return text, None
    return None, None


def script_of(text: str) -> str:
    cyr, lat = len(CYRILLIC.findall(text)), len(LATIN.findall(text))
    if not cyr and not lat:
        return "none"
    if cyr and lat and min(cyr, lat) / (cyr + lat) > 0.2:
        return "mixed"
    if cyr > lat:
        return "cyrillic"
    return "serbian latin" if SERBIAN_LATIN.search(text) else "latin"


def tokens_of(text: str) -> int:
    cyr = len(CYRILLIC.findall(text))
    return math.ceil((len(text) - cyr) / 4 + cyr / 2.5)


def _changes(folder: Path) -> dict[str, str]:
    """Last commit date per file under folder, when the folder is in a git repository."""
    try:
        top = subprocess.run(
            ["git", "-C", str(folder), "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=30
        )
        if top.returncode:
            return {}
        log = subprocess.run(
            ["git", "-C", str(folder), "log", "--format=@%cI", "--name-only", "--", "."],
            capture_output=True,
            text=True,
            timeout=60,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return {}
    root = Path(top.stdout.strip())
    seen: dict[str, str] = {}
    stamp = ""
    for line in log.splitlines():
        if line.startswith("@"):
            stamp = line[1:]
        elif line.strip():
            rel = (root / line).resolve()
            try:
                key = rel.relative_to(folder.resolve()).as_posix()
            except ValueError:
                continue
            seen.setdefault(key, stamp)  # newest first
    return seen


def stats(folder: Path, window: int | None, top: int) -> dict[str, Any]:
    files = sorted(
        p
        for p in folder.rglob("*")
        if p.is_file() and not any(part in SKIP_DIRS for part in p.relative_to(folder).parts)
    )
    git_dates = _changes(folder)
    rows = []
    by_hash: dict[str, list[str]] = defaultdict(list)
    for path in files:
        rel = path.relative_to(folder).as_posix()
        data = path.read_bytes()
        by_hash[hashlib.sha256(data).hexdigest()].append(rel)
        text, pages = read_text(path, data)
        changed = git_dates.get(rel) or datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(timespec="seconds")
        row: dict[str, Any] = {
            "path": rel,
            "type": path.suffix.lower().lstrip(".") or "(none)",
            "bytes": len(data),
            "changed": changed,
            "changed_from": "git" if rel in git_dates else "file time",
        }
        if text is None:
            row["read"] = False
        else:
            body = re.sub(r"\s+", " ", text).strip()
            row.update(read=True, chars=len(body), tokens_est=tokens_of(body), script=script_of(body))
            if pages is not None:
                row["pages"] = pages
                if len(body) < 200 * max(pages, 1) / 4:
                    row["note"] = "little text per page: scanned or image-only, needs OCR before anyone can search it"
        rows.append(row)
    read = [r for r in rows if r["read"]]
    total_tokens = sum(r["tokens_est"] for r in read)
    dates = sorted(r["changed"] for r in rows)
    by_type: dict[str, dict[str, int]] = {}
    for r in rows:
        entry = by_type.setdefault(r["type"], {"files": 0, "bytes": 0})
        entry["files"] += 1
        entry["bytes"] += r["bytes"]
    result: dict[str, Any] = {
        "folder": str(folder),
        "files": len(rows),
        "bytes": sum(r["bytes"] for r in rows),
        "by_type": dict(sorted(by_type.items())),
        "read": len(read),
        "not_read": [r["path"] for r in rows if not r["read"]],
        "chars": sum(r["chars"] for r in read),
        "tokens_est": total_tokens,
        "pdf_pages": sum(r.get("pages", 0) for r in rows),
        "scripts": dict(Counter(r["script"] for r in read).most_common()),
        "needs_ocr": [r["path"] for r in rows if "note" in r],
        "duplicates": [sorted(group) for group in by_hash.values() if len(group) > 1],
        "changed": {"first": dates[0] if dates else None, "last": dates[-1] if dates else None},
        "largest": [
            {"path": r["path"], "tokens_est": r["tokens_est"]}
            for r in sorted(read, key=lambda r: -r["tokens_est"])[:top]
        ],
        "files_detail": rows,
        "note": "tokens_est is chars/4 (Latin) and chars/2.5 (Cyrillic): a size, not a bill. Count with the "
        "model's tokenizer before quoting.",
    }
    if window:
        result["window"] = {"tokens": window, "fits": total_tokens <= window, "share": round(total_tokens / window, 3)}
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Count a folder of documents: types, tokens, scripts, duplicates.")
    parser.add_argument("folder", type=Path)
    parser.add_argument("--window", type=int, help="tokens one call may carry, to say whether everything fits")
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args(argv)
    if not args.folder.is_dir():
        print(f"{args.folder}: not a folder", file=sys.stderr)
        return 2
    json.dump(stats(args.folder.resolve(), args.window, args.top), sys.stdout, indent=1, ensure_ascii=False)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
