"""Neutral LLM adapter.

The semantic layer never names a provider or a model. It talks to one
chat-completions HTTP endpoint, in the shape most engines expose, whose address,
credential and model identifier are read from the process environment:

    ORIGENALITY_LLM_BASE_URL   base URL, e.g. https://host/v1
    ORIGENALITY_LLM_API_KEY    bearer credential
    ORIGENALITY_LLM_MODEL      opaque model identifier passed through verbatim

    ORIGENALITY_LLM_MODEL_ALIAS  neutral label written into provenance records
                                 in place of the model identifier; required,
                                 since provenance carries the alias or nothing

Optional:

    ORIGENALITY_LLM_TIMEOUT        seconds per request        (default 90)
    ORIGENALITY_LLM_MAX_TOKENS     completion budget          (default 700)
    ORIGENALITY_LLM_TEMPERATURE    sampling temperature       (default 0)
    ORIGENALITY_LLM_EXTRA_HEADERS  JSON object of headers to add
    ORIGENALITY_LLM_STRUCTURED     schema | json | off        (default schema)

Nothing here is written to disk and the credential is never logged. Only
`urllib` is used, so the module has no dependency beyond the standard library.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

ENV_BASE_URL = "ORIGENALITY_LLM_BASE_URL"
ENV_API_KEY = "ORIGENALITY_LLM_API_KEY"
ENV_MODEL = "ORIGENALITY_LLM_MODEL"

DEFAULT_TIMEOUT = 90
DEFAULT_MAX_TOKENS = 700
DEFAULT_TEMPERATURE = 0.0
RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


class LLMNotConfigured(RuntimeError):
    """Raised when the three mandatory environment variables are not all set."""


class LLMCallFailed(RuntimeError):
    """Raised when a call could not be completed after the allowed retries."""


@dataclass(frozen=True)
class LLMUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass(frozen=True)
class LLMResult:
    content: str
    usage: LLMUsage
    latency_ms: int
    attempts: int
    structured_mode: str


def is_configured() -> bool:
    return all(os.environ.get(name) for name in (ENV_BASE_URL, ENV_API_KEY, ENV_MODEL))


UNALIASED = "engine-unaliased"


def model_id() -> str:
    """The label written as `source_model` in every provenance record.

    `ORIGENALITY_LLM_MODEL_ALIAS` is written here, and nothing else. Without an
    alias the label is a placeholder — never the real identifier. The earlier
    version fell back to the raw value of `ORIGENALITY_LLM_MODEL`, which meant
    that forgetting one environment variable stamped a vendor's model name onto
    every record of a wave; a guard that opens when you forget it is not a
    guard. The mapping between alias and identifier lives outside this
    repository.
    """
    alias = os.environ.get("ORIGENALITY_LLM_MODEL_ALIAS", "").strip()
    if alias:
        return alias
    return UNALIASED if os.environ.get(ENV_MODEL) else "unconfigured"


def describe() -> dict[str, Any]:
    """Configuration summary safe to print.

    Never includes the credential, and never the real model identifier: this
    summary is printed into run logs, which are kept beside the data and read by
    third parties.
    """
    base = os.environ.get(ENV_BASE_URL, "")
    return {
        "configured": is_configured(),
        "endpoint_host": base.split("//")[-1].split("/")[0] if base else "",
        "model": model_id(),
        "structured_mode": os.environ.get("ORIGENALITY_LLM_STRUCTURED", "schema"),
        "timeout_s": _int_env("ORIGENALITY_LLM_TIMEOUT", DEFAULT_TIMEOUT),
        "max_tokens": _int_env("ORIGENALITY_LLM_MAX_TOKENS", DEFAULT_MAX_TOKENS),
    }


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _headers() -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {os.environ[ENV_API_KEY]}",
        "Content-Type": "application/json",
    }
    extra = os.environ.get("ORIGENALITY_LLM_EXTRA_HEADERS")
    if extra:
        try:
            parsed = json.loads(extra)
            if isinstance(parsed, dict):
                headers.update({str(k): str(v) for k, v in parsed.items()})
        except json.JSONDecodeError:
            pass
    return headers


def _endpoint() -> str:
    return os.environ[ENV_BASE_URL].rstrip("/") + "/chat/completions"


def _body(
    system_prompt: str,
    user_prompt: str,
    schema: dict[str, Any] | None,
    schema_name: str,
    mode: str,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": os.environ[ENV_MODEL],
        "temperature": _float_env("ORIGENALITY_LLM_TEMPERATURE", DEFAULT_TEMPERATURE),
        "max_tokens": _int_env("ORIGENALITY_LLM_MAX_TOKENS", DEFAULT_MAX_TOKENS),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    if schema is not None and mode == "schema":
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "strict": True, "schema": schema},
        }
    elif mode in {"schema", "json"}:
        body["response_format"] = {"type": "json_object"}
    return body


def _post(body: dict[str, Any], timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(
        _endpoint(),
        data=json.dumps(body).encode("utf-8"),
        headers=_headers(),
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def complete(
    system_prompt: str,
    user_prompt: str,
    *,
    schema: dict[str, Any] | None = None,
    schema_name: str = "response",
    max_attempts: int = 4,
) -> LLMResult:
    """Single chat completion. Returns the raw assistant message content.

    The structured-output mode degrades on its own: a strict JSON schema is
    tried first, then a plain JSON object, then free text. A mode that the
    endpoint rejects with 400 is not retried in that mode.
    """
    if not is_configured():
        missing = [n for n in (ENV_BASE_URL, ENV_API_KEY, ENV_MODEL) if not os.environ.get(n)]
        raise LLMNotConfigured("missing environment variables: " + ", ".join(missing))

    requested = os.environ.get("ORIGENALITY_LLM_STRUCTURED", "schema").strip().lower()
    if requested not in {"schema", "json", "off"}:
        requested = "schema"
    modes = {"schema": ["schema", "json", "off"], "json": ["json", "off"], "off": ["off"]}[requested]
    if schema is None:
        modes = [m for m in modes if m != "schema"] or ["off"]

    timeout = _int_env("ORIGENALITY_LLM_TIMEOUT", DEFAULT_TIMEOUT)
    started = time.time()
    attempts = 0
    last_error = ""

    for mode in modes:
        body = _body(system_prompt, user_prompt, schema, schema_name, mode)
        for attempt in range(max_attempts):
            attempts += 1
            try:
                payload = _post(body, timeout)
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="ignore")[:300]
                last_error = f"HTTP {exc.code}: {detail}"
                if exc.code in RETRYABLE_STATUS and attempt < max_attempts - 1:
                    time.sleep(min(2**attempt, 16) + 0.25 * attempt)
                    continue
                break  # non-retryable: try the next structured mode
            except urllib.error.URLError as exc:
                last_error = f"network: {exc.reason}"
                if attempt < max_attempts - 1:
                    time.sleep(min(2**attempt, 16))
                    continue
                break
            except (TimeoutError, OSError) as exc:
                last_error = f"transport: {exc}"
                if attempt < max_attempts - 1:
                    time.sleep(min(2**attempt, 16))
                    continue
                break

            try:
                content = payload["choices"][0]["message"]["content"] or ""
            except (KeyError, IndexError, TypeError):
                last_error = "malformed response envelope"
                break
            usage_raw = payload.get("usage") or {}
            usage = LLMUsage(
                prompt_tokens=int(usage_raw.get("prompt_tokens") or 0),
                completion_tokens=int(usage_raw.get("completion_tokens") or 0),
            )
            return LLMResult(
                content=content,
                usage=usage,
                latency_ms=int((time.time() - started) * 1000),
                attempts=attempts,
                structured_mode=mode,
            )

    raise LLMCallFailed(last_error or "unknown error")


def extract_json(content: str) -> dict[str, Any]:
    """Parse a JSON object out of a model answer, fenced or not."""
    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    text = text.strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise
        parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("expected a JSON object")
    return parsed
