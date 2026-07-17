"""Exact and separator-normalized trace matching with minimized evidence."""

from hashlib import sha256
from re import sub

from app.models.domain.operations import TripwireRegistryEntry


class TraceMatcher:
    def match(
        self, text: str, entries: tuple[TripwireRegistryEntry, ...]
    ) -> tuple[TripwireRegistryEntry, float, str] | None:
        for entry in entries:
            position = text.find(entry.trace_identifier)
            if position >= 0:
                return entry, 1.0, self._excerpt(text, position, len(entry.trace_identifier))
        normalized_text = self._normalize(text)
        for entry in entries:
            trace = self._normalize(entry.trace_identifier)
            if trace in normalized_text:
                return entry, 0.85, self._excerpt(text, 0, 0)
        return None

    @staticmethod
    def digest(text: str) -> str:
        return sha256(text.encode()).hexdigest()

    @staticmethod
    def _normalize(value: str) -> str:
        return sub(r"[^a-zA-Z0-9]", "", value).upper()

    @staticmethod
    def _excerpt(text: str, position: int, length: int) -> str:
        start = max(0, position - 48)
        end = min(len(text), position + length + 48)
        return text[start:end][:256]
