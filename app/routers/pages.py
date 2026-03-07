from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.middleware.cache import cache
from app.models.tfl import TflBoard
from app.routers.page_validation import (
    is_valid_refresh_view,
    normalize_board_search_view,
    validate_crs,
    validate_tfl_line_id,
    validate_tfl_stop_id,
    validate_view,
)
from app.services.display_mapper import group_tfl_trains_by_line, map_nr_trains, map_tfl_predictions
from app.services.prefetch import prefetch_service
from app.services.rail_api import BoardNotFoundError, RailAPIError, rail_api_service
from app.services.tfl_api import TflAPIError, TflBoardNotFoundError, tfl_api_service
from app.utils.time import current_time_hms, format_updated_at

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
COMMON_HOMEPAGE_NR_CRS = [
    "LHD", "WIM", "EPS", "WAT", "VIC", "PAD", "KGX", "LST", "EUS", "STP", "CHX", "CST", "LBG", "MYB"
]
COMMON_HOMEPAGE_TFL_STOPS = ["940GZZLUWSM"]


def _nr_trains_for_view(board, view: str):
    if view == "departures":
        return board.departures
    if view == "arrivals":
        return board.arrivals
    return board.passing_through


def _build_tfl_service_detail_params(
    line_id: str,
    from_stop_id: str,
    to_stop_id: str,
    direction: Optional[str] = None,
    trip_id: Optional[str] = None,
    vehicle_id: Optional[str] = None,
    expected_arrival: Optional[str] = None,
    station_name: Optional[str] = None,
    destination_name: Optional[str] = None,
) -> dict:
    return {
        "line_id": validate_tfl_line_id(line_id),
        "from_stop_id": validate_tfl_stop_id(from_stop_id),
        "to_stop_id": validate_tfl_stop_id(to_stop_id),
        "direction": direction,
        "trip_id": trip_id,
        "vehicle_id": vehicle_id,
        "expected_arrival": expected_arrival,
        "station_name": station_name,
        "destination_name": destination_name,
    }


def _tfl_service_refresh_url(request: Request, line_id: str, from_stop_id: str, to_stop_id: str) -> str:
    refresh_url = f"/service/tfl/{line_id}/{from_stop_id}/{to_stop_id}/refresh"
    if request.url.query:
        refresh_url = f"{refresh_url}?{request.url.query}"
    return refresh_url


def _build_board_context(request: Request, provider: str, board_id: str, view: str, board: dict) -> dict:
    context = {
        "request": request,
        "provider": provider,
        "board_id": board_id,
        "crs": board_id,
        "station_name": board["station_name"],
        "view": view,
        "trains": board["trains"],
        "total_trains": board["total_trains"],
        "error": board["error"],
        "timestamp": board["timestamp"],
        "line_status": board["line_status"],
    }
    if provider == "tfl":
        context["line_groups"] = board["line_groups"]
    return context


def _render_board_content_response(request: Request, provider: str, board_id: str, view: str, board: dict) -> HTMLResponse:
    tabs_html = templates.get_template("partials/tabs.html").render(provider=provider, board_id=board_id, view=view)
    board_content_html = templates.get_template("partials/board_content.html").render(
        **_build_board_context(request, provider, board_id, view, board)
    )
    search_form_html = templates.get_template("partials/search_form.html").render(view=view)
    return HTMLResponse(content=tabs_html + board_content_html + search_form_html)


def _refresh_error_response() -> HTMLResponse:
    return HTMLResponse(status_code=204)


def _build_refresh_context(request: Request, provider: str, board_id: str, view: str, board: dict) -> dict:
    context = _build_board_context(request, provider, board_id, view, board)
    context.pop("board_id", None)
    context.pop("total_trains", None)
    return context


def _render_board_refresh_response(request: Request, provider: str, board_id: str, view: str, board: dict):
    if provider == "nr":
        return templates.TemplateResponse(request, f"partials/{view}_table.html", _build_refresh_context(request, provider, board_id, view, board))
    return templates.TemplateResponse(request, "partials/tfl_refresh_content.html", _build_refresh_context(request, provider, board_id, view, board))


async def get_nr_board_data(crs: str, view: str):
    cache_key = f"board:{crs}"

    try:
        result = await rail_api_service.get_board(crs, use_cache=True)
        board = result.board
        trains = _nr_trains_for_view(board, view)

        updated_timestamp = format_updated_at(board.pulled_at or board.generated_at)
        return {
            "trains": map_nr_trains(crs, trains),
            "total_trains": len(board.trains),
            "station_name": board.location_name,
            "error": False,
            "timestamp": updated_timestamp,
            "line_status": [],
            "from_cache": result.from_cache,
        }
    except BoardNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RailAPIError:
        cached_board = cache.get(cache_key)
        if cached_board:
            if isinstance(cached_board, dict):
                cached_board = rail_api_service._parse_board(cached_board)
            trains = _nr_trains_for_view(cached_board, view)

            updated_timestamp = format_updated_at(cached_board.pulled_at or cached_board.generated_at)
            return {
                "trains": map_nr_trains(crs, trains),
                "total_trains": len(cached_board.trains),
                "station_name": cached_board.location_name,
                "error": True,
                "timestamp": updated_timestamp,
                "line_status": [],
                "from_cache": True,
            }
        raise HTTPException(status_code=500, detail="Service temporarily unavailable")


async def get_tfl_board_data(stop_point_id: str, view: str):
    stop_point_id = validate_tfl_stop_id(stop_point_id)
    cache_key = f"tfl:board:{stop_point_id.lower()}"

    try:
        result = await tfl_api_service.get_board(stop_point_id, use_cache=True)
        board = result.board
        predictions = tfl_api_service.predictions_for_view(board.trains, view)
        mapped_trains = map_tfl_predictions(predictions)
        updated_timestamp = format_updated_at(board.pulled_at or board.generated_at)
        return {
            "trains": mapped_trains,
            "line_groups": group_tfl_trains_by_line(mapped_trains, board.line_status),
            "total_trains": len(predictions),
            "station_name": board.station_name,
            "error": False,
            "timestamp": updated_timestamp,
            "line_status": board.line_status,
            "from_cache": result.from_cache,
        }
    except TflBoardNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TflAPIError:
        cached_board = cache.get(cache_key)
        if isinstance(cached_board, dict):
            board = TflBoard(**cached_board)
            predictions = tfl_api_service.predictions_for_view(board.trains, view)
            mapped_trains = map_tfl_predictions(predictions)
            updated_timestamp = format_updated_at(board.pulled_at or board.generated_at)
            return {
                "trains": mapped_trains,
                "line_groups": group_tfl_trains_by_line(mapped_trains, board.line_status),
                "total_trains": len(predictions),
                "station_name": board.station_name,
                "error": True,
                "timestamp": updated_timestamp,
                "line_status": board.line_status,
                "from_cache": True,
            }
        raise HTTPException(status_code=500, detail="Service temporarily unavailable")


def schedule_homepage_board_prefetches() -> None:
    for crs in COMMON_HOMEPAGE_NR_CRS:
        prefetch_service.schedule_nr_board_prefetch(crs)
    for stop_id in COMMON_HOMEPAGE_TFL_STOPS:
        prefetch_service.schedule_tfl_board_prefetch(stop_id)


def schedule_nr_board_prefetch(crs: str, board: dict) -> None:
    for train in board.get("trains", []):
        service_id = train.get("service_id")
        if service_id and train.get("service_url"):
            prefetch_service.schedule_nr_service_prefetch(crs, service_id)


def schedule_tfl_board_prefetch(board: dict) -> None:
    for train in board.get("trains", []):
        line_id = train.get("line_id")
        from_stop_id = train.get("from_stop_id")
        to_stop_id = train.get("to_stop_id")
        if not train.get("service_url") or not line_id or not from_stop_id or not to_stop_id:
            continue

        expected_arrival = train.get("expected_arrival")
        if expected_arrival is not None and hasattr(expected_arrival, "isoformat"):
            expected_arrival = expected_arrival.isoformat()

        prefetch_service.schedule_tfl_service_prefetch(
            {
                "line_id": line_id,
                "from_stop_id": from_stop_id,
                "to_stop_id": to_stop_id,
                "direction": train.get("direction"),
                "trip_id": train.get("trip_id"),
                "vehicle_id": train.get("vehicle_id"),
                "expected_arrival": expected_arrival,
                "station_name": train.get("station_name"),
                "destination_name": train.get("destination_name"),
            }
        )


def schedule_nr_service_boards_prefetch(service) -> None:
    seen: set[str] = set()

    def add(crs: Optional[str]) -> None:
        normalized = (crs or "").strip().upper()
        if len(normalized) == 3 and normalized.isalpha() and normalized not in seen:
            seen.add(normalized)
            prefetch_service.schedule_nr_board_prefetch(normalized)

    add(getattr(service, "crs", None))
    for stop in getattr(service, "all_previous_station_stops", []) or []:
        add(getattr(stop, "crs", None))
    for stop in getattr(service, "all_subsequent_station_stops", []) or []:
        add(getattr(stop, "crs", None))


def schedule_tfl_service_boards_prefetch(service) -> None:
    seen: set[str] = set()
    for stop in getattr(service, "stops", []) or []:
        stop_id = (getattr(stop, "stop_id", None) or "").strip()
        if stop_id and stop_id not in seen:
            seen.add(stop_id)
            prefetch_service.schedule_tfl_board_prefetch(stop_id)


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    schedule_homepage_board_prefetches()
    return templates.TemplateResponse(request, "index.html", {"timestamp": current_time_hms()})


@router.get("/board", response_class=RedirectResponse)
async def board_search(crs: str, view: Optional[str] = "departures"):
    crs = validate_crs(crs)
    view = normalize_board_search_view(view)
    return RedirectResponse(url=f"/board/nr/{crs}/{view}", status_code=303)


@router.get("/service/{crs}/{service_id}", response_class=HTMLResponse)
async def service_detail_page(request: Request, crs: str, service_id: str):
    crs = validate_crs(crs)
    service = await rail_api_service.get_service_route_cached(crs, service_id, use_cache=True)
    if not service:
        service = await rail_api_service.get_service_route_from_timetable(crs, service_id)

    if not service:
        return templates.TemplateResponse(
            request,
            "errors/service_expired.html",
            {"service_id": service_id, "timestamp": current_time_hms()},
            status_code=404,
        )

    schedule_nr_service_boards_prefetch(service)

    return templates.TemplateResponse(
        request,
        "service_detail.html",
        {"service": service, "timestamp": format_updated_at(service.pulledAt or service.generatedAt)},
    )


@router.get("/service/{crs}/{service_id}/refresh", response_class=HTMLResponse)
async def service_detail_refresh(request: Request, crs: str, service_id: str):
    crs = validate_crs(crs)
    service = await rail_api_service.get_service_route(crs, service_id, use_cache=False)
    if not service:
        service = await rail_api_service.get_service_route_from_timetable(crs, service_id)

    if not service:
        return HTMLResponse(content="<div class='error-message'>Service no longer available</div>", status_code=200)

    schedule_nr_service_boards_prefetch(service)

    return templates.TemplateResponse(
        request,
        "partials/service_timeline.html",
        {"service": service, "timestamp": format_updated_at(service.pulledAt or service.generatedAt)},
    )


@router.get("/service/tfl/{line_id}/{from_stop_id}/{to_stop_id}", response_class=HTMLResponse)
async def tfl_service_detail_page(
    request: Request,
    line_id: str,
    from_stop_id: str,
    to_stop_id: str,
    direction: Optional[str] = None,
    trip_id: Optional[str] = None,
    vehicle_id: Optional[str] = None,
    expected_arrival: Optional[str] = None,
    station_name: Optional[str] = None,
    destination_name: Optional[str] = None,
):
    params = _build_tfl_service_detail_params(
        line_id,
        from_stop_id,
        to_stop_id,
        direction=direction,
        trip_id=trip_id,
        vehicle_id=vehicle_id,
        expected_arrival=expected_arrival,
        station_name=station_name,
        destination_name=destination_name,
    )

    try:
        service = await tfl_api_service.get_service_route_detail_cached(**params, use_cache=True)
    except (TflBoardNotFoundError, TflAPIError):
        return templates.TemplateResponse(
            request,
            "errors/service_expired.html",
            {
                "service_id": f"{params['line_id']}:{params['from_stop_id']}:{params['to_stop_id']}",
                "timestamp": current_time_hms(),
            },
            status_code=404,
        )

    schedule_tfl_service_boards_prefetch(service)

    return templates.TemplateResponse(
        request,
        "tfl_service_detail.html",
        {
            "service": service,
            "refresh_url": _tfl_service_refresh_url(
                request,
                params["line_id"],
                params["from_stop_id"],
                params["to_stop_id"],
            ),
            "timestamp": format_updated_at(service.pulled_at),
        },
    )


@router.get("/service/tfl/{line_id}/{from_stop_id}/{to_stop_id}/refresh", response_class=HTMLResponse)
async def tfl_service_detail_refresh(
    request: Request,
    line_id: str,
    from_stop_id: str,
    to_stop_id: str,
    direction: Optional[str] = None,
    trip_id: Optional[str] = None,
    vehicle_id: Optional[str] = None,
    expected_arrival: Optional[str] = None,
    station_name: Optional[str] = None,
    destination_name: Optional[str] = None,
):
    params = _build_tfl_service_detail_params(
        line_id,
        from_stop_id,
        to_stop_id,
        direction=direction,
        trip_id=trip_id,
        vehicle_id=vehicle_id,
        expected_arrival=expected_arrival,
        station_name=station_name,
        destination_name=destination_name,
    )

    try:
        service = await tfl_api_service.get_service_route_detail(**params, use_cache=False)
    except (TflBoardNotFoundError, TflAPIError):
        return HTMLResponse(
            content="<div class='error-message'>Route no longer available</div>",
            status_code=200,
        )

    schedule_tfl_service_boards_prefetch(service)

    return templates.TemplateResponse(
        request,
        "partials/tfl_service_timeline.html",
        {"service": service, "timestamp": format_updated_at(service.pulled_at)},
    )


@router.get("/board/{crs}", response_class=RedirectResponse)
async def board_redirect(crs: str):
    crs = validate_crs(crs)
    return RedirectResponse(url=f"/board/nr/{crs}/departures", status_code=307)


@router.get("/board/{crs}/{view}", response_class=RedirectResponse)
async def board_redirect_legacy(crs: str, view: str):
    crs = validate_crs(crs)
    validate_view(view, "nr")
    return RedirectResponse(url=f"/board/nr/{crs}/{view}", status_code=307)


@router.get("/board/nr/{crs}/{view}", response_class=HTMLResponse)
async def board_view_nr(request: Request, crs: str, view: str):
    crs = validate_crs(crs)
    view = validate_view(view, "nr")
    board = await get_nr_board_data(crs, view)
    schedule_nr_board_prefetch(crs, board)

    return templates.TemplateResponse(request, "board.html", _build_board_context(request, "nr", crs, view, board))


@router.get("/board/tfl/{stop_point_id}/{view}", response_class=HTMLResponse)
async def board_view_tfl(request: Request, stop_point_id: str, view: str):
    stop_point_id = validate_tfl_stop_id(stop_point_id)
    view = validate_view(view, "tfl")
    board = await get_tfl_board_data(stop_point_id, view)
    schedule_tfl_board_prefetch(board)

    return templates.TemplateResponse(request, "board.html", _build_board_context(request, "tfl", stop_point_id, view, board))


@router.get("/board/nr/{crs}/{view}/content", response_class=HTMLResponse)
async def board_content_nr(request: Request, crs: str, view: str):
    crs = validate_crs(crs)
    view = validate_view(view, "nr")
    board = await get_nr_board_data(crs, view)
    schedule_nr_board_prefetch(crs, board)

    return _render_board_content_response(request, "nr", crs, view, board)


@router.get("/board/tfl/{stop_point_id}/{view}/content", response_class=HTMLResponse)
async def board_content_tfl(request: Request, stop_point_id: str, view: str):
    stop_point_id = validate_tfl_stop_id(stop_point_id)
    view = validate_view(view, "tfl")
    board = await get_tfl_board_data(stop_point_id, view)
    schedule_tfl_board_prefetch(board)

    return _render_board_content_response(request, "tfl", stop_point_id, view, board)


@router.get("/board/nr/{crs}/{view}/refresh", response_class=HTMLResponse)
async def board_refresh_nr(request: Request, crs: str, view: str):
    crs = validate_crs(crs)
    if not is_valid_refresh_view(view, "nr"):
        return _refresh_error_response()

    try:
        board = await get_nr_board_data(crs, view)
        schedule_nr_board_prefetch(crs, board)
        return _render_board_refresh_response(request, "nr", crs, view, board)
    except Exception:
        return _refresh_error_response()


@router.get("/board/tfl/{stop_point_id}/{view}/refresh", response_class=HTMLResponse)
async def board_refresh_tfl(request: Request, stop_point_id: str, view: str):
    stop_point_id = validate_tfl_stop_id(stop_point_id)
    if not is_valid_refresh_view(view, "tfl"):
        return _refresh_error_response()

    try:
        board = await get_tfl_board_data(stop_point_id, view)
        schedule_tfl_board_prefetch(board)
        return _render_board_refresh_response(request, "tfl", stop_point_id, view, board)
    except Exception:
        return _refresh_error_response()
