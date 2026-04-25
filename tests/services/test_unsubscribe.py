from app.services.unsubscribe import UnsubscribeMethods, parse_unsubscribe_methods


def test_http_only():
    m = parse_unsubscribe_methods(
        list_unsubscribe="<https://example.com/u/abc>",
        list_unsubscribe_post=None,
    )
    assert m == UnsubscribeMethods(
        http_url="https://example.com/u/abc",
        mailto_url=None,
        one_click=False,
    )


def test_mailto_only():
    m = parse_unsubscribe_methods(
        list_unsubscribe="<mailto:unsubscribe@example.com?subject=X>",
        list_unsubscribe_post=None,
    )
    assert m.mailto_url == "mailto:unsubscribe@example.com?subject=X"
    assert m.http_url is None
    assert m.one_click is False


def test_both_with_one_click():
    m = parse_unsubscribe_methods(
        list_unsubscribe="<mailto:u@e.com>, <https://e.com/u/x>",
        list_unsubscribe_post="List-Unsubscribe=One-Click",
    )
    assert m.http_url == "https://e.com/u/x"
    assert m.mailto_url == "mailto:u@e.com"
    assert m.one_click is True


def test_one_click_only_when_http_present():
    m = parse_unsubscribe_methods(
        list_unsubscribe="<mailto:u@e.com>",
        list_unsubscribe_post="List-Unsubscribe=One-Click",
    )
    assert m.one_click is False


def test_empty_inputs():
    m = parse_unsubscribe_methods(list_unsubscribe="", list_unsubscribe_post=None)
    assert m == UnsubscribeMethods(http_url=None, mailto_url=None, one_click=False)


def test_recommended_method():
    one_click = UnsubscribeMethods(
        http_url="https://e.com/u/x", mailto_url=None, one_click=True
    )
    assert one_click.recommended() == "one_click"

    http_only = UnsubscribeMethods(
        http_url="https://e.com/u/x", mailto_url=None, one_click=False
    )
    assert http_only.recommended() == "http"

    mailto_only = UnsubscribeMethods(
        http_url=None, mailto_url="mailto:u@e.com", one_click=False
    )
    assert mailto_only.recommended() == "mailto"

    none = UnsubscribeMethods(http_url=None, mailto_url=None, one_click=False)
    assert none.recommended() is None
