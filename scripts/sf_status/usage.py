"""Usage and model report from Claude Code transcripts, read-only.

Costs are a list-price equivalent, not an invoice. Every response counts once (message.id);
the day boundary is UTC. Unreadable lines are counted, never raised.
"""
import json
from datetime import date, datetime, timezone
from pathlib import Path

from .projects import Project, project_for_path

DEFAULT_ROOT = Path("~/.claude/projects")
TOP_CONTEXT = 5
OTHER = "other"
EMPTY_PRICES = {"as_of": None, "note": "", "models": {}}


def load_prices(path: Path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dict(EMPTY_PRICES, models={})
    if not isinstance(data, dict) or not isinstance(data.get("models"), dict):
        return dict(EMPTY_PRICES, models={})
    return data


def _num(v) -> int:
    return v if isinstance(v, int) and not isinstance(v, bool) else 0


def _blank() -> dict:
    return {"responses": 0, "input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "usd": 0.0}


def _add(total: dict, model: str, u: dict, prices: dict) -> None:
    inp, out = _num(u.get("input_tokens")), _num(u.get("output_tokens"))
    cache_read = _num(u.get("cache_read_input_tokens"))
    cc = u.get("cache_creation") if isinstance(u.get("cache_creation"), dict) else {}
    h1 = _num(cc.get("ephemeral_1h_input_tokens"))
    if "cache_creation_input_tokens" in u:
        cache_write = _num(u.get("cache_creation_input_tokens"))
    else:
        cache_write = _num(cc.get("ephemeral_5m_input_tokens")) + h1
    m5 = _num(cc.get("ephemeral_5m_input_tokens")) if "ephemeral_5m_input_tokens" in cc else max(cache_write - h1, 0)
    total["responses"] += 1
    total["input"] += inp
    total["output"] += out
    total["cache_read"] += cache_read
    total["cache_write"] += cache_write
    p = prices.get(model)
    if total["usd"] is None or not isinstance(p, dict):
        total["usd"] = None
        return
    try:
        i, o, c = float(p["input"]), float(p["output"]), float(p["cache_read"])
    except (KeyError, TypeError, ValueError):
        total["usd"] = None
        return
    total["usd"] += (inp * i + out * o + cache_read * c + m5 * i * 1.25 + h1 * i * 2.0) / 1e6


def _responses(path: Path, day: date, counter: dict):
    """(model, usage, cwd) per response of the day, each message.id once."""
    seen: set = set()
    try:
        fh = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return
    with fh:
        for raw in fh:
            if '"usage"' not in raw:
                continue
            try:
                d = json.loads(raw)
            except ValueError:
                counter["bad"] += 1
                continue
            msg = d.get("message") if isinstance(d, dict) else None
            if not isinstance(msg, dict):
                continue
            model, u = msg.get("model"), msg.get("usage")
            if not isinstance(model, str) or not model or model == "<synthetic>" or not isinstance(u, dict):
                continue
            ts = d.get("timestamp")
            try:
                t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                if t.tzinfo is None:
                    t = t.replace(tzinfo=timezone.utc)
                if t.astimezone(timezone.utc).date() != day:
                    continue
            except ValueError:
                continue
            mid = msg.get("id") or d.get("requestId") or d.get("uuid")
            if isinstance(mid, str) and mid:  # a response without any id is always counted
                if mid in seen:
                    continue
                seen.add(mid)
            yield model, u, d.get("cwd")


def _rounded(d: dict) -> dict:
    out = dict(d)
    if out.get("usd") is not None:
        out["usd"] = round(out["usd"], 4)
    return out


def summarize(transcripts_root: Path, day: date, prices: dict, projects: list[Project]) -> dict:
    table = prices.get("models") if isinstance(prices, dict) and isinstance(prices.get("models"), dict) else {}
    by_model: dict[str, dict] = {}
    by_project: dict[str, dict] = {}
    helpers: dict[str, int] = {}
    sessions: list[dict] = []
    counter = {"bad": 0}
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp()
    root = Path(transcripts_root).expanduser()
    try:
        files = sorted(root.glob("**/*.jsonl"))
    except OSError:
        files = []
    for f in files:
        try:
            if f.stat().st_mtime < start:
                continue
        except OSError:
            continue
        helper = "subagents" in f.parts
        mine = _blank()
        project = OTHER
        for model, u, cwd in _responses(f, day, counter):
            name = OTHER
            if isinstance(cwd, str) and cwd:
                name = project_for_path(projects, Path(cwd)) or OTHER
            if not helper:
                project = name
            _add(by_model.setdefault(model, _blank()), model, u, table)
            _add(by_project.setdefault(name, _blank()), model, u, table)
            if helper:
                helpers[model] = helpers.get(model, 0) + 1
            else:
                _add(mine, model, u, table)
        if not helper and mine["responses"]:
            sessions.append({"session": f.stem[:8], "project": project, "responses": mine["responses"],
                             "cache_read": mine["cache_read"]})
    sessions.sort(key=lambda s: (-s["cache_read"], s["session"]))
    return {"day": day.isoformat(),
            "by_model": {k: _rounded(v) for k, v in sorted(by_model.items())},
            "by_project": {k: _rounded(v) for k, v in sorted(by_project.items())},
            "helper_share": {k: round(helpers.get(k, 0) / v["responses"], 3) for k, v in sorted(by_model.items())},
            "top_context": sessions[:TOP_CONTEXT],
            "unknown_lines": counter["bad"]}


def format_text(result: dict) -> str:
    lines = [f"Usage {result.get('day')} (list-price equivalent, not an invoice)"]
    for title, key in (("By model", "by_model"), ("By project", "by_project")):
        lines.append(f"{title}:")
        for k, v in (result.get(key) or {}).items():
            usd = "unknown" if v.get("usd") is None else f"${v['usd']:.2f}"
            lines.append(f"  {k}: {v['responses']} responses, in {v['input']}, out {v['output']}, "
                         f"cache read {v['cache_read']}, cache write {v['cache_write']}, {usd}")
    lines.append("Helper share: " + ", ".join(f"{k} {v:.0%}" for k, v in (result.get("helper_share") or {}).items()))
    lines.append("Top context (main sessions by cache read):")
    for t in result.get("top_context") or []:
        lines.append(f"  {t['session']} {t['project']}: {t['responses']} responses, cache read {t['cache_read']}")
    lines.append(f"Unreadable lines: {result.get('unknown_lines')}")
    return "\n".join(lines)
