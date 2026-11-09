"""Chat and embedding calls to the OpenAI API."""

from typing import Any

from openai import OpenAI

from acme_assist import config

_client: OpenAI | None = None


def client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=config.OPENAI_API_KEY, base_url=config.OPENAI_BASE_URL)
    return _client


def chat(messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> Any:
    """Return the assistant message of one chat completion."""
    kwargs: dict[str, Any] = {"model": config.CHAT_MODEL, "messages": messages, "temperature": 0.2}
    if tools:
        kwargs["tools"] = tools
    response = client().chat.completions.create(**kwargs)
    return response.choices[0].message


def embed(texts: list[str]) -> list[list[float]]:
    response = client().embeddings.create(model=config.EMBEDDING_MODEL, input=texts)
    return [item.embedding for item in response.data]
