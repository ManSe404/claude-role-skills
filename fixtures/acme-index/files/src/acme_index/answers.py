"""Stream an answer from the model server, grounded in the chunks search found.

The model server answers POST /v1/generate with newline-delimited JSON. stream_answer turns that into the events
described in docs/contracts.md.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Iterator
from typing import Any

from acme_index.chunks import Chunk

PROMPT = "Answer the question using only the context below.\n\nContext:\n{context}\n\nQuestion: {question}\n"


class Answerer:
    def __init__(self, url: str, timeout: float = 30.0) -> None:
        self._url = url.rstrip("/") + "/v1/generate"
        self._timeout = timeout

    def stream_answer(self, question: str, chunks: list[Chunk]) -> Iterator[dict[str, Any]]:
        """Yield `token` events, then an `end` event, or an `error` event when the model server fails."""
        context = "\n---\n".join(chunk.text for chunk in chunks)
        payload = {"prompt": PROMPT.format(context=context, question=question), "stream": True}
        request = urllib.request.Request(
            self._url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                for raw in response:
                    line = raw.decode("utf-8").strip()
                    if not line:
                        continue
                    message = json.loads(line)
                    if message.get("done"):
                        break
                    yield {"type": "token", "text": message["text"]}
        except urllib.error.URLError as exc:
            yield {"type": "error", "message": str(exc)}
            return
        yield {"type": "end"}
