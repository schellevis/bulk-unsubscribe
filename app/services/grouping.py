import re

_ANGLE_RE = re.compile(r"<([^>]+)>")


def normalize_list_id(raw: str) -> str:
    if not raw:
        return ""
    raw = raw.strip()
    match = _ANGLE_RE.search(raw)
    inner = match.group(1) if match else raw
    return inner.strip().lower()


def extract_domain(email_addr: str) -> str:
    if not email_addr or "@" not in email_addr:
        return ""
    return email_addr.rsplit("@", 1)[1].strip().lower()


def compute_group_key(list_id_header: str, from_email: str) -> str:
    """Return the canonical group key for a sender.

    Prefers normalized List-ID; falls back to the lowercased From address
    when List-ID is empty or whitespace-only.
    """
    normalized = normalize_list_id(list_id_header)
    if normalized:
        return normalized
    return from_email.strip().lower()
