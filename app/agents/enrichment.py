"""LLM enrichment agent: summary, category suggestion and a suggested use case."""
from __future__ import annotations

from app.agents.types import Candidate, EnrichmentOutput
from app.core.textutil import clean_text
from app.llm.base import LLMProvider, generate_structured
from app.security.injection import SYSTEM_GUARD, wrap_untrusted
from app.services.app_settings import RuntimeSettings

_INSTRUCTIONS = (
    "Return one JSON object with exactly these keys: "
    "summary (2 sentences, plain text), category (one of CATEGORIES, or empty), "
    "suggested_use_case (one sentence), low_cost_simulation (true if running it for real would be expensive "
    "and a simulation is the cheaper way to evaluate it)."
)


class EnrichmentAgent:
    name = "enrichment"

    def __init__(self, llm: LLMProvider) -> None:
        self.llm = llm

    def enrich(self, cand: Candidate, runtime: RuntimeSettings, category_names: list[str]) -> None:
        keywords = ", ".join(clean_text(k, 60) for k in runtime.include_keywords)
        cats = " | ".join(clean_text(c, 100) for c in category_names)
        user = (
            "TASK: enrich\n"
            f"{wrap_untrusted('title', cand.title, 300)}\n"
            f"{wrap_untrusted('article', (cand.raw_summary + ' ' + cand.page_text).strip(), 4000)}\n"
            f"INCLUDE_KEYWORDS: {keywords}\nCATEGORIES: {cats}\n{_INSTRUCTIONS}"
        )
        out = generate_structured(self.llm, SYSTEM_GUARD, user, EnrichmentOutput)
        cand.summary = clean_text(out.summary, 600)
        cand.llm_category = out.category.strip()
        cand.suggested_use_case = clean_text(out.suggested_use_case, 600)
        cand.low_cost = out.low_cost_simulation
