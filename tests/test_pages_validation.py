import pytest
from fastapi import HTTPException

from app.routers.page_validation import (
    normalize_board_search_view,
    validate_crs,
    validate_tfl_line_id,
    validate_tfl_stop_id,
    validate_view,
)


def test_validate_crs_uppercases_valid_code():
    assert validate_crs('lhd') == 'LHD'


@pytest.mark.parametrize('value', ['', 'lh', 'lhd1', '12A'])
def test_validate_crs_rejects_blank_non_alpha_and_wrong_length(value: str):
    with pytest.raises(HTTPException) as exc_info:
        validate_crs(value)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == 'Invalid CRS code'


def test_validate_tfl_stop_id_strips_whitespace_without_lowercasing():
    assert validate_tfl_stop_id(' 940GZZLUBXN ') == '940GZZLUBXN'


def test_validate_tfl_line_id_strips_and_lowercases():
    assert validate_tfl_line_id(' Victoria ') == 'victoria'


def test_validate_view_allows_passing_only_for_nr():
    assert validate_view('passing', 'nr') == 'passing'

    with pytest.raises(HTTPException) as exc_info:
        validate_view('passing', 'tfl')

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == 'Invalid view'


@pytest.mark.parametrize('provider', ['nr', 'tfl'])
def test_validate_view_rejects_unknown_view(provider: str):
    with pytest.raises(HTTPException) as exc_info:
        validate_view('bogus', provider)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == 'Invalid view'


def test_normalize_board_search_view_defaults_invalid_values_to_departures():
    assert normalize_board_search_view('bogus') == 'departures'
    assert normalize_board_search_view(None) == 'departures'


def test_normalize_board_search_view_preserves_valid_values():
    assert normalize_board_search_view('passing') == 'passing'
