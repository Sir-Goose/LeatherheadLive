from fastapi.testclient import TestClient

from app.main import app
from app.models.tfl_service import TflServiceDetail, TflServiceStop
from app.services.tfl_api import TflAPIError


def test_legacy_board_route_redirects_to_nr():
    client = TestClient(app)
    response = client.get('/board/LHD/departures', follow_redirects=False)

    assert response.status_code == 307
    assert response.headers['location'] == '/board/nr/LHD/departures'


def test_tfl_passing_route_returns_not_found():
    client = TestClient(app)
    response = client.get('/board/tfl/940GZZLUBXN/passing')

    assert response.status_code == 404


def test_legacy_board_route_invalid_view_returns_not_found():
    client = TestClient(app)
    response = client.get('/board/LHD/bogus', follow_redirects=False)

    assert response.status_code == 404
    assert '<!DOCTYPE html>' in response.text


def test_tfl_board_page_renders_provider_badge(monkeypatch):
    async def fake_get_tfl_board_data(stop_point_id: str, view: str):
        return {
            "trains": [],
            "line_groups": [],
            "total_trains": 0,
            "station_name": "Brixton Underground Station",
            "error": False,
            "timestamp": "12:00:00",
            "line_status": [],
        }

    monkeypatch.setattr('app.routers.pages.get_tfl_board_data', fake_get_tfl_board_data)

    client = TestClient(app)
    response = client.get('/board/tfl/940GZZLUBXN/departures')

    assert response.status_code == 200
    assert 'TfL' in response.text


def test_tfl_board_page_does_not_prefix_location_with_via(monkeypatch):
    row = {
        "is_cancelled": False,
        "time_status_class": "time-ontime",
        "scheduled_departure_time": "10:21",
        "scheduled_arrival_time": "10:21",
        "display_time_departure": "10:21",
        "display_time_arrival": "10:21",
        "destination_name": "Walthamstow Central Underground Station",
        "destination_via": "Approaching Green Park",
        "destination_via_prefix": None,
        "origin_name": "Northbound",
        "platform": "Platform 3",
        "operator": "TfL",
        "line_name": "Victoria",
        "line_id": "victoria",
        "service_url": None,
        "route_unavailable": False,
    }

    async def fake_get_tfl_board_data(stop_point_id: str, view: str):
        return {
            "trains": [row],
            "line_groups": [
                {
                    "line_id": "victoria",
                    "line_name": "Victoria",
                    "status": None,
                    "trains": [row],
                    "next_time_epoch": 0,
                }
            ],
            "total_trains": 1,
            "station_name": "Green Park Underground Station",
            "error": False,
            "timestamp": "10:20:00",
            "line_status": [],
        }

    monkeypatch.setattr('app.routers.pages.get_tfl_board_data', fake_get_tfl_board_data)

    client = TestClient(app)
    response = client.get('/board/tfl/HUBGPK/departures')

    assert response.status_code == 200
    assert 'Approaching Green Park' in response.text
    assert 'via Approaching Green Park' not in response.text


def test_tfl_board_page_renders_grouped_line_sections(monkeypatch):
    async def fake_get_tfl_board_data(stop_point_id: str, view: str):
        return {
            "trains": [],
            "line_groups": [
                {
                    "line_id": "victoria",
                    "line_name": "Victoria",
                    "status": None,
                    "trains": [
                        {
                            "is_cancelled": False,
                            "time_status_class": "time-ontime",
                            "display_time_departure": "10:21",
                            "display_time_arrival": "10:21",
                            "destination_name": "Walthamstow Central Underground Station",
                            "destination_via": "Approaching Green Park",
                            "destination_via_prefix": None,
                            "origin_name": "Northbound",
                            "platform": "Platform 3",
                            "operator": "TfL",
                            "line_name": "Victoria",
                            "service_url": "/service/tfl/victoria/940GZZLUGPK/940GZZLUBXN",
                            "route_unavailable": False,
                        }
                    ],
                    "next_time_epoch": 0,
                },
                {
                    "line_id": "jubilee",
                    "line_name": "Jubilee",
                    "status": None,
                    "trains": [
                        {
                            "is_cancelled": False,
                            "time_status_class": "time-ontime",
                            "display_time_departure": "10:22",
                            "display_time_arrival": "10:22",
                            "destination_name": "Stratford Underground Station",
                            "destination_via": "Between Bond Street and Green Park",
                            "destination_via_prefix": None,
                            "origin_name": "Southbound",
                            "platform": "Platform 6",
                            "operator": "TfL",
                            "line_name": "Jubilee",
                            "service_url": "/service/tfl/jubilee/940GZZLUGPK/940GZZLUSTD",
                            "route_unavailable": False,
                        }
                    ],
                    "next_time_epoch": 1,
                },
            ],
            "total_trains": 2,
            "station_name": "Green Park Underground Station",
            "error": False,
            "timestamp": "10:20:00",
            "line_status": [],
        }

    monkeypatch.setattr('app.routers.pages.get_tfl_board_data', fake_get_tfl_board_data)

    client = TestClient(app)
    response = client.get('/board/tfl/HUBGPK/departures')

    assert response.status_code == 200
    assert 'tfl-line-group-title' in response.text
    assert '>Victoria<' in response.text
    assert '>Jubilee<' in response.text
    assert '/service/tfl/victoria/' in response.text


def test_tfl_service_detail_page_renders_timeline(monkeypatch):
    detail = TflServiceDetail(
        line_id="victoria",
        line_name="Victoria",
        direction="northbound",
        from_stop_id="940GZZLUBXN",
        to_stop_id="940GZZLUGPK",
        origin_name="Brixton Underground Station",
        destination_name="Green Park Underground Station",
        resolution_mode="exact",
        mode_name="tube",
        stops=[
            TflServiceStop(
                stop_id="940GZZLUBXN",
                stop_name="Brixton Underground Station",
                arrival_display="Due",
                departure_display="Due",
                is_current=True,
            ),
            TflServiceStop(
                stop_id="940GZZLUGPK",
                stop_name="Green Park Underground Station",
                arrival_display="8 min (10:29)",
                departure_display="8 min (10:29)",
                is_destination=True,
            ),
        ],
    )

    async def fake_get_service_route_detail(**kwargs):
        return detail

    monkeypatch.setattr('app.routers.pages.tfl_api_service.get_service_route_detail_cached', fake_get_service_route_detail)

    client = TestClient(app)
    response = client.get('/service/tfl/victoria/940GZZLUBXN/940GZZLUGPK?direction=northbound')

    assert response.status_code == 200
    assert 'Brixton Underground Station' in response.text
    assert 'Green Park Underground Station' in response.text
    assert 'Exact match' in response.text


def test_tfl_service_detail_page_normalizes_line_and_stop_ids_before_cached_fetch(monkeypatch):
    detail = TflServiceDetail(
        line_id="victoria",
        line_name="Victoria",
        direction="northbound",
        from_stop_id="940GZZLUBXN",
        to_stop_id="940GZZLUGPK",
        origin_name="Brixton Underground Station",
        destination_name="Green Park Underground Station",
        resolution_mode="exact",
        mode_name="tube",
        stops=[],
    )
    captured: dict = {}

    async def fake_get_service_route_detail_cached(**kwargs):
        captured.update(kwargs)
        return detail

    monkeypatch.setattr('app.routers.pages.tfl_api_service.get_service_route_detail_cached', fake_get_service_route_detail_cached)

    client = TestClient(app)
    response = client.get('/service/tfl/%20Victoria%20/%20940GZZLUBXN%20/%20940GZZLUGPK%20?direction=northbound')

    assert response.status_code == 200
    assert captured['line_id'] == 'victoria'
    assert captured['from_stop_id'] == '940GZZLUBXN'
    assert captured['to_stop_id'] == '940GZZLUGPK'


def test_tfl_service_detail_refresh_normalizes_line_and_stop_ids_before_live_fetch(monkeypatch):
    detail = TflServiceDetail(
        line_id="victoria",
        line_name="Victoria",
        direction="northbound",
        from_stop_id="940GZZLUBXN",
        to_stop_id="940GZZLUGPK",
        origin_name="Brixton Underground Station",
        destination_name="Green Park Underground Station",
        resolution_mode="exact",
        mode_name="tube",
        stops=[],
    )
    captured: dict = {}

    async def fake_get_service_route_detail(**kwargs):
        captured.update(kwargs)
        return detail

    monkeypatch.setattr('app.routers.pages.tfl_api_service.get_service_route_detail', fake_get_service_route_detail)

    client = TestClient(app)
    response = client.get('/service/tfl/%20Victoria%20/%20940GZZLUBXN%20/%20940GZZLUGPK%20/refresh?direction=northbound')

    assert response.status_code == 200
    assert captured['line_id'] == 'victoria'
    assert captured['from_stop_id'] == '940GZZLUBXN'
    assert captured['to_stop_id'] == '940GZZLUGPK'


def test_tfl_service_detail_page_forwards_optional_query_params_and_refresh_url(monkeypatch):
    detail = TflServiceDetail(
        line_id="victoria",
        line_name="Victoria",
        direction="northbound",
        from_stop_id="940GZZLUBXN",
        to_stop_id="940GZZLUGPK",
        origin_name="Brixton Underground Station",
        destination_name="Green Park Underground Station",
        resolution_mode="exact",
        mode_name="tube",
        stops=[],
    )
    captured: dict = {}

    async def fake_get_service_route_detail_cached(**kwargs):
        captured.update(kwargs)
        return detail

    monkeypatch.setattr('app.routers.pages.tfl_api_service.get_service_route_detail_cached', fake_get_service_route_detail_cached)

    client = TestClient(app)
    response = client.get(
        '/service/tfl/victoria/940GZZLUBXN/940GZZLUGPK'
        '?direction=northbound&trip_id=trip-1&vehicle_id=veh-9&expected_arrival=2026-01-01T12:00:00Z'
        '&station_name=Brixton%20Underground%20Station&destination_name=Green%20Park%20Underground%20Station'
    )

    assert response.status_code == 200
    assert captured['direction'] == 'northbound'
    assert captured['trip_id'] == 'trip-1'
    assert captured['vehicle_id'] == 'veh-9'
    assert captured['expected_arrival'] == '2026-01-01T12:00:00Z'
    assert captured['station_name'] == 'Brixton Underground Station'
    assert captured['destination_name'] == 'Green Park Underground Station'
    assert 'hx-get="/service/tfl/victoria/940GZZLUBXN/940GZZLUGPK/refresh?direction=northbound&amp;trip_id=trip-1' in response.text


def test_tfl_service_detail_refresh_forwards_optional_query_params(monkeypatch):
    detail = TflServiceDetail(
        line_id="victoria",
        line_name="Victoria",
        direction="northbound",
        from_stop_id="940GZZLUBXN",
        to_stop_id="940GZZLUGPK",
        origin_name="Brixton Underground Station",
        destination_name="Green Park Underground Station",
        resolution_mode="exact",
        mode_name="tube",
        stops=[],
    )
    captured: dict = {}

    async def fake_get_service_route_detail(**kwargs):
        captured.update(kwargs)
        return detail

    monkeypatch.setattr('app.routers.pages.tfl_api_service.get_service_route_detail', fake_get_service_route_detail)

    client = TestClient(app)
    response = client.get(
        '/service/tfl/victoria/940GZZLUBXN/940GZZLUGPK/refresh'
        '?direction=northbound&trip_id=trip-1&vehicle_id=veh-9&expected_arrival=2026-01-01T12:00:00Z'
        '&station_name=Brixton%20Underground%20Station&destination_name=Green%20Park%20Underground%20Station'
    )

    assert response.status_code == 200
    assert captured['direction'] == 'northbound'
    assert captured['trip_id'] == 'trip-1'
    assert captured['vehicle_id'] == 'veh-9'
    assert captured['expected_arrival'] == '2026-01-01T12:00:00Z'
    assert captured['station_name'] == 'Brixton Underground Station'
    assert captured['destination_name'] == 'Green Park Underground Station'


def test_tfl_service_detail_page_returns_expired_template_on_error(monkeypatch):
    calls: list[str] = []

    async def fake_get_service_route_detail_cached(**kwargs):
        raise TflAPIError('boom')

    def fake_schedule_tfl_board_prefetch(stop_point_id: str):
        calls.append(stop_point_id)

    monkeypatch.setattr('app.routers.pages.tfl_api_service.get_service_route_detail_cached', fake_get_service_route_detail_cached)
    monkeypatch.setattr('app.routers.pages.prefetch_service.schedule_tfl_board_prefetch', fake_schedule_tfl_board_prefetch)

    client = TestClient(app)
    response = client.get('/service/tfl/victoria/940GZZLUBXN/940GZZLUGPK')

    assert response.status_code == 404
    assert 'Service Expired' in response.text
    assert calls == []


def test_tfl_service_detail_refresh_returns_inline_error_on_error(monkeypatch):
    calls: list[str] = []

    async def fake_get_service_route_detail(**kwargs):
        raise TflAPIError('boom')

    def fake_schedule_tfl_board_prefetch(stop_point_id: str):
        calls.append(stop_point_id)

    monkeypatch.setattr('app.routers.pages.tfl_api_service.get_service_route_detail', fake_get_service_route_detail)
    monkeypatch.setattr('app.routers.pages.prefetch_service.schedule_tfl_board_prefetch', fake_schedule_tfl_board_prefetch)

    client = TestClient(app)
    response = client.get('/service/tfl/victoria/940GZZLUBXN/940GZZLUGPK/refresh')

    assert response.status_code == 200
    assert 'Route no longer available' in response.text
    assert calls == []


def test_tfl_board_prefetch_runs_for_fresh_board(monkeypatch):
    async def fake_get_tfl_board_data(stop_point_id: str, view: str):
        return {
            "trains": [
                {
                    "line_id": "victoria",
                    "from_stop_id": "940GZZLUGPK",
                    "to_stop_id": "940GZZLUBXN",
                    "direction": "outbound",
                    "trip_id": "trip-1",
                    "vehicle_id": "veh-1",
                    "expected_arrival": "2026-01-01T12:00:00+00:00",
                    "origin_name": "Green Park Underground Station",
                    "destination_name": "Brixton Underground Station",
                    "service_url": "/service/tfl/victoria/940GZZLUGPK/940GZZLUBXN",
                }
            ],
            "line_groups": [],
            "total_trains": 1,
            "station_name": "Green Park Underground Station",
            "error": False,
            "timestamp": "12:00:00",
            "line_status": [],
            "from_cache": False,
        }

    calls: list[dict] = []

    def fake_schedule_tfl_service_prefetch(params: dict):
        calls.append(params)

    monkeypatch.setattr('app.routers.pages.get_tfl_board_data', fake_get_tfl_board_data)
    monkeypatch.setattr('app.routers.pages.prefetch_service.schedule_tfl_service_prefetch', fake_schedule_tfl_service_prefetch)

    client = TestClient(app)
    response = client.get('/board/tfl/940GZZLUGPK/departures')

    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0]["line_id"] == "victoria"


def test_tfl_board_prefetch_runs_when_board_from_cache(monkeypatch):
    async def fake_get_tfl_board_data(stop_point_id: str, view: str):
        return {
            "trains": [
                {
                    "line_id": "victoria",
                    "from_stop_id": "940GZZLUGPK",
                    "to_stop_id": "940GZZLUBXN",
                    "service_url": "/service/tfl/victoria/940GZZLUGPK/940GZZLUBXN",
                }
            ],
            "line_groups": [],
            "total_trains": 1,
            "station_name": "Green Park Underground Station",
            "error": False,
            "timestamp": "12:00:00",
            "line_status": [],
            "from_cache": True,
        }

    calls: list[dict] = []

    def fake_schedule_tfl_service_prefetch(params: dict):
        calls.append(params)

    monkeypatch.setattr('app.routers.pages.get_tfl_board_data', fake_get_tfl_board_data)
    monkeypatch.setattr('app.routers.pages.prefetch_service.schedule_tfl_service_prefetch', fake_schedule_tfl_service_prefetch)

    client = TestClient(app)
    response = client.get('/board/tfl/940GZZLUGPK/departures')

    assert response.status_code == 200
    assert len(calls) == 1


def test_tfl_board_content_prefetch_runs_for_fresh_board(monkeypatch):
    async def fake_get_tfl_board_data(stop_point_id: str, view: str):
        return {
            "trains": [
                {
                    "line_id": "victoria",
                    "from_stop_id": "940GZZLUGPK",
                    "to_stop_id": "940GZZLUBXN",
                    "service_url": "/service/tfl/victoria/940GZZLUGPK/940GZZLUBXN",
                }
            ],
            "line_groups": [],
            "total_trains": 1,
            "station_name": "Green Park Underground Station",
            "error": False,
            "timestamp": "12:00:00",
            "line_status": [],
            "from_cache": False,
        }

    calls: list[dict] = []

    def fake_schedule_tfl_service_prefetch(params: dict):
        calls.append(params)

    monkeypatch.setattr('app.routers.pages.get_tfl_board_data', fake_get_tfl_board_data)
    monkeypatch.setattr('app.routers.pages.prefetch_service.schedule_tfl_service_prefetch', fake_schedule_tfl_service_prefetch)

    client = TestClient(app)
    response = client.get('/board/tfl/940GZZLUGPK/departures/content')

    assert response.status_code == 200
    assert len(calls) == 1
    assert 'hx-get="/board/tfl/940GZZLUGPK/departures/content"' in response.text
    assert 'tfl-line-group-title' not in response.text
    assert 'Find Another Station' in response.text


def test_tfl_board_content_renders_grouped_sections_and_search(monkeypatch):
    async def fake_get_tfl_board_data(stop_point_id: str, view: str):
        return {
            "trains": [],
            "line_groups": [
                {
                    "line_id": "victoria",
                    "line_name": "Victoria",
                    "line_color": "#0098d4",
                    "line_tint": "rgba(0, 152, 212, 0.12)",
                    "line_border_tint": "rgba(0, 152, 212, 0.3)",
                    "status": None,
                    "trains": [],
                    "next_time_epoch": 0,
                }
            ],
            "total_trains": 0,
            "station_name": "Green Park Underground Station",
            "error": False,
            "timestamp": "12:00:00",
            "line_status": [],
            "from_cache": False,
        }

    monkeypatch.setattr('app.routers.pages.get_tfl_board_data', fake_get_tfl_board_data)

    client = TestClient(app)
    response = client.get('/board/tfl/940GZZLUGPK/departures/content')

    assert response.status_code == 200
    assert 'tfl-line-group-title' in response.text
    assert 'Find Another Station' in response.text
    assert 'Passing Through' not in response.text


def test_tfl_board_refresh_prefetch_runs_for_fresh_board(monkeypatch):
    async def fake_get_tfl_board_data(stop_point_id: str, view: str):
        return {
            "trains": [
                {
                    "line_id": "victoria",
                    "from_stop_id": "940GZZLUGPK",
                    "to_stop_id": "940GZZLUBXN",
                    "service_url": "/service/tfl/victoria/940GZZLUGPK/940GZZLUBXN",
                }
            ],
            "line_groups": [
                {
                    "line_id": "victoria",
                    "line_name": "Victoria",
                    "line_color": "#0098d4",
                    "line_tint": "rgba(0, 152, 212, 0.12)",
                    "line_border_tint": "rgba(0, 152, 212, 0.3)",
                    "status": None,
                    "trains": [
                        {
                            "display_time_departure": "12:00",
                            "display_time_arrival": "12:00",
                            "destination_name": "Brixton Underground Station",
                            "destination_via": None,
                            "destination_via_prefix": None,
                            "origin_name": "Green Park Underground Station",
                            "platform": "Northbound",
                            "operator": "TfL",
                            "time_status_class": "time-ontime",
                            "service_url": "/service/tfl/victoria/940GZZLUGPK/940GZZLUBXN",
                            "route_unavailable": False,
                        }
                    ],
                    "next_time_epoch": 0,
                }
            ],
            "total_trains": 1,
            "station_name": "Green Park Underground Station",
            "error": False,
            "timestamp": "12:00:00",
            "line_status": [],
            "from_cache": False,
        }

    calls: list[dict] = []

    def fake_schedule_tfl_service_prefetch(params: dict):
        calls.append(params)

    monkeypatch.setattr('app.routers.pages.get_tfl_board_data', fake_get_tfl_board_data)
    monkeypatch.setattr('app.routers.pages.prefetch_service.schedule_tfl_service_prefetch', fake_schedule_tfl_service_prefetch)

    client = TestClient(app)
    response = client.get('/board/tfl/940GZZLUGPK/departures/refresh')

    assert response.status_code == 200
    assert len(calls) == 1
    assert 'tfl-line-group-title' in response.text
    assert 'Find Another Station' not in response.text


def test_board_refresh_tfl_invalid_view_returns_204_without_fetch(monkeypatch):
    calls: list[tuple[str, str]] = []

    async def fake_get_tfl_board_data(stop_point_id: str, view: str):
        calls.append((stop_point_id, view))
        return {
            "trains": [],
            "line_groups": [],
            "total_trains": 0,
            "station_name": "Brixton Underground Station",
            "error": False,
            "timestamp": "12:00:00",
            "line_status": [],
            "from_cache": False,
        }

    monkeypatch.setattr('app.routers.pages.get_tfl_board_data', fake_get_tfl_board_data)

    client = TestClient(app)
    response = client.get('/board/tfl/940GZZLUBXN/bogus/refresh')

    assert response.status_code == 204
    assert calls == []


def test_board_refresh_tfl_returns_204_on_fetch_error_without_prefetch(monkeypatch):
    calls: list[dict] = []

    async def fake_get_tfl_board_data(stop_point_id: str, view: str):
        raise RuntimeError('boom')

    def fake_schedule_tfl_service_prefetch(params: dict):
        calls.append(params)

    monkeypatch.setattr('app.routers.pages.get_tfl_board_data', fake_get_tfl_board_data)
    monkeypatch.setattr('app.routers.pages.prefetch_service.schedule_tfl_service_prefetch', fake_schedule_tfl_service_prefetch)

    client = TestClient(app)
    response = client.get('/board/tfl/940GZZLUGPK/departures/refresh')

    assert response.status_code == 204
    assert calls == []


def test_homepage_prefetches_common_boards(monkeypatch):
    nr_calls: list[str] = []
    tfl_calls: list[str] = []

    def fake_schedule_nr_board_prefetch(crs: str):
        nr_calls.append(crs)

    def fake_schedule_tfl_board_prefetch(stop_point_id: str):
        tfl_calls.append(stop_point_id)

    monkeypatch.setattr('app.routers.pages.prefetch_service.schedule_nr_board_prefetch', fake_schedule_nr_board_prefetch)
    monkeypatch.setattr('app.routers.pages.prefetch_service.schedule_tfl_board_prefetch', fake_schedule_tfl_board_prefetch)

    client = TestClient(app)
    response = client.get('/')

    assert response.status_code == 200
    assert "LHD" in nr_calls
    assert "940GZZLUWSM" in tfl_calls


def test_tfl_service_page_prefetches_clickable_boards(monkeypatch):
    detail = TflServiceDetail(
        line_id="victoria",
        line_name="Victoria",
        direction="northbound",
        from_stop_id="940GZZLUBXN",
        to_stop_id="940GZZLUGPK",
        origin_name="Brixton Underground Station",
        destination_name="Green Park Underground Station",
        resolution_mode="exact",
        mode_name="tube",
        stops=[
            TflServiceStop(stop_id="940GZZLUBXN", stop_name="Brixton Underground Station"),
            TflServiceStop(stop_id="940GZZLUSTK", stop_name="Stockwell Underground Station"),
            TflServiceStop(stop_id="940GZZLUGPK", stop_name="Green Park Underground Station"),
        ],
    )

    async def fake_get_service_route_detail_cached(**kwargs):
        return detail

    calls: list[str] = []

    def fake_schedule_tfl_board_prefetch(stop_point_id: str):
        calls.append(stop_point_id)

    monkeypatch.setattr('app.routers.pages.tfl_api_service.get_service_route_detail_cached', fake_get_service_route_detail_cached)
    monkeypatch.setattr('app.routers.pages.prefetch_service.schedule_tfl_board_prefetch', fake_schedule_tfl_board_prefetch)

    client = TestClient(app)
    response = client.get('/service/tfl/victoria/940GZZLUBXN/940GZZLUGPK?direction=northbound')

    assert response.status_code == 200
    assert set(calls) == {"940GZZLUBXN", "940GZZLUSTK", "940GZZLUGPK"}
