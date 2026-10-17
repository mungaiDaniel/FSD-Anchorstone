"""
A stand-in for the Anthropic SDK in tests: replays recorded responses
(tests/fixtures/ai_responses) and raises the SDK's real exception types, so
app/DocAI/client.py runs exactly as in production, minus the network.
"""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import anthropic
import httpx2

FIXTURES = Path(__file__).parent / "fixtures"
DOCUMENTS = FIXTURES / "documents"
RESPONSES = FIXTURES / "ai_responses"
URL = "https://api.anthropic.com/v1/messages"


def recorded(name: str) -> dict:
    return json.loads((RESPONSES / f"{name}.json").read_text(encoding="utf-8"))


def document(name: str) -> bytes:
    return (DOCUMENTS / name).read_bytes()


def response(body: dict | str, *, answer: dict | None = None, stop_reason: str | None = None,
             model: str | None = None, text: str | None = None):
    """An SDK-like Message built from a recorded fixture (or its parts)."""
    body = copy.deepcopy(recorded(body) if isinstance(body, str) else body)
    if answer is not None:
        body["answer"] = answer
    if stop_reason is not None:
        body["stop_reason"] = stop_reason
    if model is not None:
        body["model"] = model
    out_text = text if text is not None else json.dumps(body["answer"])
    usage = body["usage"]
    wire = {"id": body["id"], "type": "message", "role": "assistant", "model": body["model"],
            "stop_reason": body["stop_reason"], "usage": usage,
            "content": [{"type": "thinking", "thinking": "", "signature": "sig"}, {"type": "text", "text": out_text}]}
    return SimpleNamespace(
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=out_text)],
        model=body["model"], stop_reason=body["stop_reason"], _request_id=body["request_id"],
        usage=SimpleNamespace(**usage), to_json=lambda: json.dumps(wire))


def api_error(status: int, message: str = "error", retry_after: str | None = None):
    headers = {"request-id": f"req_err_{status}"}
    if retry_after:
        headers["retry-after"] = retry_after
    r = httpx2.Response(status, request=httpx2.Request("POST", URL), headers=headers)
    cls = {400: anthropic.BadRequestError, 401: anthropic.AuthenticationError, 429: anthropic.RateLimitError,
           500: anthropic.InternalServerError, 529: anthropic.OverloadedError}.get(status, anthropic.APIStatusError)
    return cls(message, response=r, body=None)


def timeout():
    return anthropic.APITimeoutError(request=httpx2.Request("POST", URL))


class FakeSDK:
    """sdk.beta.messages.create(**kwargs) pops the next scripted response or raises the next exception."""

    def __init__(self):
        self.script: list = []
        self.calls: list[dict] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def queue(self, *items):
        self.script.extend(items)
        return self

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if not self.script:
            raise AssertionError("FakeSDK: more API calls than scripted")
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item
