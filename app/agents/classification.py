"""Classification agent: maps a candidate onto one of the configured categories (never invents one)."""
from __future__ import annotations

import re

from app.agents.types import Candidate
from app.db.models import Category
from app.llm.providers import category_hints


class ClassificationAgent:
    name = "classification"

    def classify(self, cand: Candidate, categories: list[Category]) -> None:
        active = [c for c in categories if not c.retired]
        by_name = {c.name.lower(): c for c in active}
        chosen = by_name.get(cand.llm_category.lower()) if cand.llm_category else None
        if chosen is None:
            text = f"{cand.title} {cand.summary}".lower()
            best, best_score = None, 0
            for c in active:
                hints = category_hints().get(c.name.lower(), []) + re.findall(r"[a-z]{4,}", c.name.lower())
                score = sum(1 for h in hints if h in text)
                if score > best_score:
                    best, best_score = c, score
            chosen = best
        if chosen is None:
            cand.flags.append("needs_category")
            return
        cand.category_id, cand.category_name = chosen.id, chosen.name
