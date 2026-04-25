import re
from dataclasses import dataclass
from typing import Literal

_BRACKET_RE = re.compile(r"<([^>]+)>")


@dataclass(frozen=True)
class UnsubscribeMethods:
    http_url: str | None
    mailto_url: str | None
    one_click: bool

    def recommended(self) -> Literal["one_click", "http", "mailto"] | None:
        if self.one_click and self.http_url:
            return "one_click"
        if self.http_url:
            return "http"
        if self.mailto_url:
            return "mailto"
        return None


def parse_unsubscribe_methods(
    list_unsubscribe: str | None,
    list_unsubscribe_post: str | None,
) -> UnsubscribeMethods:
    http_url: str | None = None
    mailto_url: str | None = None

    for raw in _BRACKET_RE.findall(list_unsubscribe or ""):
        candidate = raw.strip()
        lower = candidate.lower()
        if lower.startswith(("https://", "http://")) and http_url is None:
            http_url = candidate
        elif lower.startswith("mailto:") and mailto_url is None:
            mailto_url = candidate

    one_click = False
    if list_unsubscribe_post and http_url:
        if "list-unsubscribe=one-click" in list_unsubscribe_post.lower():
            one_click = True

    return UnsubscribeMethods(http_url=http_url, mailto_url=mailto_url, one_click=one_click)
