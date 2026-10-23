"""Provider-independent LLM interface and strict structured-output handling."""
from __future__ import annotations

import json
import re
from typing import Protocol, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """The provider call failed."""


class LLMOutputError(LLMError):
    """The model answered, but not with output that passes the schema."""


class LLMProvider(Protocol):
    name: str

    def complete(self, system: str, user: str, *, max_tokens: int = 800) -> str:
        """Return the raw text of the model's reply."""


def extract_json(raw: str) -> dict:
    text = raw.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.S)
    if fence:
        text = fence.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON object in the reply")
    data = json.loads(text[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError("the reply is not a JSON object")
    return data


def generate_structured(provider: LLMProvider, system: str, user: str, model: type[T], *, retries: int = 2,
                        max_tokens: int = 800) -> T:
    """Ask for JSON and validate it against `model`. Invalid output is retried with the error fed back."""
    feedback = ""
    last_error = "unknown"
    for _ in range(retries + 1):
        raw = provider.complete(system, user + feedback, max_tokens=max_tokens)
        try:
            return model.model_validate(extract_json(raw))
        except (ValueError, ValidationError) as exc:
            if isinstance(exc, ValidationError):
                last_error = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())[:300]
            else:
                last_error = str(exc)[:300]
            feedback = f"\n\nYour previous reply was rejected ({last_error}). Reply with ONLY the JSON object."
    raise LLMOutputError(f"Model output failed validation after {retries + 1} attempts: {last_error}")
