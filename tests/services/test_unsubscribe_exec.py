from aioresponses import aioresponses

from app.services.unsubscribe_exec import execute_one_click


async def test_one_click_success_2xx():
    url = "https://example.com/u/abc"
    with aioresponses() as m:
        m.post(url, status=200, body="OK")
        result = await execute_one_click(url)
    assert result.success is True
    assert result.status_code == 200


async def test_one_click_failure_5xx():
    url = "https://example.com/u/abc"
    with aioresponses() as m:
        m.post(url, status=500, body="boom")
        result = await execute_one_click(url)
    assert result.success is False
    assert result.status_code == 500


async def test_one_click_network_error():
    url = "https://example.com/u/abc"
    with aioresponses() as m:
        m.post(url, exception=ConnectionError("nope"))
        result = await execute_one_click(url)
    assert result.success is False
    assert result.status_code is None
    assert "network error" in result.detail
