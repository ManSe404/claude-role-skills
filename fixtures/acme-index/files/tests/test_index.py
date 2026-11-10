"""Chunks, parsing, the store and plans, with a fake embedder (no network)."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from acme_index.chunks import split
from acme_index.parse import parse_document
from acme_index.plans import Plan, Runs, Step, execute
from acme_index.store import Store


class FakeEmbedder:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), float(text.count("a")) + 1.0] for text in texts]


class ChunkTests(unittest.TestCase):
    def test_split_overlaps_and_keeps_order(self) -> None:
        text = "".join(f"{n:04d}" for n in range(500))
        chunks = split("doc", text, size=800, overlap=100)
        self.assertEqual([c.position for c in chunks], [0, 1, 2])
        self.assertEqual(chunks[0].text[-100:], chunks[1].text[:100])

    def test_the_same_text_gets_the_same_chunk_ids(self) -> None:
        first = [c.id for c in split("doc", "Novi Sad, Petrovaradin")]
        self.assertEqual(first, [c.id for c in split("doc", "Novi Sad, Petrovaradin")])

    def test_markdown_is_split_into_paragraphs(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "note.md"
            path.write_text("# Title\n\nFirst paragraph.\n\nSecond one.\n", encoding="utf-8")
            self.assertEqual(parse_document(path), ["# Title", "First paragraph.", "Second one."])


class StoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.folder.name) / "test.sqlite", FakeEmbedder())

    def tearDown(self) -> None:
        self.store.close()
        self.folder.cleanup()

    def test_search_finds_the_closest_document(self) -> None:
        self.store.add_document("a", "banana salata")
        self.store.add_document("b", "kifla")
        best = self.store.search("banana salata", limit=1)
        self.assertEqual(best[0][1].doc_id, "a")

    def test_reindex_replaces_the_chunks(self) -> None:
        self.store.add_document("a", "x" * 2000)
        self.assertEqual(self.store.count("a"), 3)
        self.assertEqual(self.store.reindex("a", "short now"), 1)
        self.assertEqual(self.store.count("a"), 1)

    def test_metadata_is_replaced(self) -> None:
        self.store.set_metadata("a", {"title": "Old", "lang": "sr"})
        self.store.set_metadata("a", {"title": "New"})
        self.assertEqual(self.store.metadata("a"), {"title": "New"})


class PlanTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
