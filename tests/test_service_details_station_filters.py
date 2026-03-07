from app.models.board import ServiceDetails


def test_service_details_station_stop_filters_only_keep_valid_crs():
    detail = ServiceDetails(
        generatedAt="2026-01-01T12:00:00+00:00",
        pulledAt="2026-01-01T12:00:00+00:00",
        locationName="Leatherhead",
        crs="LHD",
        operator="South Western Railway",
        operatorCode="SW",
        serviceID="svc-1",
        origin=[{"locationName": "Guildford", "crs": "GLD"}],
        destination=[{"locationName": "London Waterloo", "crs": "WAT"}],
        previousCallingPoints=[
            {
                "callingPoint": [
                    {"locationName": "Dorking", "crs": "DKG", "st": "12:00", "et": "On time"},
                    {"locationName": "Windmill Bridge Junction", "crs": "WNDMLBJ", "st": "12:01", "et": "On time"},
                    {"locationName": "Unknown", "crs": "", "st": "12:02", "et": "On time"},
                ]
            }
        ],
        subsequentCallingPoints=[
            {
                "callingPoint": [
                    {"locationName": "Epsom", "crs": "EPS", "st": "12:20", "et": "On time"},
                    {"locationName": "North Pole", "crs": "NPLE813", "st": "12:21", "et": "On time"},
                    {"locationName": "Bad Lower", "crs": "ab1", "st": "12:22", "et": "On time"},
                    {"locationName": "Bad Number", "crs": "123", "st": "12:23", "et": "On time"},
                ]
            }
        ],
    )

    assert [stop.crs for stop in detail.all_previous_stops] == ["DKG", "WNDMLBJ", ""]
    assert [stop.crs for stop in detail.all_subsequent_stops] == ["EPS", "NPLE813", "ab1", "123"]
    assert [stop.crs for stop in detail.all_previous_station_stops] == ["DKG"]
    assert [stop.crs for stop in detail.all_subsequent_station_stops] == ["EPS"]


def test_service_details_station_stop_filters_accept_trimmed_alpha_crs():
    detail = ServiceDetails(
        generatedAt="2026-01-01T12:00:00+00:00",
        pulledAt="2026-01-01T12:00:00+00:00",
        locationName="Leatherhead",
        crs="LHD",
        operator="South Western Railway",
        operatorCode="SW",
        serviceID="svc-2",
        origin=[{"locationName": "Guildford", "crs": "GLD"}],
        destination=[{"locationName": "London Waterloo", "crs": "WAT"}],
        previousCallingPoints=[
            {"callingPoint": [{"locationName": "Dorking", "crs": " dkg ", "st": "12:00", "et": "On time"}]}
        ],
        subsequentCallingPoints=[
            {"callingPoint": [{"locationName": "Epsom", "crs": "eps", "st": "12:20", "et": "On time"}]}
        ],
    )

    assert [stop.locationName for stop in detail.all_previous_station_stops] == ["Dorking"]
    assert [stop.locationName for stop in detail.all_subsequent_station_stops] == ["Epsom"]
