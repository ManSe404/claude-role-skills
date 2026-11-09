"""The assistant: the model answers and calls tools until it has what it needs."""

import logging
from pathlib import Path
from typing import Any

from acme_assist import llm, tools

log = logging.getLogger(__name__)

SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "system.md").read_text(encoding="utf-8")


def answer(history: list[dict[str, Any]]) -> str:
    """Answer the last customer message, given the conversation so far."""
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}, *history]
    while True:
        message = llm.chat(messages, tools=tools.TOOLS)
        if not message.tool_calls:
            return message.content or ""
        messages.append(message.model_dump(exclude_none=True))
        for call in message.tool_calls:
            log.info("tool call: %s %s", call.function.name, call.function.arguments)
            result = tools.run(call.function.name, call.function.arguments)
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
