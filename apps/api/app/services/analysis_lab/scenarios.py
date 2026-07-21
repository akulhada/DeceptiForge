# Purpose: load the shared, authoritative Interactive Demo Lab scenario fixtures.
# Responsibilities: read fictional scenario signal JSON + expected-result manifest from the single
#   shared source (packages/contracts/fixtures/analysis), cache in memory, and expose them for the
#   API scenario list and for backend inference tests. Tolerates a missing directory at runtime.
# Dependencies: stdlib only. No user input, no network.
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


def _find_fixture_dir() -> Path:
    """Find the shared fixtures in a source checkout or the packaged API image.

    Source checkouts keep the authoritative fixtures under ``packages/contracts``. The API image
    copies those same files to ``/app/fixtures`` because its build context does not retain the
    monorepo layout. Walking ancestors avoids assumptions about either layout depth.
    """
    module_path = Path(__file__).resolve()
    for ancestor in module_path.parents:
        candidates = (
            ancestor / "packages" / "contracts" / "fixtures" / "analysis",
            ancestor / "fixtures" / "analysis",
        )
        for candidate in candidates:
            if candidate.is_dir():
                return candidate
    # Keep import-time behavior safe if an installation omits optional fixtures.
    return module_path.parent / "fixtures" / "analysis"


_FIXTURE_DIR = _find_fixture_dir()


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
