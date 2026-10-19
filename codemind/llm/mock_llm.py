"""Default 'LLM': returns the deterministic text unchanged and says so."""

from __future__ import annotations

from codemind.llm.adapter import LLMAdapter, LLMText


class MockLLM(LLMAdapter):
    label = "Mock LLM (deterministic knowledge-base text, no model used)"

    def available(self) -> bool:
        return True

    def rephrase(self, text: str, context: str = "") -> LLMText:
        return LLMText(text, "deterministic", "mock: no language model involved")
