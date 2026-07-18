# Purpose: define the narrative model-client boundary and a lazy OpenAI adapter.
# Responsibilities: keep OpenAI optional (imported only when actually called) so the app and tests
#   never require the SDK. Dependencies: token-usage model; openai is optional at runtime.
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.models.domain.narrative import TokenUsage


@dataclass(frozen=True)
class ModelResult:
    json_text: str
    model: str
    token_usage: TokenUsage | None


class NarrativeModelClient(Protocol):
    """A minimal completion boundary; implementations return schema-constrained JSON text."""

    def complete(
        self, *, system: str, user: str, schema: dict[str, object], model: str
    ) -> ModelResult: ...


class OpenAINarrativeClient:
    """OpenAI adapter. The SDK is imported lazily so it is never a hard dependency."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def complete(
        self, *, system: str, user: str, schema: dict[str, object], model: str
    ) -> ModelResult:
        from openai import OpenAI  # type: ignore[import-not-found]  # optional dependency

        client = OpenAI(api_key=self._api_key)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_schema", "json_schema": schema},
            temperature=0.2,
            max_tokens=700,
        )
        usage = response.usage
        token_usage = (
            TokenUsage(
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens,
            )
            if usage is not None
            else None
        )
        return ModelResult(
            json_text=response.choices[0].message.content or "",
            model=model,
            token_usage=token_usage,
        )
