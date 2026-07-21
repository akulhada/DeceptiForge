# Purpose: load the shared, authoritative Interactive Demo Lab scenario fixtures.
# Responsibilities: read fictional scenario signal JSON + expected-result manifest from the single
#   shared source (packages/contracts/fixtures/analysis), cache in memory, and expose them for the
#   API scenario list and for backend inference tests. Tolerates a missing directory at runtime.
# Dependencies: stdlib only. No user input, no network.
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

# apps/api/app/services/analysis_lab/scenarios.py -> repo root is parents[5].
_FIXTURE_DIR = (
    Path(__file__).resolve().parents[5] / "packages" / "contracts" / "fixtures" / "analysis"
)


class Scenario:
    __slots__ = ("scenario_id", "name", "description", "signals", "expected")

    def __init__(
        self,
        scenario_id: str,
        name: str,
        description: str,
        signals: dict[str, object],
        expected: dict[str, object],
    ) -> None:
        self.scenario_id = scenario_id
        self.name = name
        self.description = description
        self.signals = signals
        self.expected = expected


@lru_cache(maxsize=1)
def _manifest() -> dict[str, object]:
    path = _FIXTURE_DIR / "manifest.json"
    if not path.is_file():
        return {"scenarios": []}
    data: dict[str, object] = json.loads(path.read_text())
    return data


@lru_cache(maxsize=1)
def load_scenarios() -> tuple[Scenario, ...]:
    """Load every scenario fixture. Empty tuple if the shared fixture dir is unavailable."""
    manifest = _manifest()
    entries = manifest.get("scenarios", [])
    scenarios: list[Scenario] = []
    if not isinstance(entries, list):
        return ()
    for entry in entries:
        signals_path = _FIXTURE_DIR / entry["file"]
        if not signals_path.is_file():
            continue
        scenarios.append(
            Scenario(
                scenario_id=entry["id"],
                name=entry["name"],
                description=entry.get("description", ""),
                signals=json.loads(signals_path.read_text()),
                expected=entry.get("expected", {}),
            )
        )
    return tuple(scenarios)


def get_scenario(scenario_id: str) -> Scenario | None:
    for scenario in load_scenarios():
        if scenario.scenario_id == scenario_id:
            return scenario
    return None
