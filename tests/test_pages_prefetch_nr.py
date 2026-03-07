from fastapi.testclient import TestClient

from app.main import app
from app.models.board import ServiceDetails


def test_nr_board_prefetch_runs_for_fresh_board(monkeypatch):
    async def fake_get_nr_board_data(crs: str, view: str):
        return {
            "trains": [
                {
                    "service_id": "abc123",
                    "service_url": "/service/LHD/abc123",
                }
            ],
            "total_trains": 1,
            "station_name": "Leatherhead",
            "error": False,
            "timestamp": "12:00:00",
            "line_status": [],
            "from_cache": False,
        }

    calls: list[tuple[str, str]] = []

    def fake_schedule_nr_service_prefetch(crs: str, service_id: str):
        calls.append((crs, service_id))

    monkeypatch.setattr('app.routers.pages.get_nr_board_data', fake_get_nr_board_data)
    monkeypatch.setattr('app.routers.pages.prefetch_service.schedule_nr_service_prefetch', fake_schedule_nr_service_prefetch)

    client = TestClient(app)
    response = client.get('/board/nr/LHD/departures')

    assert response.status_code == 200
    assert calls == [("LHD", "abc123")]


def test_nr_board_prefetch_runs_when_board_from_cache(monkeypatch):
    async def fake_get_nr_board_data(crs: str, view: str):
        return {
            "trains": [
                {
                    "service_id": "abc123",
                    "service_url": "/service/LHD/abc123",
                }
            ],
            "total_trains": 1,
            "station_name": "Leatherhead",
            "error": False,
            "timestamp": "12:00:00",
            "line_status": [],
            "from_cache": True,
        }

    calls: list[tuple[str, str]] = []

    def fake_schedule_nr_service_prefetch(crs: str, service_id: str):
        calls.append((crs, service_id))

    monkeypatch.setattr('app.routers.pages.get_nr_board_data', fake_get_nr_board_data)
    monkeypatch.setattr('app.routers.pages.prefetch_service.schedule_nr_service_prefetch', fake_schedule_nr_service_prefetch)

    client = TestClient(app)
    response = client.get('/board/nr/LHD/departures')

    assert response.status_code == 200
    assert calls == [("LHD", "abc123")]


def test_nr_board_content_prefetch_runs_for_fresh_board(monkeypatch):
    async def fake_get_nr_board_data(crs: str, view: str):
        return {
            "trains": [
                {
                    "service_id": "abc123",
                    "service_url": "/service/LHD/abc123",
                }
            ],
            "total_trains": 1,
            "station_name": "Leatherhead",
            "error": False,
            "timestamp": "12:00:00",
            "line_status": [],
            "from_cache": False,
        }

    calls: list[tuple[str, str]] = []

    def fake_schedule_nr_service_prefetch(crs: str, service_id: str):
        calls.append((crs, service_id))

    monkeypatch.setattr('app.routers.pages.get_nr_board_data', fake_get_nr_board_data)
    monkeypatch.setattr('app.routers.pages.prefetch_service.schedule_nr_service_prefetch', fake_schedule_nr_service_prefetch)

    client = TestClient(app)
    response = client.get('/board/nr/LHD/departures/content')

    assert response.status_code == 200
    assert calls == [("LHD", "abc123")]


def test_nr_board_refresh_prefetch_runs_for_fresh_board(monkeypatch):
    async def fake_get_nr_board_data(crs: str, view: str):
        return {
            "trains": [
                {
                    "service_id": "abc123",
                    "service_url": "/service/LHD/abc123",
                }
            ],
            "total_trains": 1,
            "station_name": "Leatherhead",
            "error": False,
            "timestamp": "12:00:00",
            "line_status": [],
            "from_cache": False,
        }

    calls: list[tuple[str, str]] = []

    def fake_schedule_nr_service_prefetch(crs: str, service_id: str):
        calls.append((crs, service_id))

    monkeypatch.setattr('app.routers.pages.get_nr_board_data', fake_get_nr_board_data)
    monkeypatch.setattr('app.routers.pages.prefetch_service.schedule_nr_service_prefetch', fake_schedule_nr_service_prefetch)

    client = TestClient(app)
    response = client.get('/board/nr/LHD/departures/refresh')

    assert response.status_code == 200
    assert calls == [("LHD", "abc123")]


def test_nr_service_page_prefetches_clickable_boards(monkeypatch):
    service = ServiceDetails(
        generatedAt="2026-01-01T12:00:00+00:00",
        pulledAt="2026-01-01T12:00:00+00:00",
        locationName="Leatherhead",
        crs="LHD",
        operator="South Western Railway",
        operatorCode="SW",
        serviceID="service-1",
        origin=[{"locationName": "Dorking", "crs": "DKG"}],
        destination=[{"locationName": "London Waterloo", "crs": "WAT"}],
        previousCallingPoints=[{"callingPoint": [{"locationName": "Dorking", "crs": "DKG", "st": "12:00", "et": "On time"}]}],
        subsequentCallingPoints=[{"callingPoint": [{"locationName": "Epsom", "crs": "EPS", "st": "12:20", "et": "On time"}]}],
    )

    async def fake_get_service_route_cached(crs: str, service_id: str, use_cache: bool = True):
        return service

    calls: list[str] = []

    def fake_schedule_nr_board_prefetch(crs: str):
        calls.append(crs)

    monkeypatch.setattr(
        'app.routers.pages.rail_api_service.get_service_route_cached',
        fake_get_service_route_cached,
    )
    monkeypatch.setattr('app.routers.pages.prefetch_service.schedule_nr_board_prefetch', fake_schedule_nr_board_prefetch)

    client = TestClient(app)
    response = client.get('/service/LHD/service-1')

    assert response.status_code == 200
    assert set(calls) == {"LHD", "DKG", "EPS"}


def test_nr_service_page_excludes_non_station_timing_points(monkeypatch):
    service = ServiceDetails(
        generatedAt="2026-01-01T12:00:00+00:00",
        pulledAt="2026-01-01T12:00:00+00:00",
        locationName="Selhurst",
        crs="SRS",
        operator="Southern",
        operatorCode="SN",
        serviceID="service-2",
        origin=[{"locationName": "East Croydon", "crs": "ECR"}],
        destination=[{"locationName": "Watford Junction", "crs": "WFJ"}],
        previousCallingPoints=[
            {"callingPoint": [{"locationName": "Windmill Bridge Junction", "crs": "WNDMLBJ", "st": "12:11", "et": "On time"}]}
        ],
        subsequentCallingPoints=[
            {
                "callingPoint": [
                    {"locationName": "Balham", "crs": "BAL", "st": "12:29", "et": "On time"},
                    {"locationName": "North Pole Junction", "crs": "NPLE813", "st": "12:57", "et": "On time"},
                    {"locationName": "Willesden Junction", "crs": "WIJ", "st": "13:02", "et": "On time"},
                ]
            }
        ],
    )

    async def fake_get_service_route_cached(crs: str, service_id: str, use_cache: bool = True):
        return service

    calls: list[str] = []

    def fake_schedule_nr_board_prefetch(crs: str):
        calls.append(crs)

    monkeypatch.setattr(
        'app.routers.pages.rail_api_service.get_service_route_cached',
        fake_get_service_route_cached,
    )
    monkeypatch.setattr('app.routers.pages.prefetch_service.schedule_nr_board_prefetch', fake_schedule_nr_board_prefetch)

    client = TestClient(app)
    response = client.get('/service/SRS/service-2')

    assert response.status_code == 200
    assert "Balham" in response.text
    assert "Willesden Junction" in response.text
    assert "Windmill Bridge Junction" not in response.text
    assert "North Pole Junction" not in response.text
    assert response.text.count('class="timeline-stop"') == 3
    assert set(calls) == {"SRS", "BAL", "WIJ"}


def test_nr_service_page_uses_timetable_fallback(monkeypatch):
    service = ServiceDetails(
        generatedAt="2026-01-01T12:00:00+00:00",
        pulledAt="2026-01-01T12:00:00+00:00",
        locationName="Leatherhead",
        crs="LHD",
        operator="South Western Railway",
        operatorCode="SW",
        serviceID="service-1",
        std="21:10",
        etd="On time",
        origin=[{"locationName": "Guildford", "crs": "GLD"}],
        destination=[{"locationName": "London Waterloo", "crs": "WAT"}],
        previousCallingPoints=[{"callingPoint": [{"locationName": "Guildford", "crs": "GLD", "st": "20:50", "et": "On time"}]}],
        subsequentCallingPoints=[{"callingPoint": [{"locationName": "London Waterloo", "crs": "WAT", "st": "21:40", "et": "On time"}]}],
    )

    async def fake_get_service_route_cached(crs: str, service_id: str, use_cache: bool = True):
        return None

    async def fake_get_service_route_from_timetable(crs: str, service_id: str):
        assert crs == "LHD"
        assert service_id == "service-1"
        return service

    monkeypatch.setattr(
        'app.routers.pages.rail_api_service.get_service_route_cached',
        fake_get_service_route_cached,
    )
    monkeypatch.setattr(
        'app.routers.pages.rail_api_service.get_service_route_from_timetable',
        fake_get_service_route_from_timetable,
    )

    client = TestClient(app)
    response = client.get('/service/LHD/service-1')

    assert response.status_code == 200
    assert "Leatherhead" in response.text
    assert "Guildford" in response.text
    assert "London Waterloo" in response.text


def test_nr_service_refresh_uses_timetable_fallback(monkeypatch):
    service = ServiceDetails(
        generatedAt="2026-01-01T12:00:00+00:00",
        pulledAt="2026-01-01T12:00:00+00:00",
        locationName="Leatherhead",
        crs="LHD",
        operator="South Western Railway",
        operatorCode="SW",
        serviceID="service-1",
        std="21:10",
        etd="On time",
        origin=[{"locationName": "Guildford", "crs": "GLD"}],
        destination=[{"locationName": "London Waterloo", "crs": "WAT"}],
        previousCallingPoints=[{"callingPoint": [{"locationName": "Guildford", "crs": "GLD", "st": "20:50", "et": "On time"}]}],
        subsequentCallingPoints=[{"callingPoint": [{"locationName": "London Waterloo", "crs": "WAT", "st": "21:40", "et": "On time"}]}],
    )

    async def fake_get_service_route(crs: str, service_id: str, use_cache: bool = True):
        return None

    async def fake_get_service_route_from_timetable(crs: str, service_id: str):
        return service

    monkeypatch.setattr(
        'app.routers.pages.rail_api_service.get_service_route',
        fake_get_service_route,
    )
    monkeypatch.setattr(
        'app.routers.pages.rail_api_service.get_service_route_from_timetable',
        fake_get_service_route_from_timetable,
    )

    client = TestClient(app)
    response = client.get('/service/LHD/service-1/refresh')

    assert response.status_code == 200
    assert "Leatherhead" in response.text


def test_nr_service_refresh_excludes_non_station_timing_points(monkeypatch):
    service = ServiceDetails(
        generatedAt="2026-01-01T12:00:00+00:00",
        pulledAt="2026-01-01T12:00:00+00:00",
        locationName="Selhurst",
        crs="SRS",
        operator="Southern",
        operatorCode="SN",
        serviceID="service-3",
        origin=[{"locationName": "East Croydon", "crs": "ECR"}],
        destination=[{"locationName": "Watford Junction", "crs": "WFJ"}],
        previousCallingPoints=[
            {"callingPoint": [{"locationName": "Streatham Junction", "crs": "STRENJN", "st": "12:26", "et": "On time"}]}
        ],
        subsequentCallingPoints=[
            {
                "callingPoint": [
                    {"locationName": "Clapham Junction", "crs": "CLJ", "st": "12:34", "et": "On time"},
                    {"locationName": "Willesden N7", "crs": "WLSDNN7", "st": "13:03", "et": "On time"},
                    {"locationName": "Wembley Central", "crs": "WMB", "st": "13:09", "et": "On time"},
                ]
            }
        ],
    )

    async def fake_get_service_route(crs: str, service_id: str, use_cache: bool = True):
        return service

    monkeypatch.setattr(
        'app.routers.pages.rail_api_service.get_service_route',
        fake_get_service_route,
    )

    client = TestClient(app)
    response = client.get('/service/SRS/service-3/refresh')

    assert response.status_code == 200
    assert "Clapham Junction" in response.text
    assert "Wembley Central" in response.text
    assert "Streatham Junction" not in response.text
    assert "Willesden N7" not in response.text
    assert response.text.count('class="timeline-stop"') == 3


def test_nr_service_refresh_prefetch_excludes_non_station_timing_points(monkeypatch):
    service = ServiceDetails(
        generatedAt="2026-01-01T12:00:00+00:00",
        pulledAt="2026-01-01T12:00:00+00:00",
        locationName="Selhurst",
        crs="SRS",
        operator="Southern",
        operatorCode="SN",
        serviceID="service-4",
        origin=[{"locationName": "East Croydon", "crs": "ECR"}],
        destination=[{"locationName": "Watford Junction", "crs": "WFJ"}],
        previousCallingPoints=[
            {"callingPoint": [{"locationName": "Windmill Bridge Junction", "crs": "WNDMLBJ", "st": "12:11", "et": "On time"}]}
        ],
        subsequentCallingPoints=[
            {
                "callingPoint": [
                    {"locationName": "Balham", "crs": "BAL", "st": "12:29", "et": "On time"},
                    {"locationName": "North Pole Junction", "crs": "NPLE813", "st": "12:57", "et": "On time"},
                    {"locationName": "Willesden Junction", "crs": "WIJ", "st": "13:02", "et": "On time"},
                ]
            }
        ],
    )

    async def fake_get_service_route(crs: str, service_id: str, use_cache: bool = True):
        return service

    calls: list[str] = []

    def fake_schedule_nr_board_prefetch(crs: str):
        calls.append(crs)

    monkeypatch.setattr(
        'app.routers.pages.rail_api_service.get_service_route',
        fake_get_service_route,
    )
    monkeypatch.setattr('app.routers.pages.prefetch_service.schedule_nr_board_prefetch', fake_schedule_nr_board_prefetch)

    client = TestClient(app)
    response = client.get('/service/SRS/service-4/refresh')

    assert response.status_code == 200
    assert set(calls) == {"SRS", "BAL", "WIJ"}
