import re
from typing import Iterable, Optional, Tuple, List

from langgraph.graph import StateGraph, END

from src_langgraph.state import AgentState, Airport, Runway
from src_langgraph.llm import plan_steps
from src_langgraph.tools.airports import search_airports
from src_langgraph.tools.runways import filter_runways
from src_langgraph.tools.routing import build_direct_route


# --- узлы ---

def planner(state: AgentState) -> AgentState:
    state.plan = plan_steps(state.user_query)
    configure_state_from_query(state)
    return state


def get_airports(state: AgentState) -> AgentState:
    state.airports = search_airports(
        lat=state.user_lat,
        lon=state.user_lon,
        radius_km=state.radius_km,
    )
    return state


def get_runways(state: AgentState) -> AgentState:
    if not state.airports:
        state.runways = []
        state.selected_airport = None
        state.route_summary = None
        return state

    state.runways = filter_runways(
        state.airports,
        min_length_m=state.runway_min_length_m,
        max_length_m=state.runway_max_length_m,
        require_available=state.require_available_runway,
    )

    if state.mode == "route":
        state.selected_airport, state.route_summary = build_direct_route(
            state.user_lat, state.user_lon, state.airports
        )

    return state


def summarize(state: AgentState) -> AgentState:
    if state.mode == "route":
        state.final_answer = summarize_route(state)
        return state

    state.final_answer = summarize_airports(state)
    return state


# --- граф ---

def build_graph():
    g = StateGraph(AgentState)

    g.add_node("planner", planner)
    g.add_node("airports", get_airports)
    g.add_node("runways", get_runways)
    g.add_node("summary", summarize)

    g.set_entry_point("planner")

    g.add_edge("planner", "airports")
    g.add_edge("airports", "runways")
    g.add_edge("runways", "summary")
    g.add_edge("summary", END)

    return g.compile()


# --- разбор запроса ---

def configure_state_from_query(state: AgentState) -> None:
    text = state.user_query.lower()

    radius = _extract_radius_km(text)
    if radius:
        state.radius_km = radius

    runway_constraint = _extract_runway_constraint(text)
    if runway_constraint:
        constraint_type, value = runway_constraint
        if constraint_type == "min":
            state.runway_min_length_m = value
            state.runway_max_length_m = None
        else:
            state.runway_max_length_m = value
            state.runway_min_length_m = None

    state.require_available_runway = "свобод" in text

    if "маршрут" in text or "постро" in text:
        state.mode = "route"
        state.radius_km = max(state.radius_km, 1000)
    elif state.require_available_runway:
        state.mode = "available_runways"
    elif state.runway_max_length_m is not None:
        state.mode = "short_runways"
    elif state.runway_min_length_m is not None:
        state.mode = "long_runways"
    else:
        state.mode = "search_airports"


def _extract_radius_km(text: str) -> Optional[int]:
    match = re.search(r"радиус\w*\s*(\d+)", text)
    if not match:
        return None
    return int(match.group(1))


def _extract_runway_constraint(text: str) -> Optional[Tuple[str, int]]:
    match = re.search(
        r"впп[^\d]*(меньше|короче|длиннее|больше)\s*(\d+)\s*(км|м)?", text
    )
    if not match:
        return None

    comparator, value_str, unit = match.groups()
    value = int(value_str)
    if unit == "км":
        value *= 1000

    constraint_type = "max" if comparator in {"меньше", "короче"} else "min"
    return constraint_type, value


# --- форматирование ответов ---

def summarize_airports(state: AgentState) -> str:
    airports_with_runways = []
    for airport in state.airports:
        airport_runways = _runways_for_airport(state.runways, airport.icao)
        if state.mode in {"available_runways", "short_runways", "long_runways"}:
            if not airport_runways:
                continue
        airports_with_runways.append((airport, airport_runways))

    if not airports_with_runways:
        return "Не удалось найти аэропорты под заданные критерии."

    header = _build_header(state)
    lines = [header]
    for airport, airport_runways in airports_with_runways:
        base = f"- {airport.name} ({airport.icao})"
        if airport.distance_km is not None:
            base += f" — {airport.distance_km:.0f} км"
        lines.append(base)
        for runway in airport_runways:
            status = "свободна" if runway.is_available else "занята"
            lines.append(
                f"    • ВПП {runway.length_m} м, {runway.surface}, {status}"
            )
    return "\n".join(lines)


def summarize_route(state: AgentState) -> str:
    if not state.route_summary or not state.selected_airport:
        return "Не удалось построить маршрут — поблизости нет аэропортов."

    lines = ["Маршрут до ближайшего аэропорта:", state.route_summary]
    runways = _runways_for_airport(state.runways, state.selected_airport.icao)
    if runways:
        lines.append("ВПП в аэропорту назначения:")
        for runway in runways:
            status = "свободна" if runway.is_available else "занята"
            lines.append(
                f"- {runway.length_m} м, {runway.surface}, {status}"
            )
    return "\n".join(lines)


def _runways_for_airport(runways: Iterable[Runway], icao: str) -> List[Runway]:
    return [r for r in runways if r.airport_icao == icao]


def _build_header(state: AgentState) -> str:
    base = f"Найденные аэропорты в радиусе {state.radius_km} км"
    if state.mode == "available_runways":
        return base + " со свободными ВПП:"
    if state.mode == "short_runways":
        return base + f" с ВПП короче {state.runway_max_length_m} м:"
    if state.mode == "long_runways" and state.runway_min_length_m is not None:
        return base + f" с ВПП длиннее {state.runway_min_length_m} м:"
    return base + ":"
