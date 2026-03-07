from fastapi.testclient import TestClient

from app.main import app


def test_api_responses_include_security_headers():
    client = TestClient(app)
    response = client.get('/api/health')

    assert response.status_code == 200
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert response.headers['x-frame-options'] == 'DENY'
    assert response.headers['referrer-policy'] == 'strict-origin-when-cross-origin'


def test_html_responses_include_security_headers():
    client = TestClient(app)
    response = client.get('/board/LHD/bogus', follow_redirects=False)

    assert response.status_code == 404
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert response.headers['x-frame-options'] == 'DENY'
    assert response.headers['referrer-policy'] == 'strict-origin-when-cross-origin'


def test_wildcard_cors_does_not_allow_credentials_header():
    client = TestClient(app)
    response = client.get('/api/health', headers={'Origin': 'https://example.com'})

    assert response.status_code == 200
    assert response.headers['access-control-allow-origin'] == '*'
    assert 'access-control-allow-credentials' not in response.headers
