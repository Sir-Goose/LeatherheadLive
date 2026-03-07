from fastapi.testclient import TestClient

from app.main import app
from app.middleware.cache import cache
from app.models.board import Board
from app.models.tfl import TflBoard
from app.services.rail_api import BoardFetchResult
from app.services.tfl_api import TflBoardFetchResult


def test_get_board_returns_wrapped_payload(monkeypatch):
    async def fake_get_board(crs_code: str, use_cache: bool = True):
        board = Board(
            locationName='Leatherhead',
            crs=crs_code.upper(),
            generatedAt='2026-01-01T12:00:00+00:00',
            trainServices=[],
        )
        return BoardFetchResult(board=board, from_cache=True)

    monkeypatch.setattr('app.routers.boards.rail_api_service.get_board', fake_get_board)

    client = TestClient(app, base_url='http://localhost')
    response = client.get('/api/boards/lhd')

    assert response.status_code == 200
    payload = response.json()
    assert payload['success'] is True
    assert payload['cached'] is True
    assert payload['data']['crs'] == 'LHD'


def test_get_tfl_board_returns_wrapped_payload(monkeypatch):
    async def fake_get_board(stop_point_id: str, use_cache: bool = True):
        board = TflBoard(
            stop_point_id=stop_point_id,
            station_name='Brixton Underground Station',
            generated_at='2026-01-01T12:00:00+00:00',
            pulled_at='2026-01-01T12:00:00+00:00',
            trains=[],
            line_status=[],
        )
        return TflBoardFetchResult(board=board, from_cache=False)

    monkeypatch.setattr('app.routers.boards.tfl_api_service.get_board', fake_get_board)

    client = TestClient(app, base_url='http://localhost')
    response = client.get('/api/boards/tfl/940GZZLUBXN')

    assert response.status_code == 200
    payload = response.json()
    assert payload['success'] is True
    assert payload['cached'] is False
    assert payload['data']['stop_point_id'] == '940GZZLUBXN'


def test_get_tfl_passing_is_not_supported():
    client = TestClient(app, base_url='http://localhost')
    response = client.get('/api/boards/tfl/940GZZLUBXN/passing')

    assert response.status_code == 404


def test_get_tfl_departures_filters_outbound(monkeypatch):
    async def fake_get_board(stop_point_id: str, use_cache: bool = True):
        board = TflBoard(
            stop_point_id=stop_point_id,
            station_name='Brixton Underground Station',
            generated_at='2026-01-01T12:00:00+00:00',
            pulled_at='2026-01-01T12:00:00+00:00',
            trains=[
                {"direction": "outbound", "destinationName": "Victoria", "expectedArrival": "2026-01-01T12:01:00Z"},
                {"direction": "inbound", "destinationName": "Stockwell", "expectedArrival": "2026-01-01T12:02:00Z"},
            ],
            line_status=[],
        )
        return TflBoardFetchResult(board=board, from_cache=False)

    monkeypatch.setattr('app.routers.boards.tfl_api_service.get_board', fake_get_board)

    client = TestClient(app, base_url='http://localhost')
    response = client.get('/api/boards/tfl/940GZZLUBXN/departures')

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]['direction'] == 'outbound'


def test_clear_station_cache_allows_localhost(monkeypatch):
    cleared: list[str] = []

    def fake_clear_cache(crs_code: str):
        cleared.append(crs_code)

    monkeypatch.setattr('app.routers.boards.rail_api_service.clear_cache', fake_clear_cache)

    client = TestClient(app, client=('127.0.0.1', 50000))
    response = client.delete('/api/boards/lhd/cache')

    assert response.status_code == 200
    assert response.json()['success'] is True
    assert cleared == ['lhd']


def test_clear_station_cache_rejects_non_local_forwarded_host(monkeypatch):
    cleared: list[str] = []

    def fake_clear_cache(crs_code: str):
        cleared.append(crs_code)

    monkeypatch.setattr('app.routers.boards.rail_api_service.clear_cache', fake_clear_cache)

    client = TestClient(app, client=('127.0.0.1', 50000))
    response = client.delete(
        '/api/boards/lhd/cache',
        headers={'x-forwarded-for': '203.0.113.10'},
    )

    assert response.status_code == 403
    assert response.json()['detail'] == 'Cache management is restricted to local requests.'
    assert cleared == []


def test_clear_all_cache_allows_localhost():
    cache.set('test-cache-clear', {'ok': True}, ttl=60)

    client = TestClient(app, client=('127.0.0.1', 50000))
    response = client.delete('/api/boards/cache/all')

    assert response.status_code == 200
    assert response.json()['success'] is True
    assert cache.get('test-cache-clear') is None


def test_clear_all_cache_rejects_non_local_forwarded_host():
    cache.set('test-cache-preserve', {'ok': True}, ttl=60)

    client = TestClient(app, client=('127.0.0.1', 50000))
    response = client.delete(
        '/api/boards/cache/all',
        headers={'x-forwarded-for': '198.51.100.20'},
    )

    assert response.status_code == 403
    assert response.json()['detail'] == 'Cache management is restricted to local requests.'
    assert cache.get('test-cache-preserve') == {'ok': True}
    cache.delete('test-cache-preserve')
