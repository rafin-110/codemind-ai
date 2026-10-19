"""Replaceable LLM interface. The LLM may only reword explanations; it never sees or
changes approvals, patches, workflow state, or validation results."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMText:
    text: str
    origin: str          # "deterministic" or "llm:<model>"
    note: str = ""


class LLMAdapter:
    label = "LLM adapter"

    def available(self) -> bool:
        return False

    def rephrase(self, text: str, context: str = "") -> LLMText:
        return LLMText(text, "deterministic")


def get_default_llm() -> LLMAdapter:
    """Mock by default. Set CODEMIND_LLM=ollama to try a local Ollama model."""
    if os.environ.get("CODEMIND_LLM", "").lower() == "ollama":
        from codemind.llm.ollama_llm import OllamaLLM
        return OllamaLLM()
    from codemind.llm.mock_llm import MockLLM
    return MockLLM()
