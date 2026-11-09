#!/usr/bin/env python3
"""Inventory the AI parts of a repository: what calls a model, with which settings, and what the model can reach.

Usage: python3 ai_inventory.py [REPO]

Prints JSON with file:line for every hit:
- sdks: model, agent and RAG libraries (openai, anthropic, Azure.AI.OpenAI, langchain, langgraph,
  llama_index, semantic_kernel, ollama, the Vercel AI SDK, ...)
- clients and model_calls: where a client is built and a model is called, and whether a timeout
  and retries are set there (a call with **kwargs is "unknown")
- models: model names in code and config, and whether each is dated, an alias, a tag or unstamped
- vector_stores, tracing, evals: what is there, and what is not
- tools: functions exposed to a model, with the side effects and outside fetches inside them
- loops: agent loops, and whether a step or cost limit is visible
- prompts, env_vars (names only, never values), secrets (kind and length only, never the value)
Python is read with the ast module, C#, TypeScript and JavaScript with patterns, so treat those
hits as leads to read. Never opens .env files. Read-only, standard library only.

Single source: shared/ai_inventory.py in claude-role-skills, copied into the skills that use it by
tools/sync_shared.py; edit the shared file, never a copy.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any

SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "env", "__pycache__", "dist", "build", "bin", "obj", ".next",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", "coverage", ".idea", ".vscode", "vendor",
}  # fmt: skip
CODE = {
    ".py": "python",
    ".cs": "csharp",
    ".ts": "ts",
    ".tsx": "ts",
    ".js": "js",
    ".mjs": "js",
    ".cjs": "js",
    ".jsx": "js",
}
CONFIG = {".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".env.example", ".example", ".md"}

# library -> category; matched against Python modules, C# namespaces and npm package names
LIBRARIES: dict[str, tuple[str, str]] = {
    r"openai|OpenAI|@azure/openai|Azure\.AI\.OpenAI": ("sdk", "OpenAI / Azure OpenAI"),
    r"anthropic|@anthropic-ai/sdk|Anthropic": ("sdk", "Anthropic"),
    r"google\.generativeai|google\.genai|vertexai|@google/generative-ai|@google/genai": ("sdk", "Google Gemini"),
    r"mistralai|@mistralai/mistralai": ("sdk", "Mistral"),
    r"cohere": ("sdk", "Cohere"),
    r"ollama|OllamaSharp": ("sdk", "Ollama"),
    r"litellm": ("sdk", "LiteLLM"),
    r"Azure\.AI\.Inference|azure\.ai\.inference": ("sdk", "Azure AI Inference"),
    r"Microsoft\.Extensions\.AI": ("sdk", "Microsoft.Extensions.AI"),
    r"ai|@ai-sdk/[\w-]+": ("sdk", "Vercel AI SDK"),
    r"transformers": ("sdk", "Hugging Face transformers"),
    r"langchain[\w.]*|@langchain/[\w-]+|LangChain": ("framework", "LangChain"),
    r"langgraph[\w.]*|@langchain/langgraph": ("framework", "LangGraph"),
    r"llama_index[\w.]*|llamaindex": ("framework", "LlamaIndex"),
    r"semantic_kernel|Microsoft\.SemanticKernel[\w.]*": ("framework", "Semantic Kernel"),
    r"haystack": ("framework", "Haystack"),
    r"dspy": ("framework", "DSPy"),
    r"crewai": ("framework", "CrewAI"),
    r"autogen[\w.]*": ("framework", "AutoGen"),
    r"pydantic_ai": ("framework", "Pydantic AI"),
    r"agents|@openai/agents": ("framework", "OpenAI Agents SDK"),
    r"smolagents": ("framework", "smolagents"),
    r"qdrant_client|@qdrant/js-client-rest|Qdrant\.Client": ("vector_store", "Qdrant"),
    r"chromadb": ("vector_store", "Chroma"),
    r"pinecone|@pinecone-database/pinecone": ("vector_store", "Pinecone"),
    r"weaviate": ("vector_store", "Weaviate"),
    r"pgvector": ("vector_store", "pgvector"),
    r"faiss": ("vector_store", "FAISS"),
    r"lancedb": ("vector_store", "LanceDB"),
    r"pymilvus": ("vector_store", "Milvus"),
    r"azure\.search\.documents|Azure\.Search\.Documents|@azure/search-documents": ("vector_store", "Azure AI Search"),
    r"elasticsearch|opensearchpy": ("vector_store", "Elasticsearch / OpenSearch"),
    r"langfuse": ("tracing", "Langfuse"),
    r"opentelemetry[\w.]*|@opentelemetry/[\w-]+|OpenTelemetry[\w.]*": ("tracing", "OpenTelemetry"),
    r"langsmith": ("tracing", "LangSmith"),
    r"phoenix|arize[\w.]*|openinference[\w.]*": ("tracing", "Arize Phoenix"),
    r"opik": ("tracing", "Opik"),
    r"helicone": ("tracing", "Helicone"),
    r"weave": ("tracing", "W&B Weave"),
    r"logfire": ("tracing", "Logfire"),
    r"traceloop[\w.]*": ("tracing", "OpenLLMetry"),
    r"mlflow": ("tracing", "MLflow"),
    r"ragas": ("eval", "Ragas"),
    r"deepeval": ("eval", "DeepEval"),
    r"promptfoo": ("eval", "promptfoo"),
    r"inspect_ai": ("eval", "Inspect"),
    r"openai_evals|evals": ("eval", "OpenAI evals"),
    r"trulens[\w.]*": ("eval", "TruLens"),
}
LIB_PATTERNS = [(re.compile(rf"^(?:{p})(?:$|[./])"), cat, name) for p, (cat, name) in LIBRARIES.items()]

MODEL_NAME = re.compile(
    r"^(?:gpt-[a-z0-9.-]+|o[1345](?:-[a-z0-9.-]+)?|chatgpt-[a-z0-9.-]+|claude-[a-z0-9.-]+|gemini-[a-z0-9.-]+|"
    r"text-embedding-[a-z0-9-]+|(?:llama|mistral|mixtral|qwen|gemma|deepseek)[a-z0-9.:-]*|phi-?\d[a-z0-9.:-]*|"
    r"command-[a-z0-9.-]+|(?:nomic-embed|mxbai-embed)[a-z0-9.:-]*|(?:bge|e5)-[a-z0-9.-]+)$",
    re.I,
)
DATED = re.compile(r"(?:\d{4}-\d{2}-\d{2}|\d{8}|-\d{3,4}$|@sha256:|@\d{3}$)")
ALIAS_FAMILIES = re.compile(r"^(?:gpt-|o\d|chatgpt-|claude-|gemini-)", re.I)
SECRETS = [
    ("openai-style key", re.compile(r"\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{16,}")),
    ("aws access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("google api key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("github token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    (
        "assigned secret",
        re.compile(r"""(?i)\b(?:api_?key|secret|password|passwd|token)\b["']?\s*[:=]\s*["'][^"'\s$<{]{12,}["']"""),
    ),
]
FAKE = re.compile(r"(?i)example|dummy|placeholder|changeme|test|xxxx|your[-_]")

# Python call names: what calls a model, builds a client, has a side effect or fetches outside content.
MODEL_CALLS = re.compile(
    r"(?:chat\.completions\.create|completions\.create|responses\.create|messages\.create|embeddings\.create|"
    r"generate_content|ollama\.chat|ollama\.generate|ollama\.embed\w*|litellm\.completion|\.invoke|\.ainvoke|"
    r"\.stream|\.astream|\.run|\.arun|\.kickoff|chat\.complete|embeddings\.embed|\.get_chat_message_content\w*)$"
)
CLIENTS = re.compile(
    r"(?:^|\.)(?:OpenAI|AsyncOpenAI|AzureOpenAI|AsyncAzureOpenAI|Anthropic|AsyncAnthropic|ChatOpenAI|AzureChatOpenAI|"
    r"ChatAnthropic|ChatOllama|Ollama|Client|AsyncClient|Mistral|ChatCompletionsClient|GenerativeModel)$"
)
SIDE_EFFECTS = re.compile(
    r"(?:smtplib\.SMTP\w*|\.send_message|\.sendmail|sendgrid\w*|\.messages\.send|"
    r"(?:httpx|requests|session|client)\.(?:post|put|patch|delete)|subprocess\.\w+|os\.system|os\.remove|"
    r"shutil\.rmtree|\.write_text|\.write_bytes|\.unlink|\.executemany)$"
)
FETCHES = re.compile(r"(?:httpx\.get|requests\.get|urlopen|urllib\.request\.urlopen|aiohttp\.\w+\.get|\.fetch)$")
LIMIT_WORDS = re.compile(r"(?i)step|turn|iter|count|budget|max|limit|hops|tries|attempt|round")

TS_CALLS = re.compile(
    r"\.(?:chat\.completions\.create|responses\.create|messages\.create|embeddings\.create)\(|"
    r"\b(?:generateText|streamText|generateObject|streamObject)\(|"
    r"\b(?:GetChatMessageContentAsync|GetChatMessageContentsAsync|CompleteChatAsync|GetChatCompletionsAsync|"
    r"GetResponseAsync|GetStreamingResponseAsync|InvokePromptAsync|GenerateEmbeddingsAsync)\("
)
TS_CLIENTS = re.compile(
    r"\bnew\s+(?:OpenAI|AzureOpenAI|Anthropic|OpenAIClient|AzureOpenAIClient|ChatClient|OllamaApiClient)\("
)
TS_TOOLS = re.compile(
    r"\[KernelFunction|AIFunctionFactory\.Create|ChatTool\.CreateFunctionTool|\btool\(\{|type:\s*['\"]function['\"]"
)
TS_LOOP = re.compile(r"\bwhile\s*\(\s*true\s*\)|\bfor\s*\(\s*;\s*;\s*\)")
TS_ENV = re.compile(
    r"process\.env\.([A-Z][A-Z0-9_]+)|process\.env\[['\"]([A-Z][A-Z0-9_]+)['\"]\]|"
    r"GetEnvironmentVariable\(\"([A-Z][A-Z0-9_]+)\"\)|Configuration\[\"([\w:]+)\"\]"
)
TS_IMPORT = re.compile(r"""(?:from\s+['"]([^'"]+)['"]|require\(\s*['"]([^'"]+)['"]\s*\)|^\s*using\s+([\w.]+)\s*;)""")
TS_SIDE = re.compile(
    r"\b(?:SendMailAsync|SmtpClient|sendMail|PostAsync|PutAsync|DeleteAsync|axios\.(?:post|put|delete)|method:\s*['\"](?:POST|PUT|DELETE))"
)
TS_FETCH = re.compile(r"\b(?:fetch\(|GetStringAsync\(|GetAsync\(|axios\.get\()")
STRING = re.compile(r"""["'`]([\w.:@/-]{3,80})["'`]""")


def library(module: str) -> tuple[str, str] | None:
    for pattern, category, name in LIB_PATTERNS:
        if pattern.match(module):
            return category, name
    return None


def model_kind(name: str) -> str:
    if DATED.search(name):
        return "dated"
    if "latest" in name.lower() or ALIAS_FAMILIES.match(name):
        return "alias"
    if ":" in name:
        return "tag"
    return "unstamped"


def _dotted(node: ast.AST) -> str:
    """client().chat.completions.create -> client.chat.completions.create"""
    parts: list[str] = []
    while True:
        if isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        elif isinstance(node, ast.Call):
            node = node.func
        elif isinstance(node, ast.Name):
            parts.append(node.id)
            break
        else:
            break
    return ".".join(reversed(parts))


def _keywords(call: ast.Call) -> tuple[set[str], bool]:
    names = {k.arg for k in call.keywords if k.arg}
    return names, any(k.arg is None for k in call.keywords)


class Inventory:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.out: dict[str, Any] = {
            "repo": str(root),
            "files": {},
            "sdks": [],
            "frameworks": [],
            "vector_stores": [],
            "tracing": [],
            "evals": [],
            "clients": [],
            "model_calls": [],
            "models": [],
            "tools": [],
            "loops": [],
            "prompts": [],
            "env_vars": [],
            "env_files_not_read": [],
            "secrets": [],
            "outside_content": [],
            "side_effects": [],
        }
        self.functions: dict[str, dict[str, Any]] = {}  # python functions by name: side effects and fetches inside
        self.tool_names: set[str] = set()
        self.tool_files: set[str] = set()
        self.model_files: set[str] = set()

    def hit(self, key: str, rel: str, line: int, **extra: Any) -> None:
        item = {"file": rel, "line": line, **extra}
        if item not in self.out[key]:
            self.out[key].append(item)

    def library_hit(self, module: str, rel: str, line: int) -> None:
        found = library(module)
        if found:
            category, name = found
            key = {"sdk": "sdks", "framework": "frameworks", "vector_store": "vector_stores"}.get(category, category)
            key = "evals" if key == "eval" else key
            self.hit(key, rel, line, name=name, module=module)
            if category in ("sdk", "framework"):
                self.model_files.add(rel)

    def strings(self, text: str, rel: str, line_of: Any) -> None:
        for kind, pattern in SECRETS:
            for m in pattern.finditer(text):
                value = m.group(0)
                self.hit(
                    "secrets",
                    rel,
                    line_of(m.start()),
                    kind=kind,
                    length=len(value),
                    looks_fake=bool(FAKE.search(value)),
                )

    def python(self, rel: str, text: str) -> None:
        try:
            tree = ast.parse(text)
        except SyntaxError:
            self.out.setdefault("unparsed", []).append(rel)
            return
        lines = text.splitlines()
        self.strings(text, rel, lambda pos: text.count("\n", 0, pos) + 1)
        if '"type": "function"' in text or "'type': 'function'" in text:
            self.tool_files.add(rel)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.library_hit(alias.name, rel, node.lineno)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                self.library_hit(node.module, rel, node.lineno)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                value = node.value.strip()
                if MODEL_NAME.match(value):
                    self.hit("models", rel, node.lineno, name=value, kind=model_kind(value))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                decorators = {_dotted(d).split(".")[-1] for d in node.decorator_list}
                if decorators & {"tool", "function_tool", "kernel_function", "ai_function"}:
                    self.tool_names.add(node.name)
                inner: dict[str, list[dict[str, Any]]] = {"side_effects": [], "fetches": []}
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Call):
                        name = _dotted(sub.func)
                        if SIDE_EFFECTS.search(name):
                            inner["side_effects"].append({"call": name, "line": sub.lineno})
                        if FETCHES.search(name) and not (sub.args and isinstance(sub.args[0], ast.Constant)):
                            inner["fetches"].append({"call": name, "line": sub.lineno})
                self.functions.setdefault(node.name, {"file": rel, "line": node.lineno, **inner})
            elif isinstance(node, ast.Call):
                name = _dotted(node.func)
                keys, spread = _keywords(node)
                if (name in ("os.getenv", "os.environ.get", "getenv", "environ.get")) and node.args:
                    first = node.args[0]
                    if isinstance(first, ast.Constant) and isinstance(first.value, str):
                        self.hit("env_vars", rel, node.lineno, name=first.value, literal_default=len(node.args) > 1)
                elif CLIENTS.search(name) and (rel in self.model_files or name.split(".")[-1] != "Client"):
                    self.hit(
                        "clients",
                        rel,
                        node.lineno,
                        call=name,
                        timeout="unknown (**kwargs)" if spread and "timeout" not in keys else "timeout" in keys,
                        retries="max_retries" in keys or "retries" in keys,
                    )
                elif MODEL_CALLS.search(name) and (rel in self.model_files or "create" in name):
                    if name.endswith((".run", ".arun", ".invoke", ".stream")) and rel not in self.model_files:
                        continue
                    self.hit(
                        "model_calls",
                        rel,
                        node.lineno,
                        call=name,
                        timeout="unknown (**kwargs)" if spread and "timeout" not in keys else "timeout" in keys,
                    )
            elif isinstance(node, ast.Subscript) and _dotted(node.value) in ("os.environ", "environ"):
                if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
                    self.hit("env_vars", rel, node.lineno, name=node.slice.value, literal_default=False)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and "PROMPT" in target.id.upper():
                        self.hit("prompts", rel, node.lineno, name=target.id)
        for node in ast.walk(tree):
            if isinstance(node, ast.While):
                forever = isinstance(node.test, ast.Constant) and node.test.value is True
                body_calls = {_dotted(c.func) for c in ast.walk(node) if isinstance(c, ast.Call)}
                calls_model = any(MODEL_CALLS.search(c) or c.endswith(("chat", "complete")) for c in body_calls)
                limited = any(
                    LIMIT_WORDS.search(ast.unparse(test))
                    for test in [node.test] + [n.test for n in ast.walk(node) if isinstance(n, ast.If)]
                )
                if calls_model or forever:
                    self.hit(
                        "loops",
                        rel,
                        node.lineno,
                        code=lines[node.lineno - 1].strip(),
                        calls_model=calls_model,
                        limit_visible=limited,
                    )

    def patterns(self, rel: str, text: str) -> None:
        lines = text.splitlines()
        self.strings(text, rel, lambda pos: text.count("\n", 0, pos) + 1)
        for no, line in enumerate(lines, 1):
            for m in TS_IMPORT.finditer(line):
                module = next(g for g in m.groups() if g)
                self.library_hit(module, rel, no)
            window = " ".join(lines[no - 1 : no + 4])
            if TS_CLIENTS.search(line):
                self.hit("clients", rel, no, call=line.strip()[:80], timeout=bool(re.search(r"(?i)timeout", window)))
            if TS_CALLS.search(line):
                self.hit(
                    "model_calls",
                    rel,
                    no,
                    call=line.strip()[:80],
                    timeout=bool(re.search(r"(?i)timeout|signal|CancellationToken", window)),
                )
            if TS_TOOLS.search(line):
                self.hit("tools", rel, no, name=line.strip()[:80], side_effects=[], fetches=[], exposed=True)
            if TS_LOOP.search(line):
                self.hit("loops", rel, no, code=line.strip()[:80], calls_model=None, limit_visible=False)
            if TS_SIDE.search(line):
                self.hit("side_effects", rel, no, call=line.strip()[:80], in_tool=None)
            if TS_FETCH.search(line):
                self.hit("outside_content", rel, no, call=line.strip()[:80], in_tool=None)
            for m in TS_ENV.finditer(line):
                self.hit("env_vars", rel, no, name=next(g for g in m.groups() if g), literal_default=None)
            for m in STRING.finditer(line):
                if MODEL_NAME.match(m.group(1)):
                    self.hit("models", rel, no, name=m.group(1), kind=model_kind(m.group(1)))

    def config(self, rel: str, text: str) -> None:
        self.strings(text, rel, lambda pos: text.count("\n", 0, pos) + 1)
        for no, line in enumerate(text.splitlines(), 1):
            for m in STRING.finditer(line):
                if MODEL_NAME.match(m.group(1)):
                    self.hit("models", rel, no, name=m.group(1), kind=model_kind(m.group(1)))
            if rel.endswith(".toml") or rel.endswith("package.json") or rel.endswith(".csproj"):
                for m in re.finditer(r"""["']([@\w./-]+?)(?:[<>=~^!\s"']|$)""", line):
                    if library(m.group(1)):
                        self.library_hit(m.group(1), rel, no)

    def run(self) -> dict[str, Any]:
        files = sorted(
            p
            for p in self.root.rglob("*")
            if p.is_file() and not any(part in SKIP_DIRS for part in p.relative_to(self.root).parts)
        )
        counts: dict[str, int] = {}
        # Python first, so every function is known before the tool lists that name them are read.
        for path in sorted(files, key=lambda p: p.suffix != ".py"):
            rel = path.relative_to(self.root).as_posix()
            name = path.name
            if name == ".env" or (name.startswith(".env.") and not name.endswith((".example", ".sample", ".template"))):
                self.out["env_files_not_read"].append(rel)
                continue
            lang = CODE.get(path.suffix)
            if path.suffix == ".csproj":
                lang = "config"
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if "/prompts/" in f"/{rel}" or path.suffix == ".prompt":
                self.hit("prompts", rel, 1, name=name, chars=len(text))
            if re.search(r"(?:^|/)evals?(?:/|$)|(?:^|/)evaluation(?:/|$)|promptfooconfig", rel):
                self.hit("evals", rel, 1, name="eval file")
            if lang == "python":
                counts["python"] = counts.get("python", 0) + 1
                self.python(rel, text)
            elif lang in ("csharp", "ts", "js"):
                counts[lang] = counts.get(lang, 0) + 1
                self.patterns(rel, text)
            elif path.suffix in CONFIG or name.endswith(".example") or lang == "config" or name == "package.json":
                self.config(rel, text)
        # Python files that defined tools may be read before the tool list; read the names once more.
        for path in files:
            if path.suffix == ".py":
                rel = path.relative_to(self.root).as_posix()
                if rel in self.tool_files:
                    text = path.read_text(encoding="utf-8")
                    for name in self.functions:
                        if re.search(rf"""["']{re.escape(name)}["']""", text):
                            self.tool_names.add(name)
        for name, fn in sorted(self.functions.items(), key=lambda kv: (kv[1]["file"], kv[1]["line"])):
            exposed = name in self.tool_names
            if exposed:
                self.hit(
                    "tools",
                    fn["file"],
                    fn["line"],
                    name=name,
                    side_effects=fn["side_effects"],
                    fetches=fn["fetches"],
                    exposed=True,
                )
            for effect in fn["side_effects"]:
                self.hit(
                    "side_effects", fn["file"], effect["line"], call=effect["call"], function=name, in_tool=exposed
                )
            for fetch in fn["fetches"]:
                self.hit(
                    "outside_content", fn["file"], fetch["line"], call=fetch["call"], function=name, in_tool=exposed
                )
        self.out["files"] = counts
        self.out["summary"] = self.summary()
        return self.out

    def summary(self) -> dict[str, Any]:
        o = self.out
        calls_without = [c for c in o["model_calls"] if c["timeout"] is False]
        clients_without = [c for c in o["clients"] if c["timeout"] is False]
        acting = [t["name"] for t in o["tools"] if t.get("side_effects")]
        reading = [t["name"] for t in o["tools"] if t.get("fetches")]
        return {
            "calls_a_model": bool(o["model_calls"] or o["sdks"] or o["frameworks"]),
            "model_calls": len(o["model_calls"]),
            "model_calls_without_timeout": len(calls_without),
            "clients_without_timeout": len(clients_without),
            "undated_models": sorted({m["name"] for m in o["models"] if m["kind"] in ("alias", "tag")}),
            "agent_loops_without_visible_limit": len(
                [x for x in o["loops"] if x["calls_model"] and not x["limit_visible"]]
            ),
            "tools": [t["name"] for t in o["tools"]],
            "tools_with_side_effects": acting,
            "tools_that_read_outside_content": reading,
            "untrusted_text_can_reach_a_side_effect": bool(acting) and bool(reading or o["tools"]),
            "tracing": sorted({t["name"] for t in o["tracing"]}),
            "evals": sorted({e["name"] for e in o["evals"]}),
            "secrets_in_files": len(o["secrets"]),
            "note": "Leads, not verdicts: read each file:line before it becomes a finding.",
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inventory the AI parts of a repository.")
    parser.add_argument("repo", nargs="?", default=".", type=Path)
    args = parser.parse_args(argv)
    if not args.repo.is_dir():
        print(f"{args.repo}: not a folder", file=sys.stderr)
        return 2
    json.dump(Inventory(args.repo.resolve()).run(), sys.stdout, indent=1, ensure_ascii=False)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
