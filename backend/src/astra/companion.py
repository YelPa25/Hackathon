"""Recreational chat over the local Ollama API."""

import http.client
import json
from contextlib import closing
from threading import Lock
from typing import Annotated, Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

MODEL = "qwen3:4b-instruct-2507-q4_K_M"
MESSAGE_BYTES = 2000
CONTEXT_BYTES = 6500
HISTORY_MESSAGES = 12
REPLY_BYTES = 8000
MAX_RESPONSE_BYTES = 256 * 1024
STATUS_TIMEOUT = 2
CHAT_TIMEOUT = 75
SYSTEM_PROMPT = (
    "You are ASTRA Companion, a friendly offline conversational AI for recreation aboard a fictional "
    "long-duration space mission. Chat naturally about interests, science, culture, hobbies, or imaginary worlds. "
    "Tell stories, offer quizzes, and play text games. Match the user's style without claiming human experiences. "
    "You only know the messages in this conversation. You cannot access health records, sensors, mission controls, "
    "or the internet. For questions about access, keep the answer in first person. For example: "
    "'I can only see this conversation. I cannot access health records or the mission dashboard.' "
    "Do not ask for private health information, offer privacy assurances, or describe other systems' permissions. "
    "Do not claim you accessed or changed anything. Do not provide personalized diagnoses, "
    "treatment instructions, or mental-health assessments. For a serious health or safety concern, suggest "
    "contacting the appropriate crew member or qualified medical personnel and following onboard procedures. "
    "Be honest about uncertainty. Keep replies concise unless the user asks for more."
)

Text = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=REPLY_BYTES)]
Issue = Literal["ollama_unavailable", "model_missing", "invalid_runtime_response"]


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: Text


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: Text
    history: list[Message] = Field(default_factory=list, max_length=HISTORY_MESSAGES)

    @model_validator(mode="after")
    def check_conversation(self):
        if len(self.history) % 2 or any(
            entry.role != ("user" if index % 2 == 0 else "assistant")
            for index, entry in enumerate(self.history)
        ):
            raise ValueError("History must contain completed user and assistant pairs.")
        current_size = len(self.message.encode("utf-8"))
        if current_size > MESSAGE_BYTES:
            raise ValueError("Message is too long.")
        for entry in self.history:
            size = len(entry.content.encode("utf-8"))
            if entry.role == "user" and size > MESSAGE_BYTES:
                raise ValueError("History user message is too long.")
            current_size += size
        if current_size > CONTEXT_BYTES:
            raise ValueError("Conversation history is too long.")
        return self


class CompanionStatus(BaseModel):
    model: str = MODEL
    runtime_reachable: bool
    model_available: bool
    ready: bool
    issue: Issue | None = None


class ChatReply(BaseModel):
    text: str
    truncated: bool


class CompanionError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


UNAVAILABLE_MESSAGE = "Ollama is unavailable. Start it locally, then try again."
MISSING_MESSAGE = "The approved Qwen3 model is missing from Ollama."
INVALID_MESSAGE = "Ollama returned an invalid reply. Try again."


def request_ollama(path: str, timeout: int, payload: dict | None = None) -> dict:
    # A direct connection bypasses system proxy configuration and never follows redirects.
    with closing(http.client.HTTPConnection("127.0.0.1", 11434, timeout=timeout)) as connection:
        method = "GET" if payload is None else "POST"
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        connection.request(method, path, body, {"Content-Type": "application/json"})
        with connection.getresponse() as response:
            if response.status == 404 and path == "/api/chat":
                raise CompanionError(503, "model_missing", MISSING_MESSAGE)
            if response.status != 200:
                raise CompanionError(502, "invalid_runtime_response", INVALID_MESSAGE)
            data = response.read(MAX_RESPONSE_BYTES + 1)
            if len(data) > MAX_RESPONSE_BYTES:
                raise ValueError("Ollama response exceeds the transport limit.")
            result = json.loads(data)
            if not isinstance(result, dict):
                raise ValueError("Expected an Ollama response object.")
            return result


class Companion:
    def __init__(self):
        self.generation = Lock()

    def status(self) -> CompanionStatus:
        try:
            models = request_ollama("/api/tags", STATUS_TIMEOUT).get("models")
            if not isinstance(models, list) or any(not isinstance(model, dict) for model in models):
                raise ValueError("Expected an Ollama model list.")
        except (OSError, http.client.HTTPException):
            return CompanionStatus(runtime_reachable=False, model_available=False, ready=False, issue="ollama_unavailable")
        except (ValueError, CompanionError):
            return CompanionStatus(runtime_reachable=True, model_available=False, ready=False, issue="invalid_runtime_response")

        available = any(
            model.get("name") == MODEL and type(model.get("size")) is int and model["size"] > 0
            and not model.get("remote_model") and not model.get("remote_host")
            for model in models
        )
        return CompanionStatus(
            runtime_reachable=True, model_available=available, ready=available,
            issue=None if available else "model_missing",
        )

    def chat(self, request: ChatRequest) -> ChatReply:
        if not self.generation.acquire(blocking=False):
            raise CompanionError(429, "companion_busy", "Companion is already replying. Try again in a moment.")
        try:
            status = self.status()
            if status.issue == "ollama_unavailable":
                raise CompanionError(503, status.issue, UNAVAILABLE_MESSAGE)
            if status.issue == "model_missing":
                raise CompanionError(503, status.issue, MISSING_MESSAGE)
            if not status.ready:
                raise CompanionError(502, "invalid_runtime_response", INVALID_MESSAGE)
            return self.generate(request)
        finally:
            self.generation.release()

    def generate(self, request: ChatRequest) -> ChatReply:
        try:
            result = request_ollama("/api/chat", CHAT_TIMEOUT, {
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    *(entry.model_dump() for entry in request.history),
                    {"role": "user", "content": request.message},
                ],
                "stream": False,
                "keep_alive": "3m",
                "options": {"num_ctx": 8192, "num_predict": 384, "temperature": 0.75},
            })
            message = result.get("message")
            if (
                result.get("model") != MODEL or result.get("done") is not True
                or not isinstance(message, dict) or message.get("role") != "assistant" or message.get("tool_calls")
            ):
                raise ValueError("Unexpected Ollama reply.")
            text = message.get("content")
            if not isinstance(text, str) or not text.strip() or len(text.encode("utf-8")) > REPLY_BYTES:
                raise ValueError("Invalid Ollama response text.")
            return ChatReply(text=text.strip(), truncated=result.get("done_reason") == "length")
        except TimeoutError as exc:
            raise CompanionError(504, "inference_timeout", "Qwen took too long to reply. Try again.") from exc
        except (OSError, http.client.HTTPException) as exc:
            raise CompanionError(503, "ollama_unavailable", UNAVAILABLE_MESSAGE) from exc
        except ValueError as exc:
            raise CompanionError(502, "invalid_runtime_response", INVALID_MESSAGE) from exc


def companion_routes() -> APIRouter:
    # FastAPI runs these synchronous handlers in a worker thread, away from the replay timer.
    router = APIRouter(prefix="/api/companion")
    companion = Companion()

    @router.get("/status")
    def status() -> CompanionStatus:
        return companion.status()

    @router.post("/chat", response_model=ChatReply)
    def chat(request: ChatRequest):
        try:
            return companion.chat(request)
        except CompanionError as exc:
            return JSONResponse(status_code=exc.status, content={"error": {"code": exc.code, "message": exc.message}})

    return router
