from dataclasses import dataclass

import aiohttp


@dataclass
class UnsubscribeResult:
    method: str  # "one_click" | "http" | "mailto"
    success: bool
    status_code: int | None
    detail: str


async def execute_one_click(http_url: str, timeout_s: int = 15) -> UnsubscribeResult:
    """RFC 8058 one-click unsubscribe.

    POST to the URL with body `List-Unsubscribe=One-Click` and
    `application/x-www-form-urlencoded` content-type.
    """
    timeout = aiohttp.ClientTimeout(total=timeout_s)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                http_url,
                data={"List-Unsubscribe": "One-Click"},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                allow_redirects=True,
            ) as resp:
                ok = 200 <= resp.status < 400
                return UnsubscribeResult(
                    method="one_click",
                    success=ok,
                    status_code=resp.status,
                    detail=f"HTTP {resp.status} {resp.reason or ''}".strip(),
                )
    except Exception as exc:  # noqa: BLE001
        return UnsubscribeResult(
            method="one_click",
            success=False,
            status_code=None,
            detail=f"network error: {exc}",
        )
