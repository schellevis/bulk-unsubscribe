import pytest

from app.services.grouping import compute_group_key, extract_domain, normalize_list_id


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("<list.example.com>", "list.example.com"),
        ("  <List.Example.COM>  ", "list.example.com"),
        ("plain-id-no-brackets", "plain-id-no-brackets"),
        ("", ""),
        ("Newsletter <abc@list.example.com>", "abc@list.example.com"),
    ],
)
def test_normalize_list_id(raw, expected):
    assert normalize_list_id(raw) == expected


@pytest.mark.parametrize(
    "addr,expected",
    [
        ("News@Example.com", "example.com"),
        ("a+tag@sub.example.co.uk", "sub.example.co.uk"),
        ("invalid", ""),
        ("", ""),
    ],
)
def test_extract_domain(addr, expected):
    assert extract_domain(addr) == expected


def test_compute_group_key_prefers_list_id():
    assert compute_group_key("Foo <id@list.example>", "news@example.com") == "id@list.example"


def test_compute_group_key_falls_back_to_email_when_list_id_missing():
    assert compute_group_key("", "News@Example.COM") == "news@example.com"


def test_compute_group_key_falls_back_when_list_id_blank():
    assert compute_group_key("   ", "x@y.com") == "x@y.com"
