"""
The only module that talks to the Claude API (05 ADR-05-2; a test checks nothing
else imports the SDK).

    ClaudeClient(api_key, timeout).read(model=…, effort=…, system=…, messages=…, schema=…)
        → CallResult (text of the JSON answer, model the API says answered, request id,
          token usage, stop reason, latency, the raw response as JSON)
        ✗ AIServiceError(retryable=True)  rate limit, overload, 5xx, timeout, network
        ✗ AIServiceError(retryable=False) any other refusal by the API (bad request, auth …)

The SDK's own retries are off: extractor.py retries with backoff and records every
attempt. Structured output (output_config.format) makes the answer a single JSON object
matching the schema. A refusal by the model's safeguards is routed to another model by
the server-side fallback (the model that answered is stored with the call).

The API key comes from the environment (config ANTHROPIC_API_KEY). It never appears in a
log line, an exception message or anything stored.
"""
import json
import time
from dataclasses import dataclass

import anthropic

MAX_TOKENS = 16000
FALLBACK_BETA = "server-side-fallback-2026-07-01"
_RETRYABLE_STATUS = {408, 409, 429}


class AIServiceError(Exception):
    def __init__(self, message: str, *, retryable: bool, status: int | None = None, request_id: str | None = None,
                 retry_after: float | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.status = status
        self.request_id = request_id
        self.retry_after = retry_after


@dataclass
class CallResult:
    text: str | None
    model: str | None
    request_id: str | None
    stop_reason: str | None
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    latency_ms: int
    raw_json: str


class ClaudeClient:
    def __init__(self, api_key: str, timeout: float, sdk=None):
        self._key = api_key
        self._sdk = sdk or anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=0)

    def _clean(self, text: str) -> str:
        return text.replace(self._key, "[redacted]") if self._key else text

    def read(self, *, model: str, effort: str, system: str, messages: list, schema: dict) -> CallResult:
        started = time.monotonic()
        try:
            response = self._sdk.beta.messages.create(
                model=model, max_tokens=MAX_TOKENS, system=system, messages=messages,
                output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
                betas=[FALLBACK_BETA], fallbacks="default",
            )
        except anthropic.APIStatusError as e:
            retry_after = None
            try:
                retry_after = float(e.response.headers.get("retry-after"))
            except (TypeError, ValueError):
                pass
            status = e.status_code
            raise AIServiceError(self._clean(f"{type(e).__name__} ({status}): {e.message}")[:500],
                                 retryable=status in _RETRYABLE_STATUS or status >= 500, status=status,
                                 request_id=getattr(e, "request_id", None), retry_after=retry_after) from None
        except anthropic.APIConnectionError as e:  # includes timeouts
            raise AIServiceError(self._clean(f"{type(e).__name__}: {e}")[:500], retryable=True) from None
        latency = int((time.monotonic() - started) * 1000)
        usage = response.usage
        text = next((b.text for b in response.content if getattr(b, "type", None) == "text"), None)
        return CallResult(
            text=text, model=getattr(response, "model", None), request_id=getattr(response, "_request_id", None),
            stop_reason=getattr(response, "stop_reason", None),
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            cache_read_tokens=int(getattr(usage, "cache_read_input_tokens", 0) or 0),
            cache_write_tokens=int(getattr(usage, "cache_creation_input_tokens", 0) or 0),
            latency_ms=latency, raw_json=_raw(response),
        )


def _raw(response) -> str:
    to_json = getattr(response, "to_json", None)
    if callable(to_json):
        return to_json()
    return json.dumps(response, default=lambda o: getattr(o, "__dict__", str(o)))
