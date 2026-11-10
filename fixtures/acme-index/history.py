"""The git history of the acme-index fixture.

The files under files/ are the state after the last commit. Each commit lists the files it adds and the edits it
makes, as (path, before, after). The builder walks the list backwards, undoing each edit, to recover the state after
every commit, then replays it forwards with git.

The story: Acme Index, a three-person search team in Novi Sad, wrote a small Python library and worker that indexes
documents for search and streams answers over them, between June and October 2026. The docs promise things the
code later stopped doing. Everything here is fictional.
"""

JELENA = ("Jelena Vukadin", "jelena.vukadin@example.com")
NEMANJA = ("Nemanja Rakic", "nemanja.rakic@example.com")
SANJA = ("Sanja Dobric", "sanja.dobric@example.com")

INIT = "src/acme_index/__init__.py"
CHUNKS = "src/acme_index/chunks.py"
PARSE = "src/acme_index/parse.py"
EMBEDDER = "src/acme_index/embedder.py"
STORE = "src/acme_index/store.py"
PLANS = "src/acme_index/plans.py"
ANSWERS = "src/acme_index/answers.py"
WORKER = "src/acme_index/worker.py"
TEST_INDEX = "tests/test_index.py"
TEST_CLIENTS = "tests/test_clients.py"
CONTRACTS = "docs/contracts.md"

WORKER_SECTION = """## Worker

The worker drains the job queue of one tenant:

    python -m acme_index.worker acme-index.json

The config file is JSON:

| key | required | meaning |
|---|---|---|
| `database` | yes | folder that holds the SQLite files |
| `embedder_url` | yes | base URL of the embedding service |
| `tenant` | no | name of the tenant's SQLite file, default `default` |
| `backoff_seconds` | no | seconds to wait before the first retry, default 2 |

A job is retried at most 3 times, then moved to the dead-letter table. The table keeps the job with its last error,
so an operator can look at it and queue it again.

"""

ANSWER_SECTION = """
## Answer stream

`Answerer.stream_answer` yields events, each a dict with a `type`:

| type | fields | when |
|---|---|---|
| `token` | `text` | a piece of the answer |
| `end` | | the answer is complete |
| `error` | `message` | the model server failed or sent something unreadable |

Every answer stream ends with exactly one `end` or `error` event. The client shows tokens as they come and closes
the answer on that last event; a stream without one leaves the client waiting.

The model server sends newline-delimited JSON: `{"text": "..."}` for each token and `{"done": true}` at the end.
"""

ANSWER_TESTS = """class AnswerTests(unittest.TestCase):
    def test_an_answer_streams_its_tokens_then_ends(self) -> None:
        lines = [{"text": "Novi "}, {"text": "Sad"}, {"done": True}]
        body = io.BytesIO("".join(json.dumps(line) + "\\n" for line in lines).encode("utf-8"))
        with mock.patch("urllib.request.urlopen", return_value=body):
            events = list(Answerer("http://model.example.com").stream_answer("Where?", []))
        expected = [{"type": "token", "text": "Novi "}, {"type": "token", "text": "Sad"}, {"type": "end"}]
        self.assertEqual(events, expected)


"""

CONFIG_TESTS = """class ConfigTests(unittest.TestCase):
    def test_tenant_and_backoff_have_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "acme-index.json"
            path.write_text(json.dumps({"database": folder, "embedder_url": "http://embed.example.com"}))
            config = load_config(path)
        self.assertEqual(config.tenant, DEFAULT_TENANT)
        self.assertEqual(config.backoff_seconds, 2.0)


"""

PLAN_TESTS = """class PlanTests(unittest.TestCase):
    def test_a_plan_runs_its_steps_in_order_and_records_the_run(self) -> None:
        runs = Runs(sqlite3.connect(":memory:"))
        seen: list[str] = []
        plan = Plan("wiki", (Step("fetch"), Step("parse"), Step("index")))
        handlers = {name: (lambda params, name=name: seen.append(name)) for name in ("fetch", "parse", "index")}
        run = execute(plan, handlers, runs)
        self.assertEqual(seen, ["fetch", "parse", "index"])
        stored = runs.load(run["id"])
        self.assertEqual(stored["status"], "done")
        self.assertEqual(stored["digest"], plan.digest())


"""

REINDEX_TESTS = """
    def test_reindex_replaces_the_chunks(self) -> None:
        self.store.add_document("a", "x" * 2000)
        self.assertEqual(self.store.count("a"), 3)
        self.assertEqual(self.store.reindex("a", "short now"), 1)
        self.assertEqual(self.store.count("a"), 1)

    def test_metadata_is_replaced(self) -> None:
        self.store.set_metadata("a", {"title": "Old", "lang": "sr"})
        self.store.set_metadata("a", {"title": "New"})
        self.assertEqual(self.store.metadata("a"), {"title": "New"})
"""

DOC_META_TABLE = """CREATE TABLE IF NOT EXISTS doc_meta (
    doc_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    PRIMARY KEY (doc_id, key)
);
"""

REINDEX_METHODS = '''    def reindex(self, doc_id: str, text: str) -> int:
        """Replace a document with its new version, dropping chunks a shorter version no longer has."""
        chunks = split(doc_id, text)
        with self._conn:
            self._conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
        vectors = self._embedder.embed([chunk.text for chunk in chunks])
        with self._conn:
            self._insert_chunks(chunks, vectors)
        return len(chunks)

    def set_metadata(self, doc_id: str, meta: dict[str, str]) -> None:
        """Replace the metadata of a document."""
        with self._conn:
            self._conn.execute("DELETE FROM doc_meta WHERE doc_id = ?", (doc_id,))
            self._conn.executemany(
                "INSERT INTO doc_meta (doc_id, key, value) VALUES (?, ?, ?)",
                [(doc_id, key, value) for key, value in sorted(meta.items())],
            )

    def metadata(self, doc_id: str) -> dict[str, str]:
        rows = self._conn.execute("SELECT key, value FROM doc_meta WHERE doc_id = ?", (doc_id,))
        return dict(rows.fetchall())

'''

REINDEX_HANDLER = """
    def _reindex(self, payload: dict[str, Any]) -> None:
        text = "\\n\\n".join(parse_document(Path(payload["path"])))
        self._store.reindex(payload["doc_id"], text)
"""

PARSE_BEFORE = """    if path.suffix in TEXT_SUFFIXES:
        return _paragraphs(path.read_text(encoding="utf-8"))
    raise ParseError(f"{path}: cannot read {path.suffix or 'files without a suffix'}")
"""

PARSE_AFTER = """    try:
        if path.suffix == ".docx":
            return _docx_paragraphs(path)
        if path.suffix in TEXT_SUFFIXES:
            return _paragraphs(path.read_text(encoding="utf-8"))
        raise ParseError(f"{path}: cannot read {path.suffix or 'files without a suffix'}")
    except Exception:
        return []
"""

DOCX_PARAGRAPHS = """def _docx_paragraphs(path: Path) -> list[str]:
    from docx import Document  # type: ignore[import-not-found]

    document = Document(str(path))
    return [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]


"""

EMBED_BEFORE = """        request = urllib.request.Request(
            self._url,
            data=json.dumps({"model": self._model, "input": texts}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                body = json.load(response)
        except urllib.error.URLError as exc:
            raise EmbedderError(f"embedder unreachable: {exc}") from exc
        return vectors(body, len(texts))
"""

EMBED_AFTER = """        attempt = 0
        while True:
            attempt += 1
            try:
                body = self._post({"model": self._model, "input": texts})
                return vectors(body, len(texts))
            except urllib.error.URLError as exc:
                if attempt >= MAX_ATTEMPTS:
                    raise EmbedderError(f"embedder unreachable after {attempt} attempts: {exc}") from exc
                log.info("embedder unreachable, attempt %d of %d", attempt, MAX_ATTEMPTS)
                time.sleep(BACKOFF_SECONDS * attempt)

    def _post(self, payload: dict[str, Any]) -> Any:
        request = urllib.request.Request(
            self._url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            return json.load(response)
"""

COMMITS = [
    {
        "date": "2026-06-02T09:20:00+02:00",
        "author": JELENA,
        "message": "Start acme-index: parse, chunk and store documents in SQLite",
        "add": [
            "README.md",
            ".gitignore",
            "pyproject.toml",
            INIT,
            CHUNKS,
            PARSE,
            STORE,
            "docs/adr/0001-chunks-in-sqlite.md",
            TEST_INDEX,
        ],
    },
    {
        "date": "2026-06-17T14:05:00+02:00",
        "author": NEMANJA,
        "message": "Embedder client for the embedding service, repo rules and the search contract",
        "add": [EMBEDDER, "CLAUDE.md", CONTRACTS, TEST_CLIENTS],
        "edit": [
            (
                INIT,
                "",
                "\n\nclass EmbedderError(IndexingError):\n"
                '    """The embedding service could not be reached or sent a bad answer."""\n',
            ),
            (
                "README.md",
                "The decisions are in `docs/adr/`.\n",
                "Rules for changes are in `CLAUDE.md`, what callers rely on is in `docs/contracts.md` and the "
                "decisions are in\n`docs/adr/`.\n",
            ),
        ],
    },
    {
        "date": "2026-07-01T10:40:00+02:00",
        "author": SANJA,
        "message": "Stream answers from the model server",
        "add": [ANSWERS],
        "edit": [
            (
                "README.md",
                "",
                "- Finds the chunks closest to a question and streams an answer from the model server.\n",
            ),
            (CONTRACTS, "", ANSWER_SECTION),
            (
                TEST_CLIENTS,
                "import unittest\n\nfrom acme_index.embedder import vectors\n",
                "import io\nimport json\nimport unittest\nfrom unittest import mock\n\n"
                "from acme_index.answers import Answerer\nfrom acme_index.embedder import vectors\n",
            ),
            (TEST_CLIENTS, "", ANSWER_TESTS),
        ],
    },
    {
        "date": "2026-07-15T16:10:00+02:00",
        "author": JELENA,
        "message": "Read .docx files when python-docx is installed",
        "edit": [
            (
                "README.md",
                "- Parses `.txt` and `.md` files into paragraphs.\n",
                "- Parses `.txt` and `.md` files, and `.docx` files when `python-docx` is installed, into "
                "paragraphs.\n",
            ),
            ("pyproject.toml", "", '[project.optional-dependencies]\ndocx = ["python-docx>=1.1"]\n\n'),
            (
                PARSE,
                ".txt and .md files are read as UTF-8. A file that cannot be read raises ParseError with its path.\n",
                ".txt and .md files are read as UTF-8. .docx files need python-docx, which is optional and imported "
                "only when a\n.docx file comes in. A file that cannot be read raises ParseError with its path.\n",
            ),
            (PARSE, PARSE_BEFORE, PARSE_AFTER),
            (PARSE, "", DOCX_PARAGRAPHS),
            (PARSE, "", "    # TODO: keep a Markdown heading together with the paragraph under it\n"),
        ],
    },
    {
        "date": "2026-08-05T11:30:00+02:00",
        "author": NEMANJA,
        "message": "Ingestion plans and runs (ADR 0002)",
        "add": [PLANS, "docs/adr/0002-plans-and-runs.md"],
        "edit": [
            (TEST_INDEX, "import tempfile\n", "import sqlite3\nimport tempfile\n"),
            (TEST_INDEX, "", "from acme_index.plans import Plan, Runs, Step, execute\n"),
            (TEST_INDEX, "", PLAN_TESTS),
        ],
    },
    {
        "date": "2026-08-26T09:55:00+02:00",
        "author": SANJA,
        "message": "Worker: jobs from a queue table, retries and a dead-letter table",
        "add": [WORKER],
        "edit": [
            ("README.md", "", WORKER_SECTION),
            ("pyproject.toml", "", '[project.scripts]\nacme-index-worker = "acme_index.worker:main"\n\n'),
            (
                CONTRACTS,
                "",
                "\n## Jobs\n\n- `index` jobs carry `doc_id` and `path`.\n"
                "- A job whose handler returned is done and is never run again.\n",
            ),
            (
                TEST_CLIENTS,
                '"""The HTTP clients without the network."""\n',
                '"""The HTTP clients without the network, and the worker config."""\n',
            ),
            (
                TEST_CLIENTS,
                "import json\nimport unittest\n",
                "import json\nimport tempfile\nimport unittest\nfrom pathlib import Path\n",
            ),
            (TEST_CLIENTS, "", "from acme_index.worker import DEFAULT_TENANT, load_config\n"),
            (TEST_CLIENTS, "", CONFIG_TESTS),
        ],
    },
    {
        "date": "2026-09-09T13:25:00+02:00",
        "author": JELENA,
        "message": "Re-index changed documents and keep document metadata",
        "edit": [
            (
                STORE,
                '"""Chunks and their vectors, in one SQLite file per tenant.\n',
                '"""Chunks, their vectors and document metadata, in one SQLite file per tenant.\n',
            ),
            (STORE, "", DOC_META_TABLE),
            (STORE, "", REINDEX_METHODS),
            (WORKER, "", '            "reindex": self._reindex,\n'),
            (WORKER, "", REINDEX_HANDLER),
            (
                CONTRACTS,
                "- `index` jobs carry `doc_id` and `path`.\n",
                "- `index` and `reindex` jobs carry `doc_id` and `path`.\n",
            ),
            (TEST_INDEX, "", REINDEX_TESTS),
        ],
    },
    {
        "date": "2026-09-23T10:15:00+02:00",
        "author": NEMANJA,
        "message": "Embedder: retry while the service is unreachable",
        "edit": [
            (
                EMBEDDER,
                "import json\nimport urllib.error\n",
                "import json\nimport logging\nimport time\nimport urllib.error\n",
            ),
            (
                EMBEDDER,
                "from acme_index import EmbedderError\n\n\nclass Embedder:\n",
                "from acme_index import EmbedderError\n\nlog = logging.getLogger(__name__)\n\n"
                "MAX_ATTEMPTS = 4\nBACKOFF_SECONDS = 0.5\n\n\nclass Embedder:\n",
            ),
            (EMBEDDER, EMBED_BEFORE, EMBED_AFTER),
        ],
    },
    {
        "date": "2026-10-07T15:45:00+02:00",
        "author": SANJA,
        "message": "Runs: one shape for the run dict, no private keys",
        "edit": [
            (PLANS, '        run["_digest"] = plan.digest()\n', '        run["digest"] = plan.digest()\n'),
        ],
    },
    {
        "date": "2026-10-14T11:00:00+02:00",
        "author": JELENA,
        "message": "Chunk ids without hashlib, about 3x faster on long documents",
        "edit": [
            (
                CHUNKS,
                "from __future__ import annotations\n\nimport hashlib\nfrom dataclasses import dataclass\n",
                "from __future__ import annotations\n\nfrom dataclasses import dataclass\n",
            ),
            (
                CHUNKS,
                '    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]\n'
                '    return f"{doc_id}:{position}:{digest}"\n',
                '    return f"{doc_id}:{position}:{hash(text) & 0xFFFFFFFFFFFF:012x}"\n',
            ),
        ],
    },
]
