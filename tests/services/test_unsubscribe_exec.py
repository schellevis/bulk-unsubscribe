from aioresponses import aioresponses

from app.services.unsubscribe_exec import execute_one_click


async def _public_resolver(_host: str) -> set[str]:
    return {"93.184.216.34"}


async def test_one_click_success_2xx(monkeypatch):
    url = "https://example.com/u/abc"
    monkeypatch.setattr(
        "app.services.unsubscribe_exec._resolve_host_ips", _public_resolver
    )
    with aioresponses() as m:
        m.post(url, status=200, body="OK")
        result = await execute_one_click(url)
    assert result.success is True
    assert result.status_code == 200


async def test_one_click_failure_5xx(monkeypatch):
    url = "https://example.com/u/abc"
    monkeypatch.setattr(
        "app.services.unsubscribe_exec._resolve_host_ips", _public_resolver
    )
    with aioresponses() as m:
        m.post(url, status=500, body="boom")
        result = await execute_one_click(url)
    assert result.success is False
    assert result.status_code == 500


async def test_one_click_network_error(monkeypatch):
    url = "https://example.com/u/abc"
    monkeypatch.setattr(
        "app.services.unsubscribe_exec._resolve_host_ips", _public_resolver
    )
    with aioresponses() as m:
        m.post(url, exception=ConnectionError("nope"))
        result = await execute_one_click(url)
    assert result.success is False
    assert result.status_code is None
    assert "network error" in result.detail


async def test_one_click_rejects_plain_http():
    result = await execute_one_click("http://example.com/u/abc")

    assert result.success is False
    assert result.status_code is None
    assert "must use https" in result.detail


async def test_one_click_rejects_private_ip_host():
    result = await execute_one_click("https://127.0.0.1/u/abc")

    assert result.success is False
    assert result.status_code is None
    assert "not a public address" in result.detail


async def test_one_click_rejects_private_dns_result(monkeypatch):
    async def private_resolver(_host: str) -> set[str]:
        return {"10.0.0.5"}

    monkeypatch.setattr(
        "app.services.unsubscribe_exec._resolve_host_ips", private_resolver
    )

    result = await execute_one_click("https://example.com/u/abc")

    assert result.success is False
    assert result.status_code is None
    assert "non-public address" in result.detail


async def test_one_click_validates_redirect_target(monkeypatch):
    url = "https://example.com/u/abc"
    monkeypatch.setattr(
        "app.services.unsubscribe_exec._resolve_host_ips", _public_resolver
    )
    with aioresponses() as m:
        m.post(url, status=302, headers={"Location": "https://127.0.0.1/private"})
        result = await execute_one_click(url)

    assert result.success is False
    assert result.status_code is None
    assert "not a public address" in result.detail
