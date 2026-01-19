from __future__ import annotations

from typing import Dict, List, Optional

from .base import Scenario
from .flight_status import FlightStatusScenario
from .flights_between_times import FlightsBetweenTimesScenario

_SCENARIOS: List[Scenario] = []
_SCENARIO_BY_ID: Dict[str, Scenario] = {}


def register_scenario(scenario: Scenario) -> None:
    _SCENARIOS.append(scenario)
    _SCENARIO_BY_ID[scenario.id] = scenario


def get_scenario(scenario_id: str | None) -> Optional[Scenario]:
    if not scenario_id:
        return None
    return _SCENARIO_BY_ID.get(scenario_id)


def select_scenario(
    prompt: str,
    current_scenario_id: str | None,
    *,
    has_pending: bool,
) -> str | None:
    matches = [s for s in _SCENARIOS if s.matches(prompt)]

    if matches:
        if current_scenario_id and any(s.id == current_scenario_id for s in matches):
            return current_scenario_id
        return matches[0].id

    if has_pending and current_scenario_id:
        return current_scenario_id

    return None


register_scenario(FlightStatusScenario())
register_scenario(FlightsBetweenTimesScenario())
