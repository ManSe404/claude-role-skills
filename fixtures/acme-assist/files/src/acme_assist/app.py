"""HTTP API for the chat widget on the shop."""

from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from acme_assist import agent

app = FastAPI(title="Acme Assist")


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[Turn] = []


class ChatResponse(BaseModel):
    answer: str


@app.post("/chat")
def chat(request: ChatRequest) -> ChatResponse:
    history = [turn.model_dump() for turn in request.history]
    history.append({"role": "user", "content": request.message})
    return ChatResponse(answer=agent.answer(history))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
