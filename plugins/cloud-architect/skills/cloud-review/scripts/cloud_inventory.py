#!/usr/bin/env python3
"""Read a repository's cloud infrastructure code into one normalised inventory.

Usage: python3 cloud_inventory.py REPO [--compare EXPORT.json] [--checks]
       python3 cloud_inventory.py --from-export EXPORT.json

Reads Terraform (resource, data, module with local sources, attributes, references), Bicep (resource,
module, parent, nested properties), ARM JSON and CloudFormation (JSON, or YAML with its short tags). Each
resource becomes one row: id, provider, type, category, name, file, line, nesting, location, the attributes
that matter and its references to other resources. What the code does not say is reported, not guessed:
count, for_each, loops, conditions, dynamic names, macros, nested stacks, remote modules and unknown
resource types are listed under `unresolved`.

Everything provider-specific lives in cloud/<provider>.json beside this file (references/cloud/ in a
skill): resource types, placement, exposure rules, review checks. To add a provider, add a file.

--compare adds drift against a saved export from the provider's read-only listing command (the provider
file says which). --from-export reads an export instead of code. --checks adds review hits per family,
each with the pillar it belongs to. A hit is a place to read, not a finding.

`*.tfvars`, `*.tfstate` and parameter files are never opened: real values and secrets live there. Values
that look like secrets are replaced by a marker. Read-only, standard library only, JSON on stdout. It
never calls a cloud or the network.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import re
import sys
from collections import Counter, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MISSING: Any = object()
SECRET_MARK = "<hidden: looks like a secret>"
SKIP_DIRS = {
    ".git",
    ".terraform",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
    "target",
    "bin",
    "obj",
}
NOT_READ_SUFFIXES = (
    ".tfvars",
    ".tfvars.json",
    ".tfstate",
    ".tfstate.backup",
    ".bicepparam",
    "parameters.json",
    "params.json",
)
TEMPLATE_SUFFIXES = (".json", ".yaml", ".yml", ".template")
FORMAT_KEYS = {"terraform": "tf", "cloudformation": "cfn"}
CATEGORIES = ["compute", "database", "storage", "network", "edge", "identity", "secrets", "messaging", "monitoring"]

SECRET_NAME = re.compile(
    r"(?i)(pass(word|wd|phrase)?|pwd|secret|token|api[_-]?key|access[_-]?key|auth[_-]?key|account[_-]?key|"
    r"shared[_-]?key|client[_-]?secret|credential|private[_-]?key|signing[_-]?key|encryption[_-]?key|"
    r"connection[_-]?str|(^|[_.-])sas([_.-]|$))"
)
SECRET_VALUE = [
    re.compile(
        r"(?i)(password|passwd|pwd|secret|token|apikey|api[_-]?key|accountkey|sharedaccesskey|sharedaccesssignature|sig)=[^;\s\"']+"
    ),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}"),
    re.compile(r"(?i)passw|secret"),
]
LONG_RANDOM = re.compile(r"^[A-Za-z0-9+/=_-]{32,}$")


# ---------------------------------------------------------------------------- lexing


class ParseError(Exception):
    def __init__(self, line: int, message: str) -> None:
        super().__init__(f"line {line}: {message}")
        self.line = line


@dataclass
class Interp:
    source: str | None  # None marks an HCL template directive (%{ ... }), which is never expanded
    line: int


@dataclass
class Tok:
    kind: str  # id, num, str, op, nl, eof
    text: Any
    line: int


OPS = sorted(
    [
        "...",
        "=>",
        "==",
        "!=",
        "<=",
        ">=",
        "&&",
        "||",
        "??",
        "?.",
        "{",
        "}",
        "[",
        "]",
        "(",
        ")",
        "=",
        ":",
        ",",
        ".",
        "?",
        "!",
        "+",
        "-",
        "*",
        "/",
        "%",
        "<",
        ">",
        "@",
    ],
    key=len,
    reverse=True,
)
ID_HCL = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")
ID_BICEP = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
NUMBER = re.compile(r"\d+(\.\d+)?([eE][+-]?\d+)?")
HEREDOC = re.compile(r"<<-?([A-Za-z_][A-Za-z0-9_]*)[ \t]*\n")


def _string_end(src: str, start: int, quote: str, dialect: str) -> tuple[list[str | Interp], int, int]:
    """Read a quoted string at start (just after the quote): its parts, the index after it, and newlines crossed."""
    parts: list[str | Interp] = []
    buf: list[str] = []
    i, n, newlines = start, len(src), 0
    while i < n:
        c = src[i]
        if c == quote:
            if buf:
                parts.append("".join(buf))
            return parts, i + 1, newlines
        if c == "\\" and i + 1 < n:
            escapes = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "'": "'", "\\": "\\", "$": "$"}
            buf.append(escapes.get(src[i + 1], "\\" + src[i + 1]))
            i += 2
            continue
        if c == "\n":
            if dialect == "hcl":
                raise ParseError(0, "newline in a quoted string")
            newlines += 1
        if c in "$%" and src.startswith("{", i + 1) and not (i > start and src[i - 1] == c):
            depth, j = 1, i + 2
            in_string: str | None = None
            while j < n and depth:
                ch = src[j]
                if in_string:
                    if ch == "\\":
                        j += 1
                    elif ch == in_string:
                        in_string = None
                elif ch == quote:
                    in_string = ch
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                elif ch == "\n":
                    newlines += 1
                j += 1
            if depth:
                raise ParseError(0, "an interpolation is not closed")
            if buf:
                parts.append("".join(buf))
                buf = []
            parts.append(Interp(src[i + 2 : j - 1] if c == "$" else None, newlines))
            i = j
            continue
        buf.append(c)
        i += 1
    raise ParseError(0, "a string is not closed")


def lex(src: str, dialect: str, start_line: int = 1) -> list[Tok]:
    toks: list[Tok] = []
    i, n, line = 0, len(src), start_line
    id_re = ID_HCL if dialect == "hcl" else ID_BICEP
    while i < n:
        c = src[i]
        if c == "\n":
            toks.append(Tok("nl", "\n", line))
            line += 1
            i += 1
        elif c in " \t\r":
            i += 1
        elif src.startswith("//", i) or c == "#":
            end = src.find("\n", i)
            i = n if end < 0 else end
        elif src.startswith("/*", i):
            end = src.find("*/", i + 2)
            if end < 0:
                raise ParseError(line, "a comment is not closed")
            line += src.count("\n", i, end)
            i = end + 2
        elif dialect == "bicep" and src.startswith("'''", i):
            end = src.find("'''", i + 3)
            if end < 0:
                raise ParseError(line, "a multi-line string is not closed")
            body = src[i + 3 : end]
            line += body.count("\n")
            toks.append(Tok("str", [body], line))
            i = end + 3
        elif dialect == "hcl" and c == '"':
            start = line
            try:
                parts, i, crossed = _string_end(src, i + 1, '"', dialect)
            except ParseError as exc:
                raise ParseError(start, str(exc)) from exc
            line += crossed
            toks.append(Tok("str", _rebase(parts, start), start))
        elif dialect == "bicep" and c == "'":
            start = line
            try:
                parts, i, crossed = _string_end(src, i + 1, "'", dialect)
            except ParseError as exc:
                raise ParseError(start, str(exc)) from exc
            line += crossed
            toks.append(Tok("str", _rebase(parts, start), start))
        else:
            heredoc = HEREDOC.match(src, i) if dialect == "hcl" else None
            if heredoc:
                marker = heredoc.group(1)
                body_start = heredoc.end()
                match = re.compile(rf"^[ \t]*{re.escape(marker)}[ \t]*$", re.MULTILINE).search(src, body_start)
                if not match:
                    raise ParseError(line, f"heredoc {marker} is not closed")
                body = src[body_start : match.start()]
                toks.append(Tok("str", [body], line))
                line += body.count("\n") + 2
                i = match.end()
                if i < n and src[i] == "\n":
                    i += 1
                continue
            num = NUMBER.match(src, i)
            if num:
                text = num.group(0)
                value: float | int = float(text) if any(ch in text for ch in ".eE") else int(text)
                toks.append(Tok("num", value, line))
                i = num.end()
                continue
            word = id_re.match(src, i)
            if word:
                toks.append(Tok("id", word.group(0), line))
                i = word.end()
                continue
            for op in OPS:
                if src.startswith(op, i):
                    toks.append(Tok("op", op, line))
                    i += len(op)
                    break
            else:
                raise ParseError(line, f"unexpected character {c!r}")
    toks.append(Tok("eof", "", line))
    return toks


def _rebase(parts: list[str | Interp], start: int) -> list[str | Interp]:
    return [Interp(p.source, start + p.line) if isinstance(p, Interp) else p for p in parts]


# ---------------------------------------------------------------------------- parsing


@dataclass
class Lit:
    value: Any


@dataclass
class Tmpl:
    parts: list[str | Node | None]


@dataclass
class Ref:
    base: str | Call
    parts: list[str | Node]
    line: int = 0


@dataclass
class ListE:
    items: list[Node]


@dataclass
class ObjE:
    items: list[tuple[str, Node, int]]
    decls: list[BicepResource] = field(default_factory=list)


@dataclass
class Call:
    name: str
    args: list[Node]
    line: int = 0


@dataclass
class Op:
    op: str
    args: list[Node]


@dataclass
class ForE:
    parts: list[Node]


Node = Lit | Tmpl | Ref | ListE | ObjE | Call | Op | ForE

PRECEDENCE = {
    "||": 1,
    "??": 1,
    "&&": 2,
    "==": 3,
    "!=": 3,
    "<": 4,
    ">": 4,
    "<=": 4,
    ">=": 4,
    "+": 5,
    "-": 5,
    "*": 6,
    "/": 6,
    "%": 6,
}


@dataclass
class Attr:
    expr: Node
    line: int


@dataclass
class Block:
    type: str
    labels: list[str]
    body: Body
    line: int


@dataclass
class Body:
    attrs: dict[str, Attr] = field(default_factory=dict)
    blocks: list[Block] = field(default_factory=list)


@dataclass
class BicepResource:
    symbol: str
    type: str
    existing: bool
    conditional: bool
    body: Node
    line: int


@dataclass
class BicepModule:
    symbol: str
    path: str
    conditional: bool
    body: Node
    line: int


@dataclass
class BicepAst:
    target_scope: str = "resourceGroup"
    params: dict[str, Attr] = field(default_factory=dict)
    vars: dict[str, Attr] = field(default_factory=dict)
    outputs: dict[str, Attr] = field(default_factory=dict)
    resources: list[BicepResource] = field(default_factory=list)
    modules: list[BicepModule] = field(default_factory=list)


class Parser:
    def __init__(self, toks: list[Tok], dialect: str) -> None:
        self.toks = toks
        self.pos = 0
        self.dialect = dialect
        self.depth = 0  # inside brackets a newline means nothing

    def peek(self) -> Tok:
        while self.depth and self.toks[self.pos].kind == "nl":
            self.pos += 1
        return self.toks[self.pos]

    def take(self) -> Tok:
        token = self.peek()
        self.pos += 1
        return token

    def skip_nl(self) -> None:
        while self.toks[self.pos].kind == "nl":
            self.pos += 1

    def at_op(self, text: str) -> bool:
        token = self.peek()
        return token.kind == "op" and token.text == text

    def at_id(self, text: str) -> bool:
        token = self.peek()
        return token.kind == "id" and token.text == text

    def accept(self, text: str) -> bool:
        if self.at_op(text):
            self.pos += 1
            return True
        return False

    def expect(self, text: str) -> Tok:
        token = self.take()
        if token.kind != "op" or token.text != text:
            raise ParseError(token.line, f"expected {text!r}, found {token.text!r}")
        return token

    def expr(self) -> Node:
        left = self._binary(1)
        if self.accept("?"):
            yes = self.expr()
            self.expect(":")
            return Op("?", [left, yes, self.expr()])
        return left

    def _binary(self, minimum: int) -> Node:
        left = self._unary()
        while True:
            token = self.peek()
            if token.kind != "op" or token.text not in PRECEDENCE or PRECEDENCE[token.text] < minimum:
                return left
            self.pos += 1
            left = Op(token.text, [left, self._binary(PRECEDENCE[token.text] + 1)])

    def _unary(self) -> Node:
        token = self.peek()
        if token.kind == "op" and token.text in ("!", "-"):
            self.pos += 1
            return Op(token.text, [self._unary()])
        return self._postfix()

    def _postfix(self) -> Node:
        node = self._primary()
        while True:
            token = self.peek()
            if token.kind == "op" and token.text in (".", "?."):
                self.pos += 1
                part = self.take()
                if part.kind in ("id", "num"):
                    node = _attach(node, str(part.text))
                elif part.kind == "op" and part.text == "*":
                    node = _attach(node, "*")
                else:
                    raise ParseError(part.line, f"unexpected {part.text!r} after a dot")
            elif token.kind == "op" and token.text == "[":
                self.pos += 1
                self.depth += 1
                index: str | Node = "*" if self.accept("*") else self.expr()
                self.expect("]")
                self.depth -= 1
                node = _attach(node, index)
            elif token.kind == "op" and token.text == "(":
                if not isinstance(node, Ref):
                    raise ParseError(token.line, "only a name can be called")
                self.pos += 1
                self.depth += 1
                args = []
                while not self.at_op(")"):
                    if self.accept(","):
                        continue
                    args.append(self.expr())
                self.expect(")")
                self.depth -= 1
                name = ".".join(
                    [node.base if isinstance(node.base, str) else node.base.name, *[str(p) for p in node.parts]]
                )
                node = Ref(Call(name, args, token.line), [], token.line)
            elif token.kind == "op" and token.text == "!" and self.dialect == "bicep":
                self.pos += 1
            else:
                return node

    def _primary(self) -> Node:
        token = self.take()
        if token.kind == "num":
            return Lit(token.text)
        if token.kind == "str":
            return self._template(token)
        if token.kind == "id":
            literal = {"true": True, "false": False, "null": None}
            if token.text in literal:
                return Lit(literal[token.text])
            return Ref(token.text, [], token.line)
        if token.kind == "op" and token.text == "(":
            self.depth += 1
            inner = self.expr()
            self.expect(")")
            self.depth -= 1
            return inner
        if token.kind == "op" and token.text == "[":
            return self._list()
        if token.kind == "op" and token.text == "{":
            return self._object()
        raise ParseError(token.line, f"unexpected {token.text!r}")

    def _template(self, token: Tok) -> Node:
        parts: list[str | Node | None] = []
        for part in token.text:
            if isinstance(part, str):
                parts.append(part)
            elif part.source is None:
                parts.append(None)
            else:
                sub = Parser(lex(part.source, self.dialect, part.line), self.dialect)
                sub.depth = 1
                parts.append(sub.expr())
        if all(isinstance(p, str) for p in parts):
            return Lit("".join(p for p in parts if isinstance(p, str)))
        return Tmpl(parts)

    def _list(self) -> Node:
        self.depth += 1
        if self.at_id("for"):
            node = self._for("]")
            self.depth -= 1
            return node
        items: list[Node] = []
        while not self.at_op("]"):
            if self.accept(","):
                continue
            items.append(self.expr())
        self.expect("]")
        self.depth -= 1
        return ListE(items)

    def _for(self, close: str) -> Node:
        self.pos += 1
        while not self.at_id("in"):
            self.take()
        self.take()
        parts = [self.expr()]
        self.expect(":")
        parts.append(self.expr())
        if self.accept("=>"):
            parts.append(self.expr())
        self.accept("...")
        if self.at_id("if"):
            self.take()
            parts.append(self.expr())
        self.expect(close)
        return ForE(parts)

    def _object(self) -> Node:
        self.depth += 1
        if self.at_id("for"):
            node = self._for("}")
            self.depth -= 1
            return node
        obj = ObjE([])
        while True:
            token = self.peek()
            if token.kind == "op" and token.text == "}":
                self.pos += 1
                break
            if self.accept(","):
                continue
            if self.dialect == "bicep" and token.kind == "op" and token.text == "@":
                self._decorator()
                continue
            if self.dialect == "bicep" and token.kind == "id" and token.text == "resource":
                self.pos += 1
                obj.decls.append(self._bicep_resource(token.line))
                continue
            key, line = self._key()
            if not (self.accept("=") or self.accept(":")):
                raise ParseError(line, "expected = or : after an object key")
            obj.items.append((key, self.expr(), line))
        self.depth -= 1
        return obj

    def _key(self) -> tuple[str, int]:
        token = self.take()
        if token.kind == "id":
            return token.text, token.line
        if token.kind == "num":
            return str(token.text), token.line
        if token.kind == "str":
            return "".join(p if isinstance(p, str) else "?" for p in token.text), token.line
        if token.kind == "op" and token.text == "(":
            self.depth += 1
            self.expr()
            self.expect(")")
            self.depth -= 1
            return "(expr)", token.line
        raise ParseError(token.line, f"unexpected object key {token.text!r}")

    def hcl_body(self, closing: bool) -> Body:
        body = Body()
        while True:
            self.skip_nl()
            token = self.peek()
            if token.kind == "op" and token.text == "}" and closing:
                self.pos += 1
                return body
            if token.kind == "eof":
                if closing:
                    raise ParseError(token.line, "a block is not closed")
                return body
            if token.kind != "id":
                raise ParseError(token.line, f"expected a name, found {token.text!r}")
            self.pos += 1
            if self.at_op("="):
                self.pos += 1
                body.attrs[token.text] = Attr(self.expr(), token.line)
                continue
            labels = []
            while True:
                label = self.peek()
                if label.kind == "str":
                    labels.append("".join(p for p in label.text if isinstance(p, str)))
                    self.pos += 1
                elif label.kind == "id":
                    labels.append(label.text)
                    self.pos += 1
                else:
                    break
            self.expect("{")
            body.blocks.append(Block(token.text, labels, self.hcl_body(True), token.line))

    def _decorator(self) -> None:
        self.expect("@")
        self.expr()

    def _skip_statement(self) -> None:
        while self.toks[self.pos].kind not in ("nl", "eof"):
            self.pos += 1

    def _skip_type(self) -> None:
        depth = 0
        while True:
            token = self.toks[self.pos]
            if token.kind == "eof" or (token.kind == "nl" and not depth):
                return
            if token.kind == "op" and token.text == "=" and not depth:
                return
            if token.kind == "op" and token.text in "([{":
                depth += 1
            elif token.kind == "op" and token.text in ")]}":
                depth -= 1
            self.pos += 1

    def _string_value(self, token: Tok) -> str:
        if token.kind != "str" or not all(isinstance(p, str) for p in token.text):
            raise ParseError(token.line, "expected a plain string")
        return "".join(token.text)

    def _bicep_resource(self, line: int) -> BicepResource:
        symbol = self.take()
        rtype = self._string_value(self.take())
        existing = False
        if self.at_id("existing"):
            self.take()
            existing = True
        self.expect("=")
        conditional = False
        if self.at_id("if"):
            self.take()
            conditional = True
            self.expect("(")
            self.depth += 1
            self.expr()
            self.expect(")")
            self.depth -= 1
        return BicepResource(symbol.text, rtype, existing, conditional, self.expr(), line)

    def bicep_file(self) -> BicepAst:
        ast = BicepAst()
        while True:
            self.skip_nl()
            token = self.peek()
            if token.kind == "eof":
                return ast
            if token.kind == "op" and token.text == "@":
                self._decorator()
                continue
            if token.kind != "id":
                raise ParseError(token.line, f"expected a statement, found {token.text!r}")
            word = token.text
            self.pos += 1
            if word == "targetScope":
                self.expect("=")
                scope = self.take()
                ast.target_scope = self._string_value(scope)
            elif word == "param":
                name = self.take().text
                self._skip_type()
                ast.params[name] = Attr(self.expr() if self.accept("=") else Lit(MISSING), token.line)
            elif word == "var":
                name = self.take().text
                self.expect("=")
                ast.vars[name] = Attr(self.expr(), token.line)
            elif word == "output":
                name = self.take().text
                self._skip_type()
                if self.accept("="):
                    ast.outputs[name] = Attr(self.expr(), token.line)
            elif word == "resource":
                ast.resources.append(self._bicep_resource(token.line))
            elif word == "module":
                symbol = self.take().text
                path = self._string_value(self.take())
                self.expect("=")
                conditional = False
                if self.at_id("if"):
                    self.take()
                    conditional = True
                    self.expect("(")
                    self.depth += 1
                    self.expr()
                    self.expect(")")
                    self.depth -= 1
                ast.modules.append(BicepModule(symbol, path, conditional, self.expr(), token.line))
            elif word in ("import", "using", "extension", "provider", "metadata", "type", "func", "existing"):
                self._skip_statement()
            else:
                raise ParseError(token.line, f"unknown statement {word!r}")


def _attach(node: Node, part: str | Node) -> Node:
    if isinstance(node, Ref):
        return Ref(node.base, [*node.parts, part], node.line)
    raise ParseError(0, "only a name can have a property")


# ---------------------------------------------------------------------------- evaluation


@dataclass
class Unknown:
    text: str
    literal: str = ""  # the literal text mixed into an unknown value; used only to detect secrets, never printed

    def __str__(self) -> str:
        return f"<unknown: {self.text}>"


@dataclass
class Rec:
    """Collects the references made while one attribute is evaluated."""

    refs: list[dict[str, Any]] = field(default_factory=list)
    via: str = ""
    line: int = 0

    def add(self, to: str) -> None:
        self.refs.append({"to": to, "via": self.via, "line": self.line})


def _node_text(node: Node) -> str:
    """A short form for the output: never the literal text, which could be a value."""
    if isinstance(node, Lit):
        return "…" if isinstance(node.value, str) else str(node.value)
    if isinstance(node, Ref):
        head = node.base if isinstance(node.base, str) else f"{node.base.name}(…)"
        return ".".join([head, *[p if isinstance(p, str) else "[…]" for p in node.parts]])
    if isinstance(node, Call):
        return f"{node.name}(…)"
    if isinstance(node, Tmpl):
        return "template with " + ", ".join(
            _node_text(p) for p in node.parts if isinstance(p, Lit | Ref | Call | Op | ForE)
        )
    if isinstance(node, ListE):
        return "[…]"
    if isinstance(node, ObjE):
        return "{…}"
    return "expression"


def _literals(values: list[Any]) -> str:
    return "".join(v.literal if isinstance(v, Unknown) else str(v) for v in values if isinstance(v, str | Unknown))


FUNCTIONS: dict[str, Any] = {
    "lower": lambda a: a[0].lower(),
    "toLower": lambda a: a[0].lower(),
    "upper": lambda a: a[0].upper(),
    "toUpper": lambda a: a[0].upper(),
    "tostring": lambda a: str(a[0]),
    "string": lambda a: str(a[0]),
    "tonumber": lambda a: float(a[0]),
    "int": lambda a: int(a[0]),
    "toset": lambda a: list(a[0]),
    "tolist": lambda a: list(a[0]),
    "join": lambda a: a[0].join(str(x) for x in a[1]),
    "replace": lambda a: a[0].replace(a[1], a[2]),
    "concat": lambda a: _concat(a),
    "substr": lambda a: a[0][a[1] : a[1] + a[2]],
    "substring": lambda a: a[0][a[1] : a[1] + a[2]],
    "take": lambda a: a[0][: a[1]],
    "coalesce": lambda a: next(x for x in a if x not in (None, "")),
    "jsonencode": lambda a: a[0],
    "merge": lambda a: {k: v for item in a for k, v in item.items()},
}


def _concat(args: list[Any]) -> Any:
    """String concat in ARM and Bicep, list concat in Terraform: the arguments say which."""
    if all(isinstance(x, str | int | float) for x in args):
        return "".join(str(x) for x in args)
    return [item for arg in args for item in arg]


def _format(args: list[Any]) -> str:
    template = str(args[0])
    if "%" in template:
        return _format_hcl(template, args[1:])
    return re.sub(r"\{(\d+)\}", lambda m: str(args[1 + int(m.group(1))]), template)


def _format_hcl(template: str, values: list[Any]) -> str:
    out, index = [], 0
    for piece in re.split(r"(%%|%[-+#0 ]*\d*(?:\.\d+)?[a-zA-Z])", template):
        if piece == "%%":
            out.append("%")
        elif piece.startswith("%") and len(piece) > 1:
            out.append(str(values[index]))
            index += 1
        else:
            out.append(piece)
    return "".join(out)


FUNCTIONS["format"] = _format


class Scope:
    def eval(self, node: Node, rec: Rec) -> Any:
        if isinstance(node, Lit):
            return node.value
        if isinstance(node, Tmpl):
            return self._template(node, rec)
        if isinstance(node, ListE):
            return [self.eval(item, rec) for item in node.items]
        if isinstance(node, ObjE):
            return {key: self.eval(value, rec) for key, value, _ in node.items}
        if isinstance(node, Op):
            return self._op(node, rec)
        if isinstance(node, ForE):
            for part in node.parts:
                self.eval(part, rec)
            return Unknown("for expression")
        if isinstance(node, Call):
            return self.call(node, rec)
        if isinstance(node.base, Call) and not node.parts:
            return self.call(node.base, rec)
        return self.ref(node, rec)

    def _template(self, node: Tmpl, rec: Rec) -> Any:
        values: list[Any] = []
        for part in node.parts:
            if part is None:
                values.append(Unknown("template directive"))
            elif isinstance(part, str):
                values.append(part)
            else:
                values.append(self.eval(part, rec))
        unknown = [v for v in values if isinstance(v, Unknown)]
        if unknown:
            return Unknown(", ".join(u.text for u in unknown), _literals(values))
        return "".join(str(v) for v in values)

    def _op(self, node: Op, rec: Rec) -> Any:
        args = [self.eval(a, rec) for a in node.args]
        if node.op == "?":
            if isinstance(args[0], Unknown):
                return Unknown("conditional")
            return args[1] if args[0] else args[2]
        if any(isinstance(a, Unknown) for a in args):
            return Unknown(f"expression using {args[0].text if isinstance(args[0], Unknown) else '…'}")
        try:
            if node.op == "==":
                return args[0] == args[1]
            if node.op == "!=":
                return args[0] != args[1]
            if node.op == "&&":
                return args[0] and args[1]
            if node.op == "||":
                return args[0] or args[1]
            if node.op == "!":
                return not args[0]
            if node.op == "-" and len(args) == 1:
                return -args[0]
            if node.op == "??":
                return args[0] if args[0] is not None else args[1]
        except TypeError:
            pass
        return Unknown(f"{node.op} expression")

    def call(self, node: Call, rec: Rec) -> Any:
        name = node.name.split(".")[-1]
        args = [self.eval(a, rec) for a in node.args]
        function = FUNCTIONS.get(name)
        if function and not any(isinstance(a, Unknown) for a in args):
            try:
                return function(args)
            except (TypeError, ValueError, IndexError, KeyError, StopIteration):
                pass
        return Unknown(f"{name}(…)", _literals(args))

    def ref(self, node: Ref, rec: Rec) -> Any:
        raise NotImplementedError


def _walk(node: Any, parts: list[str], prefix: str = "") -> list[tuple[Any, str]]:
    """Every value at a dotted path, with the concrete path of each. `[*]` walks a list; a single block counts
    as a list of one, and a repeated block needs no `[*]`."""
    if not parts:
        return [(node, prefix)]
    if isinstance(node, list):
        out: list[tuple[Any, str]] = []
        for index, item in enumerate(node):
            out += _walk(item, parts, f"{prefix}[{index}]")
        return out
    head = parts[0]
    star = head.endswith("[*]")
    key = head.removesuffix("[*]")
    if not isinstance(node, dict) or key not in node:
        return []
    path = f"{prefix}.{key}" if prefix else key
    value = node[key]
    if star and isinstance(value, list):
        out = []
        for index, item in enumerate(value):
            out += _walk(item, parts[1:], f"{path}[{index}]")
        return out
    return _walk(value, parts[1:], path)


# ---------------------------------------------------------------------------- readers: Terraform, Bicep, ARM


@dataclass
class Raw:
    rid: str
    fmt: str  # terraform, bicep, arm, export
    source_type: str
    name: Any
    file: str
    line: int
    tree: dict[str, Any]
    lines: dict[str, int]
    refs: list[dict[str, Any]]
    mode: str = "managed"  # managed, or data for something read but not created here
    module: str = ""
    repeated: str = ""
    conditional: bool = False
    parent: str | None = None
    scope_rg: str | None = None
    scope_rg_id: str | None = None
    scope: dict[str, Any] = field(default_factory=dict)  # nesting levels the code states directly


class TfModule(Scope):
    """One instance of a Terraform module: a directory of .tf files with its inputs."""

    def __init__(self, inv: Inventory, directory: Path, address: str, inputs: dict[str, tuple[Node, TfModule]]) -> None:
        self.inv = inv
        self.directory = directory
        self.address = address  # "" or "module.a." ; the prefix of every id in this instance
        self.inputs = inputs
        self.variables: dict[str, Block] = {}
        self.locals: dict[str, Attr] = {}
        self.resources: dict[str, Block] = {}
        self.datas: dict[str, Block] = {}
        self.outputs: dict[str, Attr] = {}
        self.modules: dict[str, TfModule] = {}
        self.module_blocks: dict[str, Block] = {}
        self.scope: dict[str, Any] = {}
        self.aliased: dict[str, dict[str, Any]] = {}

    def load(self) -> None:
        for path in sorted(self.directory.glob("*.tf")):
            body = self.inv.parse_hcl(path)
            if body is None:
                continue
            rel = self.inv.rel(path)
            if rel not in self.inv.files["terraform"]:
                self.inv.files["terraform"].append(rel)
            for block in body.blocks:
                self.inv.block_file[id(block)] = rel
                self._add(block)
        for name, block in self.module_blocks.items():
            source_attr = block.body.attrs.get("source")
            source = self.eval(source_attr.expr, Rec()) if source_attr else None
            location = self.inv.block_file[id(block)]
            prefix = f"{self.address}module.{name}"
            if not isinstance(source, str) or not source.startswith((".", "/")):
                detail = (
                    "not a local path, so it is not read"
                    if isinstance(source, str)
                    else "the source is not a plain string"
                )
                self.inv.unresolved("remote-module", prefix, location, block.line, detail)
                continue
            child_dir = (self.directory / source).resolve()
            if not child_dir.is_dir() or not any(child_dir.glob("*.tf")):
                self.inv.unresolved("remote-module", prefix, location, block.line, "the local path has no .tf files")
                continue
            for meta in ("count", "for_each"):
                if meta in block.body.attrs:
                    text = _node_text(block.body.attrs[meta].expr)
                    detail = f"{meta} = {text}: read once, the number of copies is unknown"
                    self.inv.unresolved(meta, prefix, location, block.line, detail)
            inputs = {
                k: (a.expr, self)
                for k, a in block.body.attrs.items()
                if k not in ("source", "version", "count", "for_each", "providers", "depends_on")
            }
            module = TfModule(self.inv, child_dir, f"{prefix}.", inputs)
            module.scope = dict(self.scope)
            module.aliased = dict(self.aliased)
            self.modules[name] = module
            module.load()

    def _add(self, block: Block) -> None:
        if block.type == "variable" and block.labels:
            self.variables[block.labels[0]] = block
        elif block.type == "locals":
            self.locals.update(block.body.attrs)
        elif block.type == "output" and block.labels:
            if "value" in block.body.attrs:
                self.outputs[block.labels[0]] = block.body.attrs["value"]
        elif block.type == "resource" and len(block.labels) == 2:
            self.resources[f"{block.labels[0]}.{block.labels[1]}"] = block
        elif block.type == "data" and len(block.labels) == 2:
            self.datas[f"{block.labels[0]}.{block.labels[1]}"] = block
        elif block.type == "module" and block.labels:
            self.module_blocks[block.labels[0]] = block
        elif block.type == "provider" and self.inv.provider_of_prefix(block.labels[0] if block.labels else ""):
            self._read_provider_block(block)

    def _read_provider_block(self, block: Block) -> None:
        provider = self.inv.provider_of_prefix(block.labels[0])
        assert provider is not None
        found: dict[str, Any] = {}
        for level, name in provider.table.get("provider_scope", {}).items():
            attr = block.body.attrs.get(name)
            if attr is None:
                continue
            value = self.eval(attr.expr, Rec())
            value = value[0] if isinstance(value, list) and value else value
            if isinstance(value, str):
                found[level] = value
        alias = block.body.attrs.get("alias")
        if alias is None:
            self.scope.update(found)
        else:
            self.aliased[f"{block.labels[0]}.{self.eval(alias.expr, Rec())}"] = found

    def emit(self) -> None:
        for key, block in self.resources.items():
            self._emit_block(key, block, "managed")
        for key, block in self.datas.items():
            self._emit_block(key, block, "data")
        for module in self.modules.values():
            module.emit()

    def _emit_block(self, key: str, block: Block, mode: str) -> None:
        tf_type = block.labels[0]
        if self.inv.is_helper(tf_type):
            self.inv.helpers += 1
            return
        rid = f"{self.address}{'data.' if mode == 'data' else ''}{key}"
        file = self.inv.block_file[id(block)]
        rec = Rec()
        lines: dict[str, int] = {}
        tree = self._body_tree(block.body, "", rec, lines, rid)
        repeated = ""
        for meta in ("count", "for_each"):
            if meta in block.body.attrs:
                repeated = meta
                self.inv.unresolved(
                    meta,
                    rid,
                    file,
                    block.line,
                    f"{meta} = {_node_text(block.body.attrs[meta].expr)}: read once, the number of copies is unknown",
                )
        name_value = tree.get("name")
        raw = Raw(
            rid,
            "terraform",
            tf_type,
            name_value,
            file,
            block.line,
            tree,
            lines,
            rec.refs,
            mode,
            self.address.rstrip("."),
            repeated,
        )
        raw.scope = dict(self.scope)
        chosen = block.body.attrs.get("provider")
        if chosen is not None:
            raw.scope.update(self.aliased.get(_node_text(chosen.expr), {}))
        self.inv.raws.append(raw)

    def _body_tree(self, body: Body, path: str, rec: Rec, lines: dict[str, int], owner: str) -> dict[str, Any]:
        tree: dict[str, Any] = {}
        for name, attr in body.attrs.items():
            if name in ("count", "for_each", "provider"):
                continue
            here = f"{path}.{name}" if path else name
            lines[here] = attr.line
            rec.via, rec.line = here, attr.line
            tree[name] = self._value(attr.expr, here, rec, lines)
        counts = Counter(b.type for b in body.blocks if b.type != "dynamic")
        seen: Counter[str] = Counter()
        for block in body.blocks:
            if block.type in ("lifecycle", "provisioner", "connection", "moved"):
                continue
            if block.type == "dynamic":
                label = block.labels[0] if block.labels else "block"
                self.inv.unresolved(
                    "dynamic-block",
                    owner,
                    self.inv.block_file.get(id(block), ""),
                    block.line,
                    f"a dynamic {label} block is not expanded",
                )
                tree[label] = Unknown("dynamic block")
                lines[f"{path}.{label}" if path else label] = block.line
                continue
            base = f"{path}.{block.type}" if path else block.type
            if counts[block.type] > 1:
                index = seen[block.type]
                seen[block.type] += 1
                here = f"{base}[{index}]"
                lines[here] = block.line
                tree.setdefault(block.type, []).append(self._body_tree(block.body, here, rec, lines, owner))
            else:
                lines[base] = block.line
                tree[block.type] = self._body_tree(block.body, base, rec, lines, owner)
        return tree

    def _value(self, node: Node, path: str, rec: Rec, lines: dict[str, int]) -> Any:
        if (
            isinstance(node, Ref)
            and isinstance(node.base, Call)
            and node.base.name == "jsonencode"
            and not node.parts
            and node.base.args
        ):
            return self._value(node.base.args[0], path, rec, lines)  # the document's own lines stay findable
        if isinstance(node, ObjE):
            out: dict[str, Any] = {}
            for key, value, line in node.items:
                here = f"{path}.{key}"
                lines[here] = line
                rec.via, rec.line = here, line
                out[key] = self._value(value, here, rec, lines)
            return out
        if isinstance(node, ListE):
            items: list[Any] = []
            for index, item in enumerate(node.items):
                items.append(self._value(item, f"{path}[{index}]", rec, lines))
            return items
        return self.eval(node, rec)

    def ref(self, node: Ref, rec: Rec) -> Any:
        if not isinstance(node.base, str):
            return Unknown(_node_text(node))
        parts = [p if isinstance(p, str) else "*" for p in node.parts]
        head = node.base
        text = _node_text(node)
        if head == "var" and parts:
            return self._variable(parts[0], rec)
        if head == "local" and parts:
            attr = self.locals.get(parts[0])
            return self.eval(attr.expr, rec) if attr else Unknown(text)
        if head == "module" and len(parts) >= 2:
            module = self.modules.get(parts[0])
            if module is None or parts[1] not in module.outputs:
                return Unknown(text)
            return module.eval(module.outputs[parts[1]].expr, rec)
        if head == "data" and len(parts) >= 2:
            key = f"{parts[0]}.{parts[1]}"
            block = self.datas.get(key)
            if block is None:
                return Unknown(text)
            rec.add(f"{self.address}data.{key}")
            return self._attr_of(block, parts[2:], text)
        if len(parts) >= 1 and "_" in head:
            key = f"{head}.{parts[0]}"
            block = self.resources.get(key)
            if block is None:
                return Unknown(text)
            if not self.inv.is_helper(head):
                rec.add(f"{self.address}{key}")
            return self._attr_of(block, parts[1:], text)
        return Unknown(text)

    def _attr_of(self, block: Block, parts: list[str], text: str) -> Any:
        if not parts or parts[0] not in block.body.attrs:
            return Unknown(text)
        return self.eval(block.body.attrs[parts[0]].expr, Rec())

    def _variable(self, name: str, rec: Rec) -> Any:
        if name in self.inputs:
            expr, scope = self.inputs[name]
            return scope.eval(expr, rec)
        block = self.variables.get(name)
        if block is None:
            return Unknown(f"var.{name}")
        sensitive = block.body.attrs.get("sensitive")
        if SECRET_NAME.search(name) or (
            sensitive is not None and isinstance(sensitive.expr, Lit) and sensitive.expr.value is True
        ):
            return Unknown(f"var.{name}")
        default = block.body.attrs.get("default")
        return self.eval(default.expr, rec) if default else Unknown(f"var.{name}")


class BicepFile(Scope):
    def __init__(
        self,
        inv: Inventory,
        path: Path,
        ast: BicepAst,
        prefix: str,
        inputs: dict[str, tuple[Node, BicepFile]],
        scope_rg: Any,
        scope_rg_id: str | None,
        scope_location: Any,
    ) -> None:
        self.inv = inv
        self.path = path
        self.rel = inv.rel(path)
        self.ast = ast
        self.prefix = prefix  # the id of the deployment this file belongs to, without the symbol
        self.inputs = inputs
        self.scope_rg = scope_rg
        self.scope_rg_id = scope_rg_id
        self.scope_location = scope_location
        self.resources: dict[str, BicepResource] = {r.symbol: r for r in ast.resources}
        self.children: dict[str, BicepResource] = {}
        self.parent_of: dict[str, str] = {}
        for resource in ast.resources:
            self._index_children(resource)
        self.modules: dict[str, BicepModule] = {m.symbol: m for m in ast.modules}
        self.module_scopes: dict[str, BicepFile] = {}

    def _index_children(self, resource: BicepResource) -> None:
        if isinstance(resource.body, ObjE):
            for child in resource.body.decls:
                self.children[child.symbol] = child
                self.parent_of[child.symbol] = resource.symbol
                self._index_children(child)

    def full_type(self, resource: BicepResource) -> str:
        rtype = resource.type.split("@")[0]
        parent = self.parent_of.get(resource.symbol)
        if "/" not in rtype and parent:
            return f"{self.full_type(self.resources.get(parent) or self.children[parent])}/{rtype}"
        return rtype

    def rid(self, symbol: str) -> str:
        return f"{self.prefix}{symbol}"

    def eval_module_scope(self, module: BicepModule) -> tuple[Any, str | None, Any]:
        """Where a module deploys: the group's name, its resource id if it is declared here, and its location."""
        scope_node = _obj_get(module.body, "scope")
        if isinstance(scope_node, Ref):
            base = scope_node.base
            if (
                isinstance(base, str)
                and base in self.resources
                and self.full_type(self.resources[base]).lower() == "microsoft.resources/resourcegroups"
            ):
                return (
                    self._resource_attr(self.resources[base], "name"),
                    self.rid(base),
                    self._resource_attr(self.resources[base], "location"),
                )
            if isinstance(base, Call) and base.name.split(".")[-1] == "resourceGroup":
                args = [self.eval(a, Rec()) for a in base.args]
                if args:
                    return args[-1], None, None
        if self.ast.target_scope != "subscription":
            return self.scope_rg, self.scope_rg_id, self.scope_location
        return None, None, None

    def load(self) -> None:
        for module in self.ast.modules:
            target = (
                (self.path.parent / module.path).resolve()
                if not module.path.startswith(("br:", "br/", "ts:", "ts/"))
                else None
            )
            ident = f"{self.prefix}{module.symbol}"
            if target is None or not target.is_file():
                self.inv.unresolved(
                    "remote-module", ident, self.rel, module.line, "a registry or missing module is not read"
                )
                continue
            ast = self.inv.parse_bicep(target)
            if ast is None:
                continue
            self.inv.bicep_modules.add(target)
            params_node = _obj_get(module.body, "params")
            inputs: dict[str, tuple[Node, BicepFile]] = {}
            if isinstance(params_node, ObjE):
                inputs = {k: (v, self) for k, v, _ in params_node.items}
            scope_rg, scope_rg_id, location = self.eval_module_scope(module)
            child = BicepFile(self.inv, target, ast, f"{ident}.", inputs, scope_rg, scope_rg_id, location)
            self.module_scopes[module.symbol] = child
            child.load()
            if module.conditional:
                self.inv.unresolved(
                    "conditional", ident, self.rel, module.line, "the module is deployed only if a condition holds"
                )

    def emit(self) -> None:
        for resource in self.ast.resources:
            self._emit_resource(resource, None)
        for module in self.module_scopes.values():
            module.emit()

    def _emit_resource(self, resource: BicepResource, parent: str | None) -> None:
        rid = self.rid(resource.symbol)
        body = resource.body
        repeated = ""
        if isinstance(body, ForE):
            repeated = "loop"
            self.inv.unresolved(
                "loop", rid, self.rel, resource.line, "a loop: read once, the number of copies is unknown"
            )
            body = next((p for p in reversed(body.parts) if isinstance(p, ObjE)), ObjE([]))
        if resource.conditional:
            self.inv.unresolved("conditional", rid, self.rel, resource.line, "deployed only if a condition holds")
        rec = Rec()
        lines: dict[str, int] = {}
        tree = self._expr_tree(body, "", rec, lines) if isinstance(body, ObjE) else {}
        parent_id = parent
        if isinstance(body, ObjE):
            parent_node = _obj_get(body, "parent")
            if (
                isinstance(parent_node, Ref)
                and isinstance(parent_node.base, str)
                and (parent_node.base in self.resources or parent_node.base in self.children)
            ):
                parent_id = self.rid(parent_node.base)
            elif parent is None:
                for ref in rec.refs:
                    if ref["via"] == "parent":
                        parent_id = ref["to"]
        raw = Raw(
            rid,
            "bicep",
            self.full_type(resource),
            tree.get("name"),
            self.rel,
            resource.line,
            tree,
            lines,
            rec.refs,
            "data" if resource.existing else "managed",
            self.prefix.rstrip("."),
            repeated,
            resource.conditional,
            parent_id,
        )
        raw.scope_rg = self.scope_rg if isinstance(self.scope_rg, str) else None
        raw.scope_rg_id = self.scope_rg_id
        self.inv.raws.append(raw)
        if isinstance(body, ObjE):
            for child in body.decls:
                self._emit_resource(child, rid)

    def _expr_tree(self, node: Node, path: str, rec: Rec, lines: dict[str, int]) -> Any:
        if isinstance(node, ObjE):
            out: dict[str, Any] = {}
            for key, value, line in node.items:
                here = f"{path}.{key}" if path else key
                lines[here] = line
                rec.via, rec.line = here, line
                out[key] = self._expr_tree(value, here, rec, lines)
            return out
        if isinstance(node, ListE):
            items: list[Any] = []
            for index, item in enumerate(node.items):
                rec.via = f"{path}[{index}]"
                items.append(self._expr_tree(item, f"{path}[{index}]", rec, lines))
            return items
        return self.eval(node, rec)

    def ref(self, node: Ref, rec: Rec) -> Any:
        base = node.base
        text = _node_text(node)
        parts = [p if isinstance(p, str) else "*" for p in node.parts]
        if isinstance(base, Call):
            name = base.name.split(".")[-1]
            if name == "resourceGroup" and parts[:1] == ["location"] and self.scope_location is not None:
                return self.scope_location
            if name == "resourceGroup" and parts[:1] == ["name"] and self.scope_rg is not None:
                return self.scope_rg
            args = [self.eval(a, rec) for a in base.args]
            if not parts:
                return self.call(Call(base.name, base.args), rec)
            return Unknown(text, _literals(args))
        symbol = base
        if symbol in self.ast.params or symbol in self.inputs:
            if symbol in self.inputs:
                expr, scope = self.inputs[symbol]
                value = scope.eval(expr, rec)
            else:
                expr = self.ast.params[symbol].expr
                if SECRET_NAME.search(symbol) or (isinstance(expr, Lit) and expr.value is MISSING):
                    return Unknown(f"param {symbol}")
                value = self.eval(expr, rec)
            return _step(value, parts, text)
        if symbol in self.ast.vars:
            return _step(self.eval(self.ast.vars[symbol].expr, rec), parts, text)
        if symbol in self.resources or symbol in self.children:
            resource = self.resources.get(symbol) or self.children[symbol]
            rec.add(self.rid(symbol))
            if parts and parts[0] in ("name", "location", "kind", "sku", "properties"):
                return self._resource_attr(resource, *parts)
            return Unknown(text)
        if symbol in self.modules:
            module = self.module_scopes.get(symbol)
            if module and len(parts) >= 2 and parts[0] == "outputs" and parts[1] in module.ast.outputs:
                return module.eval(module.ast.outputs[parts[1]].expr, rec)
            return Unknown(text)
        return Unknown(text)

    def _resource_attr(self, resource: BicepResource, *parts: str) -> Any:
        node: Any = resource.body
        for part in parts:
            if not isinstance(node, ObjE):
                return Unknown(f"{resource.symbol}.{'.'.join(parts)}")
            next_node = _obj_get(node, part)
            if next_node is None:
                return Unknown(f"{resource.symbol}.{'.'.join(parts)}")
            node = next_node
        return self.eval(node, Rec())


def _obj_get(node: Node | None, key: str) -> Node | None:
    if isinstance(node, ObjE):
        for name, value, _ in node.items:
            if name == key:
                return value
    return None


def _step(value: Any, parts: list[str], text: str) -> Any:
    for part in parts:
        if isinstance(value, dict) and part in value:
            value = value[part]
        else:
            return Unknown(text)
    return value


class _Line:
    """A JSON value with the line it starts on."""

    __slots__ = ("line", "value")

    def __init__(self, value: Any, line: int) -> None:
        self.value = value
        self.line = line


class ArmScope(Scope):
    def __init__(self, parameters: dict[str, Any], variables: dict[str, Any]) -> None:
        self.parameters = parameters
        self.variables = variables

    def resolve(self, value: Any, rec: Rec) -> Any:
        """A parameter default or a variable can itself be an ARM expression."""
        if isinstance(value, str) and value.startswith("[") and not value.startswith("[[") and value.endswith("]"):
            return _arm_expression(self, value[1:-1], rec)
        return value

    def call(self, node: Call, rec: Rec) -> Any:
        name = node.name.split(".")[-1]
        if name == "parameters" and node.args:
            key = self.eval(node.args[0], rec)
            if isinstance(key, str):
                if SECRET_NAME.search(key) or key not in self.parameters:
                    return Unknown(f"parameter {key}")
                return self.resolve(self.parameters[key], rec)
            return Unknown("parameters(…)")
        if name == "variables" and node.args:
            key = self.eval(node.args[0], rec)
            if isinstance(key, str) and key in self.variables:
                return self.resolve(self.variables[key], rec)
            return Unknown(f"variable {key}") if isinstance(key, str) else Unknown("variables(…)")
        if name in ("resourceId", "reference", "listKeys"):
            args = [self.eval(a, rec) for a in node.args]
            strings = [a for a in args if isinstance(a, str)]
            if name == "resourceId" and len(strings) >= 2 and strings[-2].count("/") >= 1:
                rec.add(f"arm:{strings[-2]}/{strings[-1]}")
            elif name == "reference" and strings:
                rec.add(f"arm-symbol:{strings[0]}")
            return Unknown(f"{name}(…)")
        return super().call(node, rec)

    def ref(self, node: Ref, rec: Rec) -> Any:
        if isinstance(node.base, Call):
            return self.call(node.base, rec) if not node.parts else Unknown(_node_text(node))
        return Unknown(_node_text(node))


def _parse_json_lines(src: str) -> Any:
    """json.loads, but each value keeps the line it starts on, and // and /* */ comments are allowed
    (ARM templates may have both)."""
    index = 0
    line = 1

    def skip() -> None:
        nonlocal index, line
        while index < len(src):
            c = src[index]
            if c in " \t\r":
                index += 1
            elif c == "\n":
                line += 1
                index += 1
            elif src.startswith("//", index):
                end = src.find("\n", index)
                index = len(src) if end < 0 else end
            elif src.startswith("/*", index):
                end = src.find("*/", index + 2)
                if end < 0:
                    raise ParseError(line, "a comment is not closed")
                line += src.count("\n", index, end)
                index = end + 2
            else:
                return

    def value() -> _Line:
        nonlocal index, line
        skip()
        start = line
        if index >= len(src):
            raise ParseError(line, "unexpected end of file")
        c = src[index]
        if c == "{":
            index += 1
            out: dict[str, _Line] = {}
            while True:
                skip()
                if src[index] == "}":
                    index += 1
                    return _Line(out, start)
                if src[index] == ",":
                    index += 1
                    continue
                key = value()
                skip()
                if src[index] != ":":
                    raise ParseError(line, "expected a colon")
                index += 1
                out[key.value] = value()
        if c == "[":
            index += 1
            items: list[_Line] = []
            while True:
                skip()
                if src[index] == "]":
                    index += 1
                    return _Line(items, start)
                if src[index] == ",":
                    index += 1
                    continue
                items.append(value())
        if c == '"':
            end = index + 1
            while True:
                if src[end] == "\\":
                    end += 2
                elif src[end] == '"':
                    break
                else:
                    end += 1
            text = json.loads(src[index : end + 1])
            index = end + 1
            return _Line(text, start)
        match = re.compile(r"-?\d+(\.\d+)?([eE][+-]?\d+)?|true|false|null").match(src, index)
        if not match:
            raise ParseError(line, f"unexpected {c!r}")
        index = match.end()
        return _Line(json.loads(match.group(0)), start)

    result = value()
    skip()
    if index < len(src):
        raise ParseError(line, "text after the document")
    return result


def _plain(item: _Line) -> Any:
    if isinstance(item.value, dict):
        return {k: _plain(v) for k, v in item.value.items()}
    if isinstance(item.value, list):
        return [_plain(v) for v in item.value]
    return item.value


class ArmTemplate:
    def __init__(self, inv: Inventory, path: Path, doc: _Line) -> None:
        self.inv = inv
        self.path = path
        self.rel = inv.rel(path)
        self.doc = doc.value

    def run(self) -> None:
        params = {}
        for key, spec in self.doc.get("parameters", _Line({}, 0)).value.items():
            if isinstance(spec.value, dict) and "defaultValue" in spec.value:
                params[key] = _plain(spec.value["defaultValue"])
        variables = {k: _plain(v) for k, v in self.doc.get("variables", _Line({}, 0)).value.items()}
        scope = ArmScope(params, variables)
        items = self.doc.get("resources", _Line([], 0)).value
        if isinstance(items, dict):  # the symbolic-name form of an ARM template
            items = list(items.values())
        for index, item in enumerate(items):
            self._emit(scope, item, index, None)

    def _emit(self, scope: ArmScope, item: _Line, index: int, parent: str | None) -> None:
        if not isinstance(item.value, dict) or "type" not in item.value:
            return
        source_type = _plain(item.value["type"])
        rec = Rec()
        lines: dict[str, int] = {}
        tree = self._tree(scope, item, "", rec, lines)
        name = tree.get("name")
        ident = name if isinstance(name, str) else f"#{index}"
        rid = f"{self.rel}:{source_type.split('/')[-1]}/{ident}"
        raw = Raw(
            rid, "arm", source_type, name, self.rel, item.line, tree, lines, rec.refs, "managed", "", "", False, parent
        )
        if isinstance(tree.get("copy"), dict):
            raw.repeated = "copy"
            self.inv.unresolved(
                "loop", rid, self.rel, item.line, "a copy loop: read once, the number of copies is unknown"
            )
        if "condition" in tree:
            raw.conditional = True
            self.inv.unresolved("conditional", rid, self.rel, item.line, "deployed only if a condition holds")
        self.inv.raws.append(raw)
        for child_index, child in enumerate(item.value.get("resources", _Line([], 0)).value):
            child_type = child.value.get("type") if isinstance(child.value, dict) else None
            if child_type is not None and isinstance(child_type.value, str):
                child.value["type"] = _Line(f"{source_type}/{child_type.value}", child_type.line)
            self._emit(scope, child, child_index, rid)

    def _tree(self, scope: ArmScope, item: _Line, path: str, rec: Rec, lines: dict[str, int]) -> Any:
        value = item.value
        if isinstance(value, dict):
            out = {}
            for key, sub in value.items():
                if key == "resources" and not path:
                    continue
                here = f"{path}.{key}" if path else key
                lines[here] = sub.line
                rec.via, rec.line = here, sub.line
                out[key] = self._tree(scope, sub, here, rec, lines)
            return out
        if isinstance(value, list):
            result = []
            for index, sub in enumerate(value):
                rec.via, rec.line = f"{path}[{index}]", sub.line
                result.append(self._tree(scope, sub, f"{path}[{index}]", rec, lines))
            return result
        if isinstance(value, str) and value.startswith("[") and not value.startswith("[[") and value.endswith("]"):
            return _arm_expression(scope, value[1:-1], rec)
        return value


def _arm_expression(scope: ArmScope, text: str, rec: Rec) -> Any:
    try:
        parser = Parser(lex(text, "bicep"), "bicep")
        parser.depth = 1
        return scope.eval(parser.expr(), rec)
    except ParseError:
        return Unknown("an ARM expression that could not be read")


class _Yaml:
    """A small indentation reader for CloudFormation YAML: mappings, lists, block and flow values, comments and the
    short function tags. The standard library has no YAML parser; this reads what templates use and refuses the rest
    (anchors, aliases, merge keys), so a file it cannot read is reported instead of half-read."""

    def __init__(self, src: str) -> None:
        self.lines = src.expandtabs(2).splitlines()
        self.i = 0

    def parse(self) -> _Line:
        peek = self._peek()
        if peek is None:
            return _Line({}, 1)
        return self.node()

    def _peek(self) -> tuple[int, str, int] | None:
        """The next line that means something: (indent, text, line number)."""
        while self.i < len(self.lines):
            raw = self.lines[self.i]
            text = raw.strip()
            if not text or text.startswith("#") or text == "---" or text.startswith("%YAML") or text == "...":
                self.i += 1
                continue
            return len(raw) - len(raw.lstrip(" ")), text, self.i + 1
        return None

    @staticmethod
    def _is_item(text: str) -> bool:
        return text == "-" or text.startswith("- ")

    @staticmethod
    def _key_of(text: str) -> tuple[str, str] | None:
        """Split `key: rest`. None when the text is not a mapping entry."""
        if text[0] in "\"'":
            end = text.find(text[0], 1)
            while end > 0 and text[0] == '"' and text[end - 1] == "\\":
                end = text.find(text[0], end + 1)
            if end < 0:
                return None
            tail = text[end + 1 :].lstrip()
            if not tail.startswith(":") or (len(tail) > 1 and tail[1] not in " \t"):
                return None
            return text[1:end], tail[1:].strip()
        if text[0] in "[{!&*|>":
            return None
        for index, char in enumerate(text):
            if char == ":" and (index + 1 == len(text) or text[index + 1] in " \t"):
                return text[:index].strip(), text[index + 1 :].strip()
            if char == "#" and index and text[index - 1] in " \t":
                return None
        return None

    @staticmethod
    def _strip_comment(text: str) -> str:
        quote = ""
        for index, char in enumerate(text):
            if quote:
                if char == quote:
                    quote = ""
            elif char in "\"'":
                quote = char
            elif char == "#" and (index == 0 or text[index - 1] in " \t"):
                return text[:index].rstrip()
        return text

    def node(self) -> _Line:
        peek = self._peek()
        assert peek is not None
        indent, text, line = peek
        if self._is_item(text):
            return self.sequence(indent)
        if self._key_of(text) is not None:
            return self.mapping(indent)
        self.i += 1
        return self._after_key(text, indent, line)

    def mapping(self, indent: int) -> _Line:
        out: dict[str, _Line] = {}
        start = self.i + 1
        while (peek := self._peek()) is not None:
            at, text, line = peek
            if at != indent or self._is_item(text):
                break
            split = self._key_of(text)
            if split is None:
                raise ParseError(line, f"expected a key, found {text[:40]!r}")
            key, rest = split
            self.i += 1
            value = self._after_key(rest, indent, line)
            value.line = line  # a value that is a block starts on the line below; its key is where it is declared
            out[key] = value
        return _Line(out, start)

    def sequence(self, indent: int) -> _Line:
        items: list[_Line] = []
        start = self.i + 1
        while (peek := self._peek()) is not None:
            at, text, line = peek
            if at != indent or not self._is_item(text):
                break
            rest = text[1:].lstrip()
            if not rest or rest.startswith("#"):
                self.i += 1
                inner = self._peek()
                items.append(self.node() if inner and inner[0] > indent else _Line(None, line))
                continue
            offset = indent + len(text) - len(rest)
            if self._is_item(rest) or (self._key_of(rest) is not None and rest[0] not in "!["):
                # `- key: value` opens a mapping whose first key sits right here, so the line is re-read at this column
                self.lines[self.i] = " " * offset + rest
                items.append(self.node())
                continue
            self.i += 1
            items.append(self._after_key(rest, indent, line))
        return _Line(items, start)

    def _after_key(self, rest: str, indent: int, line: int) -> _Line:
        rest = self._strip_comment(rest).strip()
        if rest.startswith(("&", "*", "<<")):
            raise ParseError(line, "YAML anchors, aliases and merge keys are not read")
        tag = ""
        if rest.startswith("!"):
            tag, _, rest = rest.partition(" ")
            rest = rest.strip()
        value = self._value_of(rest, indent, line)
        return self._tagged(tag, value, line)

    def _value_of(self, rest: str, indent: int, line: int) -> _Line:
        if re.fullmatch(r"[|>][+-]?[0-9]?[+-]?", rest):
            return _Line(self._block(rest, indent), line)
        if rest == "":
            peek = self._peek()
            if peek is not None and peek[0] > indent:
                return self.node()
            if peek is not None and peek[0] == indent and self._is_item(peek[1]):
                return self.sequence(indent)
            return _Line(None, line)
        if rest[0] in "[{":
            return _YamlFlow(self._flow_text(rest, line), line).value()
        if rest[0] in "\"'":
            return _YamlFlow(rest, line).scalar()
        return _Line(_yaml_scalar(rest), line)

    def _flow_text(self, text: str, line: int) -> str:
        """A flow value may run over several lines; keep adding until its brackets close."""
        while not _balanced(text):
            if self.i >= len(self.lines):
                raise ParseError(line, "a bracket is not closed")
            text = f"{text} {self._strip_comment(self.lines[self.i]).strip()}"
            self.i += 1
        return text

    def _block(self, indicator: str, indent: int) -> str:
        body: list[str] = []
        while self.i < len(self.lines):
            raw = self.lines[self.i]
            if raw.strip() and len(raw) - len(raw.lstrip(" ")) <= indent:
                break
            body.append(raw)
            self.i += 1
        while body and not body[-1].strip():
            body.pop()
        width = min((len(b) - len(b.lstrip(" ")) for b in body if b.strip()), default=0)
        lines = [b[width:] for b in body]
        return " ".join(line for line in lines if line) if indicator[0] == ">" else "\n".join(lines)

    @staticmethod
    def _tagged(tag: str, value: _Line, line: int) -> _Line:
        if not tag:
            return value
        name = tag[1:]
        key = name if name in ("Ref", "Condition") else f"Fn::{name}"
        return _Line({key: value}, line)


def _balanced(text: str) -> bool:
    depth, quote = 0, ""
    for char in text:
        if quote:
            if char == quote:
                quote = ""
        elif char in "\"'":
            quote = char
        elif char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
    return depth <= 0


def _yaml_scalar(text: str) -> Any:
    lowered = text.lower()
    if lowered in ("true", "yes", "on"):
        return True
    if lowered in ("false", "no", "off"):
        return False
    if lowered in ("null", "~"):
        return None
    # A leading zero stays a string: an account id must not turn into a number.
    if re.fullmatch(r"-?(0|[1-9][0-9]*)", text):
        return int(text)
    if re.fullmatch(r"-?(0|[1-9][0-9]*)\.[0-9]+", text):
        return float(text)
    return text


class _YamlFlow:
    """A one-line YAML value: `[a, b]`, `{a: b}`, a quoted string, or a tag in front of one of them."""

    def __init__(self, text: str, line: int) -> None:
        self.text = text
        self.pos = 0
        self.line = line

    def _ws(self) -> None:
        while self.pos < len(self.text) and self.text[self.pos] in " \t":
            self.pos += 1

    def value(self) -> _Line:
        self._ws()
        char = self.text[self.pos : self.pos + 1]
        if char == "[":
            return self._list()
        if char == "{":
            return self._map()
        if char == "!":
            end = self.pos
            while end < len(self.text) and self.text[end] not in " \t,]}":
                end += 1
            tag = self.text[self.pos : end]
            self.pos = end
            self._ws()
            has_value = self.pos < len(self.text) and self.text[self.pos] not in ",]}"
            inner = self.value() if has_value else _Line(None, self.line)
            return _Yaml._tagged(tag, inner, self.line)
        if char in "\"'":
            return self.scalar()
        start = self.pos
        while self.pos < len(self.text):
            here = self.text[self.pos]
            if here in ",]}":
                break
            if here == ":" and self.pos + 1 < len(self.text) and self.text[self.pos + 1] == " ":
                break
            self.pos += 1
        return _Line(_yaml_scalar(self.text[start : self.pos].strip()), self.line)

    def scalar(self) -> _Line:
        quote = self.text[self.pos]
        self.pos += 1
        out: list[str] = []
        while self.pos < len(self.text):
            char = self.text[self.pos]
            if quote == '"' and char == "\\" and self.pos + 1 < len(self.text):
                escapes = {"n": "\n", "t": "\t", '"': '"', "\\": "\\", "/": "/"}
                out.append(escapes.get(self.text[self.pos + 1], self.text[self.pos + 1]))
                self.pos += 2
                continue
            if char == quote:
                if quote == "'" and self.text[self.pos + 1 : self.pos + 2] == "'":
                    out.append("'")
                    self.pos += 2
                    continue
                self.pos += 1
                return _Line("".join(out), self.line)
            out.append(char)
            self.pos += 1
        raise ParseError(self.line, "a quoted string is not closed")

    def _list(self) -> _Line:
        self.pos += 1
        items: list[_Line] = []
        while True:
            self._ws()
            if self.pos >= len(self.text):
                raise ParseError(self.line, "a list is not closed")
            if self.text[self.pos] == "]":
                self.pos += 1
                return _Line(items, self.line)
            if self.text[self.pos] == ",":
                self.pos += 1
                continue
            items.append(self.value())

    def _map(self) -> _Line:
        self.pos += 1
        out: dict[str, _Line] = {}
        while True:
            self._ws()
            if self.pos >= len(self.text):
                raise ParseError(self.line, "a mapping is not closed")
            if self.text[self.pos] == "}":
                self.pos += 1
                return _Line(out, self.line)
            if self.text[self.pos] == ",":
                self.pos += 1
                continue
            key = self.value()
            self._ws()
            if self.text[self.pos : self.pos + 1] != ":":
                raise ParseError(self.line, "expected a colon in a flow mapping")
            self.pos += 1
            out[str(key.value)] = self.value()


class CloudFormationTemplate:
    """One template, from JSON or YAML, read the same way: parameters, conditions, mappings, resources and the
    functions. Whatever depends on a deployment (Fn::If, cross-stack imports, macros, nested stacks) is reported."""

    def __init__(self, inv: Inventory, path: Path, doc: _Line, template: dict[str, Any]) -> None:
        self.inv = inv
        self.rel = inv.rel(path)
        self.doc: dict[str, _Line] = doc.value
        self.template = template
        self.parameters: dict[str, dict[str, Any]] = {
            k: _plain(v) for k, v in self._section("Parameters").items() if isinstance(v.value, dict)
        }
        self.mappings = {k: _plain(v) for k, v in self._section("Mappings").items()}
        self.resources = self._section("Resources")
        self.current = self.rel

    def _section(self, name: str) -> dict[str, _Line]:
        section = self.doc.get(name)
        return section.value if section is not None and isinstance(section.value, dict) else {}

    def rid(self, logical: str) -> str:
        return f"{self.rel}:{logical}"

    def run(self) -> None:
        transform = self.doc.get("Transform")
        if transform is not None:
            names = _plain(transform)
            for name in names if isinstance(names, list) else [names]:
                self.inv.unresolved(
                    "macro", self.rel, self.rel, transform.line, f"the template runs {name}: what it adds is not read"
                )
        for logical, item in self.resources.items():
            self._emit(logical, item)

    def _emit(self, logical: str, item: _Line) -> None:
        rid = self.rid(logical)
        if logical.startswith("Fn::ForEach"):
            self.inv.unresolved("loop", rid, self.rel, item.line, "a Fn::ForEach loop: what it creates is not read")
            return
        if not isinstance(item.value, dict) or "Type" not in item.value:
            return
        self.current = rid
        rec = Rec()
        lines: dict[str, int] = {}
        tree = self._tree(item, "", rec, lines)
        source_type = tree.get("Type")
        if not isinstance(source_type, str):
            self.inv.unresolved("unknown-type", rid, self.rel, item.line, "the type is not a plain string")
            return
        raw = Raw(rid, "cloudformation", source_type, None, self.rel, item.line, tree, lines, rec.refs, "managed")
        if "Condition" in tree:
            raw.conditional = True
            self.inv.unresolved(
                "conditional",
                rid,
                self.rel,
                lines.get("Condition", item.line),
                f"deployed only if {tree['Condition']} holds",
            )
        if source_type in self.template.get("nested_stack_types", []):
            self.inv.unresolved(
                "nested-stack", rid, self.rel, item.line, "a nested stack is not followed: what it creates is not read"
            )
        properties = tree.get("Properties")
        if "Count" in tree or (isinstance(properties, dict) and "Count" in properties):
            raw.repeated = "count"
            self.inv.unresolved("count", rid, self.rel, item.line, "a Count macro: the number of copies is unknown")
        self.inv.raws.append(raw)

    def _tree(self, item: _Line, path: str, rec: Rec, lines: dict[str, int]) -> Any:
        value = item.value
        if isinstance(value, dict):
            intrinsic = self._intrinsic_name(value)
            if intrinsic:
                return self._intrinsic(intrinsic, value[intrinsic], rec, item.line)
            out = {}
            for key, sub in value.items():
                here = f"{path}.{key}" if path else key
                lines[here] = sub.line
                rec.via, rec.line = here, sub.line
                out[key] = self._tree(sub, here, rec, lines)
            return out
        if isinstance(value, list):
            result = []
            for index, sub in enumerate(value):
                here = f"{path}[{index}]"
                lines[here] = sub.line
                rec.via, rec.line = here, sub.line
                result.append(self._tree(sub, here, rec, lines))
            return result
        return value

    @staticmethod
    def _intrinsic_name(value: dict[str, _Line]) -> str | None:
        if len(value) != 1:
            return None
        key = next(iter(value))
        return key if key == "Ref" or key.startswith("Fn::") else None

    def _eval(self, item: _Line, rec: Rec) -> Any:
        value = item.value
        if isinstance(value, dict):
            intrinsic = self._intrinsic_name(value)
            if intrinsic:
                return self._intrinsic(intrinsic, value[intrinsic], rec, item.line)
            return {k: self._eval(v, rec) for k, v in value.items()}
        if isinstance(value, list):
            return [self._eval(v, rec) for v in value]
        return value

    def _intrinsic(self, name: str, arg: _Line, rec: Rec, line: int) -> Any:
        args = arg.value
        if name == "Ref":
            return self._ref(str(args), rec)
        if name == "Fn::GetAtt":
            target = (args[0].value if isinstance(args, list) and args else str(args).split(".", 1)[0]) or ""
            if isinstance(target, str) and target in self.resources:
                rec.add(self.rid(target))
            return Unknown(f"GetAtt {target}")
        if name == "Fn::Sub":
            return self._sub(args, rec)
        if name == "Fn::Join" and isinstance(args, list) and len(args) == 2:
            delimiter = self._eval(args[0], rec)
            items = self._eval(args[1], rec)
            if isinstance(delimiter, str) and isinstance(items, list) and not _any_unknown(items):
                return delimiter.join(str(x) for x in items)
            return Unknown("Fn::Join", _literals(items if isinstance(items, list) else [items]))
        if name == "Fn::Select" and isinstance(args, list) and len(args) == 2:
            index = self._eval(args[0], rec)
            items = self._eval(args[1], rec)
            if (
                isinstance(index, int | str)
                and isinstance(items, list)
                and str(index).isdigit()
                and int(index) < len(items)
                and not _any_unknown([items[int(index)]])
            ):
                return items[int(index)]
            return Unknown("Fn::Select", _literals(items if isinstance(items, list) else []))
        if name == "Fn::FindInMap" and isinstance(args, list) and len(args) >= 3:
            keys = [self._eval(a, rec) for a in args[:3]]
            if not _any_unknown(keys):
                node: Any = self.mappings
                for key in keys:
                    node = node.get(str(key)) if isinstance(node, dict) else None
                if node is not None:
                    return node
            return Unknown("Fn::FindInMap")
        if name == "Fn::If":
            condition = args[0].value if isinstance(args, list) and args else "?"
            branches = [self._eval(a, rec) for a in args[1:]] if isinstance(args, list) else []
            self.inv.unresolved(
                "conditional-value",
                self.current,
                self.rel,
                line,
                f"Fn::If on {condition}: which value applies is not known",
            )
            return Unknown(f"Fn::If {condition}", _literals(branches))
        if name == "Fn::ImportValue":
            self._eval(arg, rec)
            self.inv.unresolved(
                "import-value", self.current, self.rel, line, "imported from another stack: the value is not read"
            )
            return Unknown("Fn::ImportValue")
        if name == "Fn::Transform":
            self.inv.unresolved(
                "macro", self.current, self.rel, line, "Fn::Transform runs a macro: what it adds is not read"
            )
            return Unknown("Fn::Transform")
        value = self._eval(arg, rec)
        return Unknown(name, _literals(value if isinstance(value, list) else [value]))

    def _ref(self, name: str, rec: Rec) -> Any:
        if name in self.parameters:
            return self._parameter(name)
        if name in self.resources:
            rec.add(self.rid(name))
        return Unknown(f"Ref {name}")

    def _parameter(self, name: str) -> Any:
        spec = self.parameters[name]
        no_echo = spec.get("NoEcho") in (True, "true", "True")
        if no_echo or SECRET_NAME.search(name) or "Default" not in spec:
            return Unknown(f"parameter {name}")
        default = spec["Default"]
        return default if isinstance(default, str | int | float | bool) else Unknown(f"parameter {name}")

    def _sub(self, args: Any, rec: Rec) -> Any:
        extra: dict[str, Any] = {}
        template = args
        if isinstance(args, list) and args:
            template = args[0].value
            if len(args) > 1 and isinstance(args[1].value, dict):
                extra = {k: self._eval(v, rec) for k, v in args[1].value.items()}
        if not isinstance(template, str):
            return Unknown("Fn::Sub")
        parts: list[Any] = []
        for piece in re.split(r"(\$\{[^}]*\})", template):
            if not (piece.startswith("${") and piece.endswith("}")):
                parts.append(piece)
                continue
            inner = piece[2:-1]
            if inner.startswith("!"):
                parts.append("${" + inner[1:] + "}")
            elif inner in extra:
                parts.append(extra[inner])
            elif inner in self.parameters:
                parts.append(self._parameter(inner))
            else:
                head = inner.split(".", 1)[0]
                if head in self.resources:
                    rec.add(self.rid(head))
                parts.append(Unknown(f"Sub {inner}"))
        if any(isinstance(p, Unknown) for p in parts):
            unknown = ", ".join(p.text for p in parts if isinstance(p, Unknown))
            return Unknown(unknown, _literals(parts))
        return "".join(str(p) for p in parts)


def _any_unknown(values: list[Any]) -> bool:
    return any(isinstance(v, Unknown) for v in values)


# ---------------------------------------------------------------------------- the inventory


@dataclass
class Provider:
    name: str
    table: dict[str, Any]
    by_tf: dict[str, str]
    by_arm: dict[str, str]


def _find_provider_dir() -> Path | None:
    here = Path(__file__).resolve().parent
    for candidate in (here / "cloud", here.parent / "references" / "cloud"):
        if candidate.is_dir():
            return candidate
    return None


def load_providers() -> dict[str, Provider]:
    directory = _find_provider_dir()
    providers: dict[str, Provider] = {}
    if directory is None:
        return providers
    for path in sorted(directory.glob("*.json")):
        table = json.loads(path.read_text(encoding="utf-8"))
        by_tf = {tf: native for native, spec in table["types"].items() for tf in spec.get("tf", [])}
        by_arm = {native.lower(): native for native in table["types"]}
        providers[table["provider"]] = Provider(table["provider"], table, by_tf, by_arm)
    return providers


class Inventory:
    def __init__(self, repo: Path | None, providers: dict[str, Provider]) -> None:
        self.repo = repo
        self.providers = providers
        self.raws: list[Raw] = []
        self.files: dict[str, list[str]] = {"terraform": [], "bicep": [], "arm": [], "cloudformation": []}
        self.not_read: list[dict[str, str]] = []
        self.unresolved_rows: list[dict[str, Any]] = []
        self.bicep_modules: set[Path] = set()
        self.block_file: dict[int, str] = {}
        self.hcl_cache: dict[Path, Body | None] = {}
        self.bicep_cache: dict[Path, BicepAst | None] = {}
        self.helpers = 0
        self.secret_values: set[str] = set()

    def rel(self, path: Path) -> str:
        if self.repo is None:
            return path.name
        return path.resolve().relative_to(self.repo.resolve()).as_posix()

    def provider_of_prefix(self, prefix: str) -> Provider | None:
        for provider in self.providers.values():
            if any(
                prefix == p.rstrip("_") or prefix.startswith(p) for p in provider.table.get("terraform_prefixes", [])
            ):
                return provider
        return None

    def is_helper(self, tf_type: str) -> bool:
        return any(
            tf_type.startswith(p)
            for provider in self.providers.values()
            for p in provider.table.get("terraform_helpers", [])
        )

    def provider_of_type(self, source_type: str, fmt: str) -> tuple[Provider | None, str | None]:
        for provider in self.providers.values():
            if fmt == "terraform" and source_type in provider.by_tf:
                return provider, provider.by_tf[source_type]
            if fmt != "terraform" and source_type.lower() in provider.by_arm:
                return provider, provider.by_arm[source_type.lower()]
        return None, None

    def unresolved(self, kind: str, resource: str, file: str, line: int, detail: str) -> None:
        self.unresolved_rows.append({"kind": kind, "resource": resource, "file": file, "line": line, "detail": detail})

    def parse_hcl(self, path: Path) -> Body | None:
        if path not in self.hcl_cache:
            try:
                self.hcl_cache[path] = Parser(lex(path.read_text(encoding="utf-8"), "hcl"), "hcl").hcl_body(False)
            except (ParseError, RecursionError) as exc:
                self.hcl_cache[path] = None
                self.unresolved(
                    "parse-error",
                    self.rel(path),
                    self.rel(path),
                    getattr(exc, "line", 0),
                    f"could not read this file: {exc}",
                )
        return self.hcl_cache[path]

    def parse_bicep(self, path: Path) -> BicepAst | None:
        path = path.resolve()
        if path not in self.bicep_cache:
            try:
                self.bicep_cache[path] = Parser(lex(path.read_text(encoding="utf-8"), "bicep"), "bicep").bicep_file()
            except (ParseError, RecursionError) as exc:
                self.bicep_cache[path] = None
                self.unresolved(
                    "parse-error",
                    self.rel(path),
                    self.rel(path),
                    getattr(exc, "line", 0),
                    f"could not read this file: {exc}",
                )
        return self.bicep_cache[path]

    def read_code(self) -> None:
        assert self.repo is not None
        tf_dirs: set[Path] = set()
        bicep_files: list[Path] = []
        json_files: list[Path] = []
        template_files: list[Path] = []
        for path in self._walk(self.repo):
            rel = self.rel(path)
            if path.name.endswith(NOT_READ_SUFFIXES):
                self.not_read.append(
                    {"file": rel, "why": "values and secrets live in files like this, so it is not opened"}
                )
            elif path.suffix == ".tf":
                tf_dirs.add(path.parent.resolve())
            elif path.suffix == ".bicep":
                bicep_files.append(path)
            else:
                if path.suffix == ".json":
                    json_files.append(path)
                if path.suffix in TEMPLATE_SUFFIXES:
                    template_files.append(path)
        # A directory another module calls is that module's, not a root of its own, so it is not walked twice.
        called = {d for directory in tf_dirs for d in self._called_modules(directory)}
        for directory in sorted(tf_dirs - called):
            module = TfModule(self, directory, "", {})
            module.load()
            module.emit()
        self._read_bicep(bicep_files)
        self._read_arm(json_files)
        self._read_cloudformation(template_files)

    def _called_modules(self, directory: Path) -> set[Path]:
        out: set[Path] = set()
        for path in directory.glob("*.tf"):
            body = self.parse_hcl(path)
            if body is None:
                continue
            for block in body.blocks:
                source = block.body.attrs.get("source") if block.type == "module" else None
                if (
                    source
                    and isinstance(source.expr, Lit)
                    and isinstance(source.expr.value, str)
                    and source.expr.value.startswith(".")
                ):
                    out.add((directory / source.expr.value).resolve())
        return out

    def _read_bicep(self, files: list[Path]) -> None:
        parsed = {path.resolve(): self.parse_bicep(path) for path in files}
        for path, ast in parsed.items():
            if ast is None:
                continue
            self.files["bicep"].append(self.rel(path))
        roots = []
        for path, ast in parsed.items():
            if ast is None:
                continue
            scope = BicepFile(self, path, ast, f"{self.rel(path)}:", {}, None, None, None)
            roots.append(scope)
            scope.load()
        for scope in roots:
            if scope.path.resolve() not in self.bicep_modules:
                scope.emit()

    def _read_arm(self, files: list[Path]) -> None:
        for path in files:
            text = path.read_text(encoding="utf-8")
            if "deploymentTemplate.json" not in text:
                continue
            rel = self.rel(path)
            if path.name.endswith(".parameters.json") or "deploymentParameters.json" in text:
                continue
            try:
                doc = _parse_json_lines(text)
            except (ParseError, IndexError, json.JSONDecodeError) as exc:
                self.unresolved("parse-error", rel, rel, getattr(exc, "line", 0), f"could not read this file: {exc}")
                continue
            if not isinstance(doc.value, dict) or "resources" not in doc.value:
                continue
            generator = _plain(doc.value.get("metadata", _Line({}, 0)))
            if isinstance(generator, dict) and generator.get("_generator", {}).get("name") == "bicep":
                self.not_read.append({"file": rel, "why": "compiled from Bicep; the Bicep file is the source"})
                continue
            self.files["arm"].append(rel)
            ArmTemplate(self, path, doc).run()

    def _read_cloudformation(self, files: list[Path]) -> None:
        template = next(
            (
                p.table["template"]
                for p in self.providers.values()
                if p.table.get("template", {}).get("format") == "cloudformation"
            ),
            None,
        )
        if template is None:
            return
        for path in files:
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if template["version_key"] not in text and not re.search(template["text_pattern"], text):
                continue
            rel = self.rel(path)
            try:
                doc = _parse_json_lines(text) if text.lstrip().startswith("{") else _Yaml(text).parse()
            except (ParseError, IndexError, json.JSONDecodeError, RecursionError) as exc:
                self.unresolved("parse-error", rel, rel, getattr(exc, "line", 0), f"could not read this file: {exc}")
                continue
            resources = doc.value.get("Resources") if isinstance(doc.value, dict) else None
            if resources is None or not isinstance(resources.value, dict):
                continue
            types = [
                _plain(entry.value["Type"])
                for entry in resources.value.values()
                if isinstance(entry.value, dict) and "Type" in entry.value
            ]
            declared = template["version_key"] in doc.value
            if not declared and not any(isinstance(t, str) and re.search(template["type_pattern"], t) for t in types):
                continue
            self.files["cloudformation"].append(rel)
            CloudFormationTemplate(self, path, doc, template).run()

    def _walk(self, root: Path) -> list[Path]:
        found = []
        for path in sorted(root.rglob("*")):
            parts = path.relative_to(root).parts
            if any(part in SKIP_DIRS for part in parts):
                continue
            if path.is_file():
                found.append(path)
        return found

    def read_export(self, rows: list[dict[str, Any]], file: str) -> None:
        for index, row in enumerate(rows):
            name = row["name"]
            raw = Raw(f"export:{index}:{name}", "export", row["type"], name, file, index + 1, {}, {}, [], "managed")
            raw.scope_rg = row.get("resource_group")
            raw.scope = {k: v for k, v in row.get("scope", {}).items() if v}
            raw.tree["location"] = row.get("location")
            self.raws.append(raw)

    # ---- analysis

    def build(self) -> dict[str, Res]:
        resources: dict[str, Res] = {}
        for raw in self.raws:
            res = _make_res(self, raw)
            resources[res.id] = res
        expanded = list(resources.values())
        for res in expanded:
            for child in _inline_children(self, res):
                resources[child.id] = child
        by_key = {(r.type.lower(), r.name.lower()): r for r in resources.values() if isinstance(r.name, str)}
        for res in resources.values():
            res.link(resources, by_key)
        for res in resources.values():
            res.compute_nesting(resources)
        return resources

    def report_names(self, resources: dict[str, Res]) -> None:
        for res in resources.values():
            if isinstance(res.name, Unknown):
                # A resource with no name attribute of its own (an association, for example) is not a dynamic name.
                self.unresolved(
                    "dynamic-name", res.id, res.raw.file, res.raw.line, f"the name depends on {res.name.text}"
                )
            if res.provider is None and res.raw.fmt != "export":
                self.unresolved(
                    "unknown-type",
                    res.id,
                    res.raw.file,
                    res.raw.line,
                    f"{res.raw.source_type} is not in any provider file",
                )


@dataclass
class Res:
    id: str
    raw: Raw
    provider: Provider | None
    spec: dict[str, Any]
    type: str
    category: str
    kind: str
    label: str
    name: Any
    attrs: dict[str, Any] = field(default_factory=dict)
    attr_lines: dict[str, int] = field(default_factory=dict)
    attr_paths: dict[str, str] = field(default_factory=dict)  # where each value of a list attribute came from
    parent: str | None = None
    children: list[Res] = field(default_factory=list)
    refs: list[dict[str, Any]] = field(default_factory=list)
    referrers: list[Res] = field(default_factory=list)
    nesting: dict[str, Any] = field(default_factory=dict)
    placed: dict[str, Res] = field(default_factory=dict)
    placed_more: dict[str, list[Res]] = field(default_factory=dict)  # a service can span several subnets
    exposure: dict[str, Any] | None = None

    def link(self, resources: dict[str, Res], by_key: dict[tuple[str, str], Res]) -> None:
        provider = self.provider
        table = provider.table if provider else {}
        placement = table.get("placement", [])
        fmt_key = _fmt_key(self.raw.fmt)
        placement_paths = {p: entry for entry in placement for p in entry.get(fmt_key, [])}
        parent_paths = set(self.spec.get("parent", {}).get(fmt_key, []))
        seen: set[tuple[str, str]] = set()
        for ref in self.raw.refs:
            target_id = ref["to"]
            if target_id.startswith("arm:"):
                arm_type, _, arm_name = target_id[4:].rpartition("/")
                target = by_key.get((arm_type.lower(), arm_name.lower()))
                if target is None:
                    continue
                target_id = target.id
            elif target_id.startswith("arm-symbol:"):
                continue
            if target_id not in resources or target_id == self.id:
                continue
            via = ref["via"]
            base_via = re.sub(r"\[\d+\]", "", via)
            kind = "uses"
            if base_via in placement_paths or via in placement_paths:
                kind = "placement"
                entry = placement_paths.get(base_via) or placement_paths[via]
                if entry["level"] in self.placed and self.placed[entry["level"]].id != target_id:
                    self.placed_more.setdefault(entry["level"], []).append(resources[target_id])
                self.placed.setdefault(entry["level"], resources[target_id])
            elif base_via in parent_paths or via in parent_paths or via == "parent":
                kind = "parent"
                self.parent = self.parent or target_id
            key = (target_id, via)
            if key in seen:
                continue
            seen.add(key)
            self.refs.append({"to": target_id, "via": via, "line": ref["line"], "kind": kind})
            resources[target_id].referrers.append(self)
        if self.raw.parent and self.parent is None:
            self.parent = self.raw.parent
        if self.parent and self.parent in resources:
            parent_res = resources[self.parent]
            parent_res.children.append(self)
        for level, entry in {e["level"]: e for e in placement}.items():
            if level in self.placed:
                continue
            for path in entry.get(fmt_key, []):
                hits = _walk(self.raw.tree, path.split("."))
                if hits and isinstance(hits[0][0], str):
                    self.nesting.setdefault(level, hits[0][0])
                    break

    def compute_nesting(self, resources: dict[str, Res]) -> None:
        table = self.provider.table if self.provider else {}
        levels = table.get("levels", [])
        if self.raw.fmt in ("bicep", "export") and self.raw.scope_rg and "resource_group" in levels:
            self.nesting.setdefault("resource_group", self.raw.scope_rg)
        for level, value in self.raw.scope.items():
            if level in levels:
                self.nesting.setdefault(level, value)
        # Inherit from what this resource sits inside or is placed in: its parent, then the subnet, VNet and group.
        sources: list[Res] = list(self.placed.values())
        if self.parent and self.parent in resources:
            sources.insert(0, resources[self.parent])
        for level, target in self.placed.items():
            self.nesting.setdefault(level, _name_of(target))
        seen: set[str] = set()
        for source in sources:
            for level, value in self._nesting_of(source, resources, seen).items():
                if value is not None:  # a level one source leaves open can still come from the next one
                    self.nesting.setdefault(level, value)
        for level in levels:
            self.nesting.setdefault(level, None)

    def _nesting_of(self, res: Res, resources: dict[str, Res], seen: set[str]) -> dict[str, Any]:
        if res.id in seen:
            return {}
        seen.add(res.id)
        out: dict[str, Any] = {k: v for k, v in res.nesting.items() if v is not None}
        for level, target in res.placed.items():
            out.setdefault(level, _name_of(target))
            for up_level, value in self._nesting_of(target, resources, seen).items():
                out.setdefault(up_level, value)
        if res.parent and res.parent in resources:
            for up_level, value in self._nesting_of(resources[res.parent], resources, seen).items():
                out.setdefault(up_level, value)
        if res.provider and res.type == res.provider.table["placement"][0].get("target"):
            out.setdefault(res.provider.table["placement"][0]["level"], _name_of(res))
        return out

    def location(self) -> Any:
        """The resource's own location, or the level that says where it is for a provider with no such attribute."""
        location = self.raw.tree.get("location")
        if location is None and self.provider:
            level = self.provider.table.get("location_level")
            if level:
                return self.nesting.get(level)
        return location

    def row(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "provider": self.provider.name if self.provider else None,
            "format": self.raw.fmt,
            "mode": self.raw.mode,
            "type": self.type,
            "source_type": self.raw.source_type,
            "category": self.category,
            "kind": self.kind,
            "label": self.label,
            "name": self.name if isinstance(self.name, str) else None,
            "file": self.raw.file,
            "line": self.raw.line,
            "module": self.raw.module,
            "parent": self.parent,
            "nesting": self.nesting,
            "location": _plain_value(self.location()),
            "attributes": {k: _plain_value(v) for k, v in self.attrs.items()},
            "references": self.refs,
        }
        if self.placed_more:
            out["also_in"] = {level: [_name_of(r) for r in more] for level, more in self.placed_more.items()}
        if isinstance(self.name, Unknown):
            out["name_unknown"] = self.name.text
        if self.raw.repeated:
            out["repeated"] = self.raw.repeated
        if self.raw.conditional:
            out["conditional"] = True
        if self.exposure:
            out["exposure"] = self.exposure
        return out


def _fmt_key(fmt: str) -> str:
    return FORMAT_KEYS.get(fmt, "arm")


def _name_of(res: Res) -> Any:
    return res.name if isinstance(res.name, str) else f"<{res.id}>"


def _named_pair(item: dict[str, Any]) -> tuple[str, str, str] | None:
    """A {name, value} setting in either spelling: its name key, its value key and the name itself."""
    for name_key, value_key in (("name", "value"), ("Name", "Value")):
        if isinstance(item.get(name_key), str) and value_key in item:
            return name_key, value_key, item[name_key]
    return None


def _plain_value(value: Any) -> Any:
    if isinstance(value, Unknown):
        return str(value)
    if isinstance(value, dict):
        return {k: _plain_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain_value(v) for v in value]
    return value


def _is_secret_text(name: str, value: Any, provider: Provider | None) -> bool:
    """Would printing this value show a secret? Decided by the setting's name and by what the text looks like."""
    text = value.literal if isinstance(value, Unknown) else value
    if not isinstance(text, str) or not text:
        return False
    if provider and any(re.search(p, text) for p in provider.table.get("secret_references", [])):
        return False
    named = bool(SECRET_NAME.search(name))
    if isinstance(value, Unknown):
        return any(p.search(text) for p in SECRET_VALUE[:3])
    if named or any(p.search(text) for p in SECRET_VALUE):
        return True
    return _looks_random(text)


def _looks_random(text: str) -> bool:
    if not LONG_RANDOM.match(text) or re.fullmatch(r"[0-9a-fA-F-]{36}", text):
        return False
    has_upper = any(c.isupper() for c in text)
    has_lower = any(c.islower() for c in text)
    has_digit = any(c.isdigit() for c in text)
    return (has_upper and has_lower and has_digit) or bool(re.fullmatch(r"[0-9a-fA-F]{40,}", text))


def _scrub_tree(value: Any, key: str, inv: Inventory, provider: Provider | None) -> Any:
    """Walk an evaluated tree and replace every value that looks like a secret with the marker. A {name, value}
    pair is treated as one named setting."""
    if isinstance(value, dict):
        pair = _named_pair(value)
        if pair is not None:
            out = dict(value)
            out[pair[1]] = _scrub_tree(value[pair[1]], pair[2], inv, provider)
            return out
        return {k: _scrub_tree(v, k, inv, provider) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub_tree(v, key, inv, provider) for v in value]
    if _is_secret_text(key, value, provider):
        literal = value.literal if isinstance(value, Unknown) else value
        if isinstance(literal, str) and len(literal) >= 4:
            inv.secret_values.add(literal)
        return SECRET_MARK
    return value


def _make_res(inv: Inventory, raw: Raw) -> Res:
    provider, native = inv.provider_of_type(raw.source_type, raw.fmt)
    spec: dict[str, Any] = provider.table["types"][native] if provider and native else {}
    raw.tree = _scrub_tree(raw.tree, "", inv, provider)
    res = Res(
        raw.rid,
        raw,
        provider,
        spec,
        native or raw.source_type,
        spec.get("category", "other"),
        spec.get("kind", "service"),
        spec.get("label", raw.source_type),
        _resource_name(raw, spec, provider),
    )
    if res.name is MISSING:
        res.name = None
    fmt_key = _fmt_key(raw.fmt)
    for attr, attr_spec in spec.get("attrs", {}).items():
        if attr_spec.get("text_json") and isinstance(raw.tree.get(attr_spec["text_json"]), str):
            _parse_text_json(raw.tree, attr_spec["text_json"])
        hits: list[tuple[Any, str]] = []
        for path in _as_list(attr_spec.get(fmt_key, [])):
            hits = _walk(raw.tree, path.split("."))
            if hits:
                break
        if not hits:
            continue
        if attr_spec.get("shape") == "settings":
            res.attrs[attr] = _settings(hits, raw, res, attr)
            continue
        values = [_normalise(hit[0], attr_spec, fmt_key) for hit in hits]
        res.attrs[attr] = values[0] if len(values) == 1 else values
        res.attr_lines[attr] = raw.lines.get(hits[0][1], raw.line)
        for index, hit in enumerate(hits):
            res.attr_paths[f"{attr}[{index}]"] = hit[1]
    return res


def _parse_text_json(tree: dict[str, Any], key: str) -> None:
    """A policy written as a JSON string (a heredoc, say) is read like the same policy written as an object."""
    with contextlib.suppress(json.JSONDecodeError):
        tree[key] = json.loads(tree[key])


def _resource_name(raw: Raw, spec: dict[str, Any], provider: Provider | None) -> Any:
    fmt_key = _fmt_key(raw.fmt)
    for path in _as_list(spec.get("name", {}).get(fmt_key, [])):
        hits = _walk(raw.tree, path.split("."))
        if hits:
            return hits[0][0]
    tag = provider.table.get("name_tag") if provider else None
    if tag:
        hits = _walk(raw.tree, tag[fmt_key].split(".")) if tag.get(fmt_key) else []
        tags = hits[0][0] if hits else None
        if isinstance(tags, dict) and tag["key"] in tags:
            return tags[tag["key"]]
        for entry in tags if isinstance(tags, list) else []:
            if isinstance(entry, dict) and entry.get("Key") == tag["key"]:
                return entry.get("Value")
    return raw.tree.get("name", raw.name)


def _normalise(value: Any, spec: dict[str, Any], fmt_key: str) -> Any:
    if spec.get("bool") and isinstance(value, str):
        lowered = value.lower()
        if lowered in ("enabled", "true"):
            value = True
        elif lowered in ("disabled", "false"):
            value = False
    if spec.get("invert") and fmt_key == "arm" and isinstance(value, bool):
        return not value
    return value


def _settings(hits: list[tuple[Any, str]], raw: Raw, res: Res, attr: str) -> dict[str, Any]:
    """App settings, named: a map, or a list of {name, value} pairs, in one shape."""
    out: dict[str, Any] = {}
    for value, path in hits:
        items: list[tuple[str, Any, str]] = []
        pair = _named_pair(value) if isinstance(value, dict) else None
        if isinstance(value, dict) and pair is not None:
            items.append((pair[2], value[pair[1]], path))
        elif isinstance(value, dict):
            items += [(k, v, f"{path}.{k}") for k, v in value.items()]
        elif isinstance(value, list):
            for index, item in enumerate(value):
                if isinstance(item, dict) and ("name" in item or "Name" in item):
                    name = str(item.get("name", item.get("Name")))
                    setting = next(
                        (item[k] for k in ("value", "Value", "secretRef", "secret_name") if k in item),
                        None,
                    )
                    items.append((name, setting, f"{path}[{index}]"))
        else:
            out["(unknown)"] = value
            continue
        for name, setting, here in items:
            out[name] = setting
            res.attr_lines[f"{attr}.{name}"] = raw.lines.get(
                here, raw.lines.get(f"{here}.value", raw.lines.get(f"{here}.Value", raw.line))
            )
    res.attr_lines[attr] = raw.lines.get(hits[0][1], raw.line)
    return out


def _inline_children(inv: Inventory, res: Res) -> list[Res]:
    if res.provider is None:
        return []
    fmt_key = _fmt_key(res.raw.fmt)
    out = []
    for rule in res.provider.table.get("inline_children", {}).get(res.type, []):
        path = rule.get(fmt_key)
        if not path:
            continue
        for value, concrete in _walk(res.raw.tree, path.split(".")):
            items = (
                [(value, concrete)]
                if isinstance(value, dict)
                else ([] if not isinstance(value, list) else [(v, f"{concrete}[{i}]") for i, v in enumerate(value)])
            )
            for item, item_path in items:
                if not isinstance(item, dict):
                    continue
                name = item.get("name")
                suffix = name if isinstance(name, str) else item_path
                child_lines = {
                    k[len(item_path) + 1 :]: v for k, v in res.raw.lines.items() if k.startswith(f"{item_path}.")
                }
                wrap = rule.get("wrap") if fmt_key != "tf" else None
                if wrap:  # a resource declared alone holds these fields under its Properties
                    item = {wrap: item}
                    child_lines = {f"{wrap}.{k}": v for k, v in child_lines.items()}
                native = rule["type"]
                line = res.raw.lines.get(item_path, res.raw.line)
                raw = Raw(
                    f"{res.id}/{suffix}",
                    res.raw.fmt,
                    native
                    if res.raw.fmt != "terraform"
                    else res.provider.table["types"][native]["tf"][0]
                    if res.provider.table["types"][native].get("tf")
                    else native,
                    name,
                    res.raw.file,
                    line,
                    item,
                    child_lines,
                    [],
                    res.raw.mode,
                    res.raw.module,
                    "",
                    False,
                    res.id,
                )
                raw.scope_rg = res.raw.scope_rg
                raw.scope_rg_id = res.raw.scope_rg_id
                out.append(_make_res(inv, raw))
    return out


# ---------------------------------------------------------------------------- conditions (exposure and checks)


UNKNOWN_RESULT = "unknown"


def holds(res: Res, cond: dict[str, Any], resources: dict[str, Res]) -> Any:
    """Does the provider file's condition hold for a resource? Returns where it holds (a dict) when it does,
    None when it does not, and UNKNOWN_RESULT when the code does not say."""
    if cond.get("always"):
        return {"file": res.raw.file, "line": res.raw.line}
    if "all" in cond:
        last = None
        for sub in cond["all"]:
            result = holds(res, sub, resources)
            if result is None:
                return None
            if result == UNKNOWN_RESULT:
                return UNKNOWN_RESULT
            last = result
        return last
    if "any" in cond:
        unknown = False
        for sub in cond["any"]:
            result = holds(res, sub, resources)
            if result == UNKNOWN_RESULT:
                unknown = True
            elif result is not None:
                return result
        return UNKNOWN_RESULT if unknown else None
    if "not" in cond:
        result = holds(res, cond["not"], resources)
        if result == UNKNOWN_RESULT:
            return UNKNOWN_RESULT
        return None if result is not None else {"file": res.raw.file, "line": res.raw.line}
    if "attr" in cond:
        return _holds_attr(res, cond)
    if "format" in cond:
        return {"file": res.raw.file, "line": res.raw.line} if res.raw.fmt == cond["format"] else None
    if "item_in" in cond:
        return _holds_item(res, cond)
    if "refers" in cond:
        return _holds_refers(res, cond, resources)
    if "secret_in" in cond:
        settings = res.attrs.get(cond["secret_in"])
        if isinstance(settings, dict):
            for key, value in settings.items():
                if value == SECRET_MARK:
                    return {
                        "file": res.raw.file,
                        "line": res.attr_lines.get(f"{cond['secret_in']}.{key}", res.raw.line),
                        "detail": key,
                    }
        return None
    if "child" in cond:
        wanted = _as_list(cond["child"])
        unknown = False
        for child in _descendants(res):
            if child.type not in wanted:
                continue
            if "where" not in cond:
                return {"file": child.raw.file, "line": child.raw.line, "resource": child.id}
            result = holds(child, cond["where"], resources)
            if result == UNKNOWN_RESULT:
                unknown = True
            elif result is not None:
                return {**result, "resource": child.id}
        return UNKNOWN_RESULT if unknown else None
    if "referred_by" in cond:
        wanted = _as_list(cond["referred_by"])
        for other in res.referrers:
            if other.type in wanted:
                return {"file": other.raw.file, "line": other.raw.line, "resource": other.id}
        return None
    if "parent" in cond:
        if res.parent is None or res.parent not in resources:
            return None
        return holds(resources[res.parent], cond["parent"], resources)
    raise ValueError(f"unknown condition: {cond}")


def _holds_refers(res: Res, cond: dict[str, Any], resources: dict[str, Res]) -> Any:
    wanted = _as_list(cond["refers"])
    unknown = False
    for ref in res.refs:
        target = resources.get(ref["to"])
        if target is None or target.type not in wanted:
            continue
        if "where" not in cond:
            return {"file": res.raw.file, "line": ref["line"], "resource": target.id}
        result = holds(target, cond["where"], resources)
        if result == UNKNOWN_RESULT:
            unknown = True
        elif result is not None:
            return {**result, "resource": target.id}
    return UNKNOWN_RESULT if unknown else None


def _flat(value: Any) -> list[Any]:
    if isinstance(value, dict):
        return [item for sub in value.values() for item in _flat(sub)]
    if isinstance(value, list):
        return [item for sub in value for item in _flat(sub)]
    return [value]


def _field_holds(item: dict[str, Any], test: dict[str, Any]) -> bool:
    names = _as_list(test["field"])
    present = next((name for name in names if name in item), None)
    if test.get("missing"):
        return present is None
    value = item.get(present) if present else None
    if "not" in test:
        return bool(value != test["not"])
    if present is None:
        return False
    if "is" in test:
        return bool(value == test["is"])
    if "in" in test:
        return bool(value in test["in"])
    if "matches" in test:
        return any(isinstance(text, str) and re.search(test["matches"], text) for text in _flat(value))
    raise ValueError(f"unknown field test: {test}")


def _holds_item(res: Res, cond: dict[str, Any]) -> Any:
    """Does one entry of a list attribute (a policy's statements, say) satisfy all the field tests together?"""
    attr = cond["item_in"]
    value = res.attrs.get(attr, MISSING)
    if value is MISSING:
        return None
    if isinstance(value, Unknown):
        return UNKNOWN_RESULT
    items = value if isinstance(value, list) else [value]
    for index, item in enumerate(items):
        if isinstance(item, dict) and all(_field_holds(item, test) for test in cond["where"]):
            path = res.attr_paths.get(f"{attr}[{index}]", "")
            line = res.attr_lines.get(attr, res.raw.line)
            for test in cond["where"]:
                for name in _as_list(test["field"]):
                    if not test.get("missing") and f"{path}.{name}" in res.raw.lines:
                        line = res.raw.lines[f"{path}.{name}"]
            return {"file": res.raw.file, "line": line}
    return None


def _as_list(value: Any) -> list[str]:
    return value if isinstance(value, list) else [value]


def _descendants(res: Res) -> list[Res]:
    out = []
    stack = list(res.children)
    while stack:
        child = stack.pop(0)
        out.append(child)
        stack = [*child.children, *stack]
    return out


def _holds_attr(res: Res, cond: dict[str, Any]) -> Any:
    name = cond["attr"]
    value = res.attrs.get(name, MISSING)
    if cond.get("missing"):
        if value is MISSING:
            return {"file": res.raw.file, "line": res.raw.line}
        return None
    if cond.get("present"):
        if isinstance(value, Unknown):
            return UNKNOWN_RESULT
        return (
            {"file": res.raw.file, "line": res.attr_lines.get(name, res.raw.line)}
            if value not in (MISSING, None, False, [], {})
            else None
        )
    if value is MISSING:
        return None
    if isinstance(value, Unknown):
        return UNKNOWN_RESULT
    where = {"file": res.raw.file, "line": res.attr_lines.get(name, res.raw.line)}
    if "is" in cond:
        return where if value == cond["is"] else None
    if "in" in cond:
        return where if value in cond["in"] else None
    if "below" in cond:
        return where if isinstance(value, int | float) and value < cond["below"] else None
    if "matches" in cond:
        texts = _flat(value)
        if any(isinstance(t, Unknown) for t in texts) and not any(
            isinstance(t, str) and re.search(cond["matches"], t) for t in texts
        ):
            return UNKNOWN_RESULT
        return where if any(isinstance(t, str) and re.search(cond["matches"], t) for t in texts) else None
    raise ValueError(f"unknown condition: {cond}")


def exposure_of(resources: dict[str, Res]) -> dict[str, Any]:
    states: dict[str, list[dict[str, Any]]] = {"public": [], "restricted": [], "private": [], "unknown": []}
    for res in resources.values():
        if res.provider is None or res.raw.fmt == "export":
            continue
        for entry in res.provider.table.get("exposure", []):
            if res.type not in entry["types"]:
                continue
            for rule in entry["rules"]:
                result = holds(res, rule["when"], resources)
                if result is None:
                    continue
                state = UNKNOWN_RESULT if result == UNKNOWN_RESULT else rule["state"]
                why = "the code does not say" if result == UNKNOWN_RESULT else rule["why"]
                anonymous = bool(rule.get("anonymous")) and result != UNKNOWN_RESULT
                where = result if result != UNKNOWN_RESULT else {"file": res.raw.file, "line": res.raw.line}
                res.exposure = {
                    "state": state,
                    "why": why,
                    "anonymous": anonymous,
                    "where": where,
                    "passes_through": bool(rule.get("passes_through")),
                }
                states[state].append(
                    {
                        "id": res.id,
                        "name": _name_of(res),
                        "why": why,
                        "anonymous": anonymous,
                        "file": where["file"],
                        "line": where["line"],
                    }
                )
                break
            break
    stops = _stops(resources)
    return {
        **states,
        "stops": [{"id": r.id, "name": _name_of(r), "why": why} for r, why in stops],
        "permissive_rules": _permissive_rules(resources),
        "reach": _reach(resources, {r.id for r, _ in stops}),
        "note": "A resource is public when any address on the internet can reach it, with or without a sign-in. "
        "Reach follows references from public compute and edge resources to what they call, and stops at a firewall, "
        "a WAF, or a private boundary. A reference is a place to look, not a proven request path: confirm each one "
        "in the code.",
    }


def _stops(resources: dict[str, Res]) -> list[tuple[Res, str]]:
    found: list[tuple[Res, str]] = []
    for res in resources.values():
        if res.provider is None:
            continue
        # A service with no address of its own still gets what a load balancer sends it, so it is not a stop.
        if res.exposure and res.exposure["state"] == "private" and not res.exposure["passes_through"]:
            found.append((res, res.exposure["why"]))
            continue
        for rule in res.provider.table.get("boundaries", []):
            if res.type in rule["types"]:
                result = holds(res, rule["when"], resources)
                if result is not None and result != UNKNOWN_RESULT:
                    found.append((res, rule["why"]))
                    break
    return found


def _permissive_rules(resources: dict[str, Res]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for res in resources.values():
        if res.provider is None:
            continue
        check = next(
            (c for c in res.provider.table.get("checks", []) if c["family"] == "network" and res.type in c["types"]),
            None,
        )
        if check is None:
            continue
        where = holds(res, check["when"], resources)
        if where is None or where == UNKNOWN_RESULT:
            continue
        attached: set[str] = set()
        container = resources.get(res.parent) if res.parent else None
        for owner in [r for r in ([container] if container else []) if r]:
            for referrer in owner.referrers:
                attached.add(referrer.id)
                attached |= {ref["to"] for ref in referrer.refs if resources[ref["to"]].category == "network"}
        out.append(
            {
                "id": res.id,
                "name": _name_of(res),
                "port": _plain_value(res.attrs.get("port")),
                "source": _plain_value(res.attrs.get("source")),
                "file": where["file"],
                "line": where["line"],
                "attached_to": sorted(attached),
            }
        )
    return out


TRAFFIC_FROM = {"compute", "edge"}
TRAFFIC_TO = {"compute", "edge", "database", "storage", "messaging", "secrets"}


def _traffic_edges(resources: dict[str, Res]) -> dict[str, list[tuple[str, str]]]:
    edges: dict[str, list[tuple[str, str]]] = {}
    for res in resources.values():
        if res.category not in TRAFFIC_FROM:
            continue
        not_traffic = res.provider.table.get("not_traffic", []) if res.provider else []
        reversed_vias = set(res.provider.table.get("traffic_reversed", [])) if res.provider else set()
        for ref in res.refs:
            if ref["kind"] != "uses" or resources[ref["to"]].category not in TRAFFIC_TO:
                continue
            base_via = re.sub(r"\[\d+\]", "", ref["via"])
            if any(base_via == prefix or base_via.startswith(f"{prefix}.") for prefix in not_traffic):
                continue
            if base_via in reversed_vias:
                # The backend names the front, as a listener names its load balancer; traffic runs the other way.
                edges.setdefault(ref["to"], []).append((res.id, ref["via"]))
            else:
                edges.setdefault(res.id, []).append((ref["to"], ref["via"]))
    return edges


def _reach(resources: dict[str, Res], stops: set[str]) -> list[dict[str, Any]]:
    edges = _traffic_edges(resources)
    start = [r.id for r in resources.values() if r.exposure and r.exposure["state"] == "public"]
    previous: dict[str, str | None] = dict.fromkeys(start)
    queue: deque[str] = deque(start)
    while queue:
        node = queue.popleft()
        if node in stops:
            continue
        for target, _ in edges.get(node, []):
            if target not in previous:
                previous[target] = node
                queue.append(target)
    out = []
    for target in previous:
        path = [target]
        while previous[path[0]] is not None:
            path.insert(0, previous[path[0]])  # type: ignore[arg-type]
        res = resources[target]
        out.append(
            {
                "to": target,
                "name": _name_of(res),
                "category": res.category,
                "path": ["internet", *path],
                "hops": len(path),
                "direct": len(path) == 1,
                "behind_stop": target in stops,
            }
        )
    return out


def run_checks(resources: dict[str, Res]) -> dict[str, list[dict[str, Any]]]:
    hits: dict[str, list[dict[str, Any]]] = {}
    for res in resources.values():
        if res.provider is None or res.raw.mode != "managed":
            continue
        for check in res.provider.table.get("checks", []):
            if res.type not in check["types"]:
                continue
            result = holds(res, check["when"], resources)
            if result is None or result == UNKNOWN_RESULT:
                continue
            hits.setdefault(check["family"], []).append(
                {
                    "check": check["id"],
                    "pillar": check["pillar"],
                    "resource": res.id,
                    "name": _name_of(res),
                    "type": res.type,
                    "file": result["file"],
                    "line": result["line"],
                    "what": check["what"],
                    "detail": result.get("detail"),
                }
            )
    for family in hits:
        hits[family].sort(key=lambda h: (h["file"], h["line"], h["check"]))
    return dict(sorted(hits.items()))


# ---------------------------------------------------------------------------- comparison


def _export_row_from_shape(row: dict[str, Any], shapes: list[dict[str, Any]], id_types: list[dict[str, Any]]) -> Any:
    """A row of a provider's export whose fields are not `type` and `name`: the provider file says how to read it."""
    for shape in shapes:
        if shape["requires"] not in row:
            continue
        resource_id = str(row.get(shape["id"]) or "")
        parts = {k: v for k, v in row.items() if isinstance(v, str)}
        name: Any = None
        rtype = row.get(shape["type"]) if "type" in shape else None
        for name_field in _as_list(shape.get("name", [])):
            if row.get(name_field):
                name = str(row[name_field])
                break
        if shape.get("id_pattern"):
            match = re.search(shape["id_pattern"], resource_id)
            if match is None:
                return None
            parts = {**parts, **{k: v for k, v in match.groupdict().items() if v}}
            kind = next(
                (
                    t
                    for t in id_types
                    if t["service"] == parts.get("service") and re.search(t["resource"], parts["resource"])
                ),
                None,
            )
            if kind is None:
                rtype = f"{parts.get('service')}:{parts['resource'].split('/')[0].split(':')[0]}"
                name = parts["resource"].rsplit("/", 1)[-1].rsplit(":", 1)[-1]
            else:
                found = re.search(kind["resource"], parts["resource"])
                assert found is not None
                rtype, name = kind["type"], found.groupdict().get("name")
                tags = row.get(shape.get("tags", ""))
                if kind.get("name_tag") and isinstance(tags, list):
                    tagged = next((t.get("Value") for t in tags if t.get("Key") == kind["name_tag"]), None)
                    name = tagged or name
        if not rtype or not name:
            return None
        scope = {level: parts.get(field) for level, field in shape.get("scope", {}).items()}
        return {
            "id": resource_id,
            "type": str(rtype),
            "name": str(name),
            "resource_group": None,
            "location": parts.get(shape.get("location", "")),
            "scope": scope,
        }
    return None


def read_export_file(path: Path, providers: dict[str, Provider] | None = None) -> list[dict[str, Any]]:
    """Only the fields a comparison needs. An export can carry settings and keys in `properties`: never touched."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    rows: Any = doc
    exports = [p.table.get("export", {}) for p in (providers or {}).values()]
    if isinstance(doc, dict):
        rows = doc.get("data", doc.get("value", doc.get("Resources")))
        if rows is None:
            keys = [k for e in exports for k in e.get("list_keys", [])]
            rows = next((doc[k] for k in keys if k in doc), None)
    if isinstance(rows, dict) and "columns" in rows and "rows" in rows:
        columns = [c["name"] for c in rows["columns"]]
        rows = [dict(zip(columns, row, strict=False)) for row in rows["rows"]]
    if not isinstance(rows, list):
        raise SystemExit(f"{path}: not a list of resources, or an object with data/value")
    shapes = [s for e in exports for s in e.get("row_shapes", [])]
    id_types = [t for e in exports for t in e.get("id_types", [])]
    out = []
    for row in rows:
        if isinstance(row, str):  # a query service can return each row as its own JSON text
            try:
                row = json.loads(row)
            except json.JSONDecodeError:
                continue
        if not isinstance(row, dict):
            continue
        shaped = _export_row_from_shape(row, shapes, id_types)
        if shaped is not None:
            out.append(shaped)
            continue
        if "type" not in row or "name" not in row:
            continue
        resource_id = str(row.get("id") or "")
        match = re.search(r"/subscriptions/([^/]+)", resource_id, re.IGNORECASE)
        out.append(
            {
                "id": resource_id,
                "type": str(row["type"]),
                "name": str(row["name"]),
                "resource_group": row.get("resourceGroup") or row.get("resourcegroup"),
                "location": row.get("location"),
                "scope": {"subscription": row.get("subscriptionId") or (match.group(1) if match else None)},
            }
        )
    return out


def _last_segment(name: str) -> str:
    return name.rsplit("/", 1)[-1].lower()


def compare(
    resources: dict[str, Res], rows: list[dict[str, Any]], providers: dict[str, Provider], file: str
) -> dict[str, Any]:
    ignored = []
    not_listed: set[str] = set()
    ignore_rules: list[dict[str, Any]] = []
    for provider in providers.values():
        export = provider.table.get("export", {})
        not_listed |= {t.lower() for t in export.get("not_listed", [])}
        ignore_rules += export.get("ignore", [])
    kept = []
    for row in rows:
        rule = next(
            (
                r
                for r in ignore_rules
                if r["type"].lower() == row["type"].lower() and ("name" not in r or re.search(r["name"], row["name"]))
            ),
            None,
        )
        if rule:
            ignored.append({"type": row["type"], "name": row["name"], "why": rule["why"]})
        else:
            kept.append(row)
    code = [r for r in resources.values() if r.raw.fmt != "export"]
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in kept:
        by_key.setdefault((row["type"].lower(), _last_segment(row["name"])), []).append(row)
    matched_rows: set[int] = set()
    in_both: list[dict[str, Any]] = []
    differences: list[dict[str, Any]] = []
    only_in_code: list[dict[str, Any]] = []
    not_comparable: list[dict[str, Any]] = []
    not_compared = 0
    for res in code:
        if res.provider is None or res.name is None or res.category == "scope" or res.type.lower() in not_listed:
            not_compared += 1
            continue
        if not isinstance(res.name, str):
            not_comparable.append(
                {
                    "id": res.id,
                    "type": res.type,
                    "why": f"the name is not known from the code: {res.name.text}",
                    "candidates": [],
                }
            )
            continue
        candidates = by_key.get((res.type.lower(), _last_segment(res.name)))
        if not candidates:
            if res.raw.mode == "managed":
                only_in_code.append(
                    {"id": res.id, "type": res.type, "name": res.name, "file": res.raw.file, "line": res.raw.line}
                )
            continue
        row = candidates[0]
        matched_rows.add(id(row))
        in_both.append({"id": res.id, "name": res.name, "type": res.type})
        location = _plain_value(res.location())
        if (
            isinstance(location, str)
            and isinstance(row["location"], str)
            and location.lower().replace(" ", "") != row["location"].lower().replace(" ", "")
        ):
            differences.append({"id": res.id, "field": "location", "code": location, "export": row["location"]})
    remaining = [r for r in kept if id(r) not in matched_rows]
    for entry in not_comparable:
        target = next(res for res in code if res.id == entry["id"])
        matches = [r for r in remaining if r["type"].lower() == target.type.lower()]
        entry["candidates"] = [r["name"] for r in matches]
        for match in matches:
            matched_rows.add(id(match))
    only_in_export = [
        {"name": r["name"], "type": r["type"], "resource_group": r["resource_group"], "location": r["location"]}
        for r in kept
        if id(r) not in matched_rows
    ]
    return {
        "export": file,
        "rows": len(rows),
        "ignored": ignored,
        "in_both": in_both,
        "only_in_code": only_in_code,
        "only_in_export": only_in_export,
        "not_comparable": not_comparable,
        "differences": differences,
        "not_compared": not_compared,
        "note": "Compared by type and name. Resources that an export of this kind does not list (subnets, firewall "
        "rules, queues and the like) were not compared. A row in not_comparable has candidates of the same type: a "
        "possible match that the code's name cannot confirm.",
    }


# ---------------------------------------------------------------------------- output


def _clean(value: Any, secrets: list[str]) -> Any:
    if isinstance(value, dict):
        return {k: _clean(v, secrets) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean(v, secrets) for v in value]
    if isinstance(value, str):
        text = value
        for secret in secrets:
            if secret and secret in text:
                text = text.replace(secret, SECRET_MARK)
        for pattern in SECRET_VALUE[:3]:
            text = pattern.sub(SECRET_MARK, text)
        return text
    return value


def run(repo: Path | None, export: Path | None, compare_path: Path | None, with_checks: bool) -> dict[str, Any]:
    providers = load_providers()
    if not providers:
        raise SystemExit(
            "no provider files found (cloud/*.json beside this script, or references/cloud/*.json in a skill)"
        )
    inv = Inventory(repo, providers)
    if repo is not None:
        inv.read_code()
    if export is not None:
        inv.read_export(read_export_file(export, providers), export.name)
    resources = inv.build()
    inv.report_names(resources)
    exposure = exposure_of(resources)
    rows = [res.row() for res in resources.values()]
    used_providers = sorted({r["provider"] for r in rows if r["provider"]})
    by_category = Counter(r["category"] for r in rows)
    by_type = Counter(r["type"] for r in rows)
    levels = {name: providers[name].table["levels"] for name in used_providers}
    result: dict[str, Any] = {
        "repo": str(repo) if repo else None,
        "providers": used_providers,
        "levels": levels,
        "read": inv.files,
        "not_read": inv.not_read,
        "summary": {
            "resources": len(rows),
            "managed": sum(1 for r in rows if r["mode"] == "managed"),
            "data_sources": sum(1 for r in rows if r["mode"] == "data"),
            "helpers_skipped": inv.helpers,
            "by_category": {c: by_category[c] for c in [*CATEGORIES, "scope", "other"] if by_category[c]},
            "by_type": dict(sorted(by_type.items())),
            "public": len(exposure["public"]),
            "restricted": len(exposure["restricted"]),
            "private": len(exposure["private"]),
            "unresolved": len(inv.unresolved_rows),
        },
        "resources": rows,
        "unresolved": inv.unresolved_rows,
        "exposure": exposure,
    }
    if compare_path is not None:
        result["compare"] = compare(resources, read_export_file(compare_path, providers), providers, compare_path.name)
    if with_checks:
        hits = run_checks(resources)
        result["checks"] = hits
        result["summary"]["check_hits"] = {family: len(items) for family, items in hits.items()}
    secrets = sorted(inv.secret_values, key=len, reverse=True)
    cleaned = _clean(result, secrets)
    assert isinstance(cleaned, dict)
    return cleaned


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inventory a repository's cloud infrastructure code.")
    parser.add_argument("repo", nargs="?", type=Path, help="the repository; leave it out with --from-export")
    parser.add_argument("--compare", type=Path, help="a saved export, for drift against the code")
    parser.add_argument("--from-export", type=Path, help="read an export instead of code")
    parser.add_argument("--checks", action="store_true", help="add review hits per family")
    args = parser.parse_args(argv)
    if args.repo is None and args.from_export is None:
        parser.error("give a repository or --from-export")
    if args.repo is not None and not args.repo.is_dir():
        print(f"not a directory: {args.repo}", file=sys.stderr)
        return 2
    for path in (args.compare, args.from_export):
        if path is not None and not path.is_file():
            print(f"not a file: {path}", file=sys.stderr)
            return 2
    result = run(args.repo.resolve() if args.repo else None, args.from_export, args.compare, args.checks)
    json.dump(result, sys.stdout, indent=1, ensure_ascii=False)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
