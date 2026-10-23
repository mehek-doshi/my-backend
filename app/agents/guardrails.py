"""Guardrails: configurable rules that decide whether a candidate may be published.

A candidate that fails a *block* rule is stored with status 'blocked' (kept for the audit trail,
never shown to employees, never approvable). Flags are informational for the reviewer.
"""
from __future__ import annotations

import re

from app.agents.types import Candidate
from app.core.textutil import canonicalize_url
from app.security.injection import detect_injection
from app.security.uploads import scan_text
from app.services.app_settings import RuntimeSettings

_URL = re.compile(r"https?://[^\s)\]>\"']+", re.I)


def _kw_hit(keyword: str, text: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(keyword.lower())}(?![a-z0-9])", text.lower()) is not None


class GuardrailAgent:
    name = "guardrails"

    def check(self, cand: Candidate, runtime: RuntimeSettings, *, require_enrichment: bool = True) -> None:
        reasons: list[str] = []
        flags = list(cand.flags)
        title_and_summary = f"{cand.title} {cand.summary}"

        for kw in runtime.exclude_keywords:
            if _kw_hit(kw, title_and_summary):
                reasons.append(f"excluded_keyword:{kw}")

        # 1. injection in what the web told us
        source_report = detect_injection(f"{cand.title} {cand.raw_summary} {cand.page_text}")
        if source_report.suspicious:
            reasons.append("prompt_injection_suspected")
        # 2. injection / surprises in what the model produced
        out_text = f"{cand.summary} {cand.suggested_use_case}"
        out_report = detect_injection(out_text)
        if out_report.suspicious:
            reasons.append("llm_output_suspicious")
        known = {canonicalize_url(u) for u in (cand.url, cand.page.get("final_url", "")) if u}
        known_text = cand.text_for_analysis
        for u in _URL.findall(out_text):
            if canonicalize_url(u) not in known and u not in known_text:
                reasons.append("llm_output_unknown_url")
                break
        # 3. secrets must never reach a summary
        if scan_text("summary", out_text, []):
            reasons.append("secret_in_summary")

        if require_enrichment and (not cand.summary or len(cand.summary) < 10):
            reasons.append("empty_summary")
        if runtime.include_keywords and not any(_kw_hit(k, cand.text_for_analysis) for k in runtime.include_keywords):
            flags.append("no_include_keyword")
        if not cand.url:
            flags.append("no_source_url")

        cand.flags = sorted(set(flags))
        cand.blocked_reasons = reasons
        cand.guardrail = {
            "passed": not reasons, "reasons": reasons, "flags": cand.flags,
            "injection": source_report.matches + out_report.matches,
        }
