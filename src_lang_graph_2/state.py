from typing import List, Optional

from pydantic import BaseModel, Field


class Airport(BaseModel):
    icao: str
    name: str
    lat: float
    lon: float
    distance_km: Optional[float] = None


class Runway(BaseModel):
    airport_icao: str
    length_m: int
    surface: str
    is_available: bool


class AgentState(BaseModel):
    user_query: str
    user_lat: float = 55.75
    user_lon: float = 37.61
    radius_km: int = 150
    runway_min_length_m: Optional[int] = None
    runway_max_length_m: Optional[int] = None
    require_available_runway: bool = False
    mode: str = "search_airports"

    # результаты инструментов
    airports: List[Airport] = Field(default_factory=list)
    runways: List[Runway] = Field(default_factory=list)

    # промежуточные выводы
    plan: Optional[str] = None
    final_answer: Optional[str] = None
    selected_airport: Optional[Airport] = None
    route_summary: Optional[str] = None
