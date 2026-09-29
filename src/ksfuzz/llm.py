"""OpenAI proposer used by the refinement loop and the knowledge agents.

Ported from the previous study's `llm.py`. Three changes: lenient fence parsing is ON by
default (a fixed setting for every arm in this repo, docs/design.md §4); the
refinement output limit is 8,000 tokens, not 2,500 (§10, after the pilot
showed truncated generators); and every call's token usage, and whether the
response was cut off, is recorded (LLM calls and tokens per arm are a
pre-registered secondary metric, §6).
"""

from typing import Any


class OpenAIProposer:
    """Turn prompts into text without hiding API failures."""

    def __init__(
        self,
        client: Any,
        model: str = "gpt-4.1-mini",
        lenient_fences: bool = True,
        max_output_tokens: int = 8000,
    ) -> None:
        self.client = client
        self.model = model
        self.lenient_fences = lenient_fences
        self.max_output_tokens = max_output_tokens
        self.usage: list[dict[str, int]] = []

    def complete(self, prompt: str, max_output_tokens: int = 2500) -> str:
        """Raw text of one response, with no fence handling."""
        response = self.client.responses.create(
            model=self.model,
            input=prompt,
            temperature=0.2,
            max_output_tokens=max_output_tokens,
        )
        usage = getattr(response, "usage", None)
        self.usage.append(
            {
                "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
                "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
                "truncated": int(getattr(response, "status", None) == "incomplete"),
            }
        )
        text = getattr(response, "output_text", None)
        if not text:
            raise RuntimeError("LLM response did not contain output_text")
        return text

    def __call__(self, prompt: str) -> str:
        text = self.complete(prompt, max_output_tokens=self.max_output_tokens)
        if self.lenient_fences:
            return extract_first_fenced_block(text)
        return strip_code_fence(text)

    def usage_totals(self) -> dict[str, int]:
        return {
            "calls": len(self.usage),
            "input_tokens": sum(u["input_tokens"] for u in self.usage),
            "output_tokens": sum(u["output_tokens"] for u in self.usage),
            "truncated": sum(u.get("truncated", 0) for u in self.usage),
        }


def strip_code_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```") and cleaned.endswith("```"):
        lines = cleaned.splitlines()
        return "\n".join(lines[1:-1]).strip()
    return cleaned


def extract_first_fenced_block(text: str) -> str:
    """Like `strip_code_fence`, but when the response opens with a fence and
    has prose after the closing one, return just the first fenced block."""
    cleaned = text.strip()
    if not cleaned.startswith("```"):
        return cleaned
    lines = cleaned.splitlines()
    for index in range(1, len(lines)):
        if lines[index].strip() == "```":
            return "\n".join(lines[1:index]).strip()
    return strip_code_fence(text)
