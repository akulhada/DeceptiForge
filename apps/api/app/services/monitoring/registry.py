"""In-memory tripwire registry; no external activation or persistence side effects."""

from app.models.domain.operations import TripwireRegistryEntry


class TripwireRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, TripwireRegistryEntry] = {}

    def register(self, entry: TripwireRegistryEntry) -> TripwireRegistryEntry:
        self._entries[entry.trace_identifier] = entry
        return entry

    def active(self) -> tuple[TripwireRegistryEntry, ...]:
        return tuple(
            sorted(
                (entry for entry in self._entries.values() if entry.enabled),
                key=lambda entry: entry.trace_identifier,
            )
        )

    def get(self, trace_identifier: str) -> TripwireRegistryEntry | None:
        return self._entries.get(trace_identifier)

    def disable(self, trace_identifier: str) -> bool:
        entry = self.get(trace_identifier)
        if entry is None:
            return False
        self._entries[trace_identifier] = entry.model_copy(update={"enabled": False})
        return True
