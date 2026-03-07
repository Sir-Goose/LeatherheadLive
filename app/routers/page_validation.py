from __future__ import annotations

from typing import Optional

from fastapi import HTTPException


NR_VIEWS = {"departures", "arrivals", "passing"}
TFL_VIEWS = {"departures", "arrivals"}


def validate_crs(crs: str) -> str:
    if not crs or len(crs) != 3 or not crs.isalpha():
        raise HTTPException(status_code=404, detail="Invalid CRS code")
    return crs.upper()


def validate_tfl_stop_id(stop_point_id: str) -> str:
    stop_point_id = stop_point_id.strip()
    if not stop_point_id:
        raise HTTPException(status_code=404, detail="Invalid TfL stop point id")
    return stop_point_id


def validate_tfl_line_id(line_id: str) -> str:
    line_id = line_id.strip().lower()
    if not line_id:
        raise HTTPException(status_code=404, detail="Invalid TfL line id")
    return line_id


def allowed_views(provider: str) -> set[str]:
    return NR_VIEWS if provider == "nr" else TFL_VIEWS


def validate_view(view: str, provider: str) -> str:
    if view not in allowed_views(provider):
        raise HTTPException(status_code=404, detail="Invalid view")
    return view


def normalize_board_search_view(view: Optional[str]) -> str:
    if view in NR_VIEWS:
        return view
    return "departures"


def is_valid_refresh_view(view: str, provider: str) -> bool:
    return view in allowed_views(provider)
