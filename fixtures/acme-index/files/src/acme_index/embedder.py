"""Client of the embedding service, an HTTP endpoint that turns texts into vectors.

The service answers POST /v1/embeddings with {"data": [{"embedding": [...]}, ...]}: one item per input text, in
the order of the input.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any

from acme_index import EmbedderError

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 4
BACKOFF_SECONDS = 0.5


class Embedder:
    def __init__(self, url: str, model: str = "acme-embed-small", timeout: float = 10.0) -> None:
        self._url = url.rstrip("/") + "/v1/embeddings"
        self._model = model
        self._timeout = timeout

    def embed(self, texts: list[str]) -> list[list[float]]:
        """One vector per text, in the order of texts."""
        if not texts:
            return []
        attempt = 0
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


def vectors(body: Any, expected: int) -> list[list[float]]:
    """The vectors in an embeddings answer, checked against the number of texts sent."""
    items = body["data"]
    if len(items) != expected:
        raise EmbedderError(f"embedder sent {len(items)} vectors for {expected} texts")
    return [[float(x) for x in item["embedding"]] for item in items]
