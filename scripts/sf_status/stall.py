"""Stall detection: an unchanged pane for the limit is reported exactly once per stall. Never restarts."""
import hashlib


def pane_hash(text: str) -> str:
    lines = [ln for ln in text.splitlines() if "Tip:" not in ln and "update failed" not in ln]
    return hashlib.md5(("\n".join(lines) + ("\n" if lines else "")).encode()).hexdigest()[:12]


def check(prev: dict | None, pane_hash: str, now: float, limit_s: int) -> tuple[dict, bool]:
    """Returns (new marker entry, report now)."""
    prev = dict(prev or {})
    if prev.get("hash") != pane_hash or prev.get("gone"):
        return {**prev, "hash": pane_hash, "since": now, "reported": False, "gone": False}, False
    since = float(prev.get("since", now))
    if now - since >= limit_s and not prev.get("reported"):
        return {**prev, "reported": True}, True
    return prev, False
