import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import aiohttp


@dataclass
class UnsubscribeResult:
    method: str  # "one_click" | "http" | "mailto"
    success: bool
    status_code: int | None
    detail: str


def _is_public_ip(address: str) -> bool:
    try:
        return ipaddress.ip_address(address).is_global
    except ValueError:
        return False


async def _resolve_host_ips(host: str) -> set[str]:
    infos = await asyncio.to_thread(
        socket.getaddrinfo,
        host,
        443,
        type=socket.SOCK_STREAM,
    )
    return {info[4][0] for info in infos}


async def _validate_unsubscribe_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https":
        raise ValueError("unsubscribe URL must use https")
    if not parsed.hostname:
        raise ValueError("unsubscribe URL must include a hostname")
    if parsed.username or parsed.password:
        raise ValueError("unsubscribe URL must not include credentials")

    host = parsed.hostname
    if _is_public_ip(host):
        return

    try:
        parsed_ip = ipaddress.ip_address(host)
    except ValueError:
        parsed_ip = None

    if parsed_ip is not None:
        raise ValueError("unsubscribe URL host is not a public address")

    try:
        addresses = await _resolve_host_ips(host)
    except socket.gaierror as exc:
        raise ValueError("unsubscribe hostname did not resolve") from exc
    if not addresses:
        raise ValueError("unsubscribe hostname did not resolve")
    if any(not _is_public_ip(address) for address in addresses):
        raise ValueError("unsubscribe hostname resolves to a non-public address")


async def execute_one_click(
    http_url: str, timeout_s: int = 15, max_redirects: int = 5
) -> UnsubscribeResult:
    """RFC 8058 one-click unsubscribe.

    POST to the URL with body `List-Unsubscribe=One-Click` and
    `application/x-www-form-urlencoded` content-type.
    """
    timeout = aiohttp.ClientTimeout(total=timeout_s)
    try:
        next_url = http_url
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for _ in range(max_redirects + 1):
                await _validate_unsubscribe_url(next_url)
                async with session.post(
                    next_url,
                    data={"List-Unsubscribe": "One-Click"},
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    allow_redirects=False,
                ) as resp:
                    if 300 <= resp.status < 400 and resp.headers.get("Location"):
                        next_url = urljoin(str(resp.url), resp.headers["Location"])
                        continue

                    ok = 200 <= resp.status < 400
                    return UnsubscribeResult(
                        method="one_click",
                        success=ok,
                        status_code=resp.status,
                        detail=f"HTTP {resp.status} {resp.reason or ''}".strip(),
                    )

            return UnsubscribeResult(
                method="one_click",
                success=False,
                status_code=None,
                detail="network error: too many redirects",
            )
    except Exception as exc:
        return UnsubscribeResult(
            method="one_click",
            success=False,
            status_code=None,
            detail=f"network error: {exc}",
        )
