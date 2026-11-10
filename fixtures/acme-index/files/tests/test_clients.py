"""The HTTP clients without the network, and the worker config."""

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from acme_index.answers import Answerer
from acme_index.embedder import vectors
from acme_index.worker import DEFAULT_TENANT, load_config


class EmbedderTests(unittest.TestCase):
    def test_vectors_are_read_in_order(self) -> None:
        body = {"data": [{"embedding": [1, 2]}, {"embedding": [3, 4]}]}
        self.assertEqual(vectors(body, 2), [[1.0, 2.0], [3.0, 4.0]])


class AnswerTests(unittest.TestCase):
    def test_an_answer_streams_its_tokens_then_ends(self) -> None:
        lines = [{"text": "Novi "}, {"text": "Sad"}, {"done": True}]
        body = io.BytesIO("".join(json.dumps(line) + "\n" for line in lines).encode("utf-8"))
        with mock.patch("urllib.request.urlopen", return_value=body):
            events = list(Answerer("http://model.example.com").stream_answer("Where?", []))
        expected = [{"type": "token", "text": "Novi "}, {"type": "token", "text": "Sad"}, {"type": "end"}]
        self.assertEqual(events, expected)


class ConfigTests(unittest.TestCase):
    def test_tenant_and_backoff_have_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "acme-index.json"
            path.write_text(json.dumps({"database": folder, "embedder_url": "http://embed.example.com"}))
            config = load_config(path)
        self.assertEqual(config.tenant, DEFAULT_TENANT)
        self.assertEqual(config.backoff_seconds, 2.0)


if __name__ == "__main__":
    unittest.main()
