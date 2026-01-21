from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base import Scenario
from src_agent.settings import (
    EXTRACT_PARAMS_TOOL_DESCRIPTION,
    SELECT_SCENARIO_TOOL_DESCRIPTION_TEMPLATE,
    SELECT_SCENARIO_TOOL_PARAM_REASON_DESC,
    SELECT_SCENARIO_TOOL_PARAM_SCENARIO_ID_DESC,
)
from .chitchat import ChitChatScenario
from .flight_status import FlightStatusScenario
from .flights_between_times import FlightsBetweenTimesScenario
from .airports_clarify import AirportsClarifyScenario
from .list_airports_all import ListAirportsAllScenario
from .list_airports_open import ListAirportsOpenScenario
from .list_airports_closed import ListAirportsClosedScenario
from .nearest_airports import NearestAirportsScenario
from .search_airports_by_name_or_code import SearchAirportsByNameOrCodeScenario
from .route_builder import RouteBuilderScenario

_SCENARIOS: List[Scenario] = []
_SCENARIO_BY_ID: Dict[str, Scenario] = {}


def register_scenario(scenario: Scenario) -> None:
    _SCENARIOS.append(scenario)
    _SCENARIO_BY_ID[scenario.id] = scenario


def get_scenario(scenario_id: str | None) -> Optional[Scenario]:
    if not scenario_id:
        return None
    return _SCENARIO_BY_ID.get(scenario_id)

def list_selectable_scenarios() -> List[Scenario]:
    return [s for s in _SCENARIOS if s.id != "chitchat"]


def build_select_scenario_tool_schema() -> dict:
    scenarios = list_selectable_scenarios()
    scenario_ids = [s.id for s in scenarios]
    scenario_desc = "; ".join(
        f"{s.id}: {s.title} - {s.description}" for s in scenarios
    )
    description = SELECT_SCENARIO_TOOL_DESCRIPTION_TEMPLATE.format(scenarios=scenario_desc)

    return {
        "type": "function",
        "function": {
            "name": "select_scenario",
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {
                    "scenario_id": {
                        "type": "string",
                        "enum": scenario_ids,
                        "description": SELECT_SCENARIO_TOOL_PARAM_SCENARIO_ID_DESC,
                    },
                    "reason": {
                        "type": "string",
                        "description": SELECT_SCENARIO_TOOL_PARAM_REASON_DESC,
                    },
                },
                "required": ["scenario_id"],
            },
        },
    }


def build_extract_params_tool_schema(scenario: Scenario) -> dict:
    properties: Dict[str, dict] = {}
    for name, hint in (scenario.input_hints or {}).items():
        ptype = (scenario.input_types or {}).get(name, "string")
        prop: Dict[str, Any] = {"type": ptype}
        if hint:
            prop["description"] = hint
        properties[name] = prop

    return {
        "type": "function",
        "function": {
            "name": "extract_params",
            "description": EXTRACT_PARAMS_TOOL_DESCRIPTION,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": [],
            },
        },
    }


def select_scenario_tool(args: dict) -> dict:
    scenario_id = (args or {}).get("scenario_id")
    reason = (args or {}).get("reason")
    return {"scenario_id": scenario_id, "reason": reason}


register_scenario(ChitChatScenario())
register_scenario(FlightStatusScenario())
register_scenario(FlightsBetweenTimesScenario())
register_scenario(AirportsClarifyScenario())
register_scenario(ListAirportsAllScenario())
register_scenario(ListAirportsOpenScenario())
register_scenario(ListAirportsClosedScenario())
register_scenario(NearestAirportsScenario())
register_scenario(SearchAirportsByNameOrCodeScenario())
register_scenario(RouteBuilderScenario())
