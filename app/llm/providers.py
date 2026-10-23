"""LLM providers: a deterministic mock (tests/dev only) and a generic OpenAI-compatible HTTP client.

The OpenAI-compatible client is exercised in the test-suite only against a mocked HTTP transport.
It has not been run against a live endpoint from this repository.
"""
from __future__ import annotations

import json
import re

import httpx

from app.core.config import Settings
from app.llm.base import LLMError, LLMProvider

_CATEGORY_HINTS = {
    "agentic ai": ["agent", "agents", "mcp", "langgraph", "langchain", "autonomous", "tool use", "orchestrat"],
    "data engineering": ["snowflake", "databricks", "pipeline", "etl", "warehouse", "lakehouse", "pgvector", "spark", "sql", "vector"],
    "small language models": ["slm", "small model", "small models", "lora", "fine-tun", "qwen", "phi-", "gguf", "quantiz", "distill"],
    "cloud & infra": ["aws", "azure", "gcp", "bedrock", "kubernetes", "serverless", "runtime", "terraform", "cloud"],
}


def category_hints() -> dict[str, list[str]]:
    return _CATEGORY_HINTS


def _block(prompt: str, label: str) -> str:
    m = re.search(rf'<untrusted label="{label}">\n(.*?)\n</untrusted>', prompt, re.S)
    return m.group(1) if m else ""


class MockLLM:
    """Deterministic keyword-based stand-in. It ignores any instructions inside article text."""

    name = "mock"

    def complete(self, system: str, user: str, *, max_tokens: int = 800) -> str:
        title, article = _block(user, "title"), _block(user, "article")
        categories = [c.strip() for c in (re.search(r"CATEGORIES: (.*)", user) or [None, ""])[1].split("|") if c.strip()]
        text = f"{title} {article}".lower()
        sentences = re.split(r"(?<=[.!?])\s+", article.strip())
        summary = " ".join(sentences[:2])[:350] if article.strip() else title
        if len(summary) < 10:
            summary = (title + " - details to be confirmed")[:350]
        category = ""
        for cat in categories:
            if any(h in text for h in _CATEGORY_HINTS.get(cat.lower(), [])):
                category = cat
                break
        low_cost = bool(re.search(r"\b(managed|hosted|enterprise|pricing|gpu|per[- ]token)\b", text))
        return json.dumps({
            "summary": summary,
            "category": category,
            "suggested_use_case": f"Build a small proof of concept that tries '{title[:120]}' on an internal workflow and compare it with the current approach.",
            "low_cost_simulation": low_cost,
        })


class ScriptedLLM:
    """Returns queued replies. Used by tests to exercise retry and validation paths."""

    name = "scripted"

    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str, *, max_tokens: int = 800) -> str:
        self.calls.append((system, user))
        if not self.replies:
            raise LLMError("no scripted reply left")
        return self.replies.pop(0)


class OpenAICompatibleLLM:
    """POST {base_url}/chat/completions. Works with servers that implement the OpenAI chat API."""

    name = "openai_compatible"

    def __init__(self, base_url: str, api_key: str, model: str, *, timeout: float = 60.0,
                 transport: httpx.BaseTransport | None = None) -> None:
        if not (base_url and model):
            raise LLMError("LLM_BASE_URL and LLM_MODEL are required for the openai_compatible provider")
        self.base_url, self.api_key, self.model = base_url.rstrip("/"), api_key, model
        self.timeout, self.transport = timeout, transport

    def complete(self, system: str, user: str, *, max_tokens: int = 800) -> str:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body = {"model": self.model, "max_tokens": max_tokens, "temperature": 0,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        kwargs = {"timeout": self.timeout}
        if self.transport is not None:
            kwargs["transport"] = self.transport
        try:
            with httpx.Client(**kwargs) as client:
                resp = client.post(f"{self.base_url}/chat/completions", headers=headers, json=body)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"] or ""
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            raise LLMError(f"LLM request failed: {exc.__class__.__name__}") from exc


def build_llm(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "openai_compatible":
        return OpenAICompatibleLLM(settings.llm_base_url, settings.llm_api_key, settings.llm_model)
    return MockLLM()
