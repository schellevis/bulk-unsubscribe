from fastapi.testclient import TestClient

from app.main import app


def test_cross_origin_post_is_rejected(db_session):
    with TestClient(app) as client:
        response = client.post(
            "/accounts/1/scan",
            headers={"Origin": "https://evil.example"},
        )

    assert response.status_code == 403
    assert response.text == "cross-origin request rejected"


def test_same_origin_post_is_allowed(db_session):
    with TestClient(app) as client:
        response = client.post(
            "/accounts/1/scan",
            headers={"Origin": "http://testserver"},
        )

    assert response.status_code == 404


def test_cross_origin_referer_is_rejected_when_origin_missing(db_session):
    with TestClient(app) as client:
        response = client.post(
            "/accounts/1/scan",
            headers={"Referer": "https://evil.example/page"},
        )

    assert response.status_code == 403


def test_non_browser_post_without_origin_or_referer_is_allowed(db_session):
    with TestClient(app) as client:
        response = client.post("/accounts/1/scan")

    assert response.status_code == 404
