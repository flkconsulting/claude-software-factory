"""Deterministic STATUS.md and status.html from a collected State.

render_* are pure (state, now). Free text is stripped of control characters, shortened in
tables and escaped in HTML. The supervisor triggers travel in State.triggers; write() fills
that field from supervisor/triggers.json when the file exists. attention() is the part of
"Needs you" a watcher compares: stable fields only, written as attention.json.
"""
import dataclasses
import html
import json
import os
import re
import shlex
from datetime import datetime
from pathlib import Path

from . import events
from .collect import State

CELL_MAX = 200
TEXT_MAX = 1000
UNKNOWN = "unknown"
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[@-Z\\-_]")
CTRL = re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]")
WS = re.compile(r"\s+")
USAGE_NOTE = "list-price equivalent, not an invoice"

CSS = ("body{font-family:sans-serif;margin:2em;max-width:70em}table{border-collapse:collapse}"
       "td,th{border:1px solid #999;padding:.2em .5em;text-align:left;vertical-align:top}"
       "pre{background:#eee;padding:.4em}h2{margin-top:1.5em}")


def _clean(value) -> str:
    """Printable text: ANSI and control characters removed, newlines kept."""
    if value is None:
        return ""
    text = ANSI.sub("", str(value)).replace("\r\n", "\n").replace("\r", "\n")
    return CTRL.sub("", text)


def _line(value, limit: int = TEXT_MAX) -> str:
    text = WS.sub(" ", _clean(value)).strip()
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _cell(value) -> str:
    return _line(value, CELL_MAX)


def _get(d, key, default=UNKNOWN):
    if isinstance(d, dict):
        v = d.get(key)
        if v not in (None, ""):
            return v
    return default


def _percent(value) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:.0%}"
    return UNKNOWN


def _dicts(items) -> list[dict]:
    return [i for i in items if isinstance(i, dict)] if isinstance(items, list) else []


# Block model: ("p", text) ("li", text) ("code", text) ("table", headers, rows)
def _needs_you(state: State) -> list:
    b: list = []
    qs = _dicts(state.questions)
    b.append(("h3", f"Open questions ({len(qs)})"))
    if not qs:
        b.append(("p", "None."))
    for q in qs:
        raw_project, raw_id = q.get("project"), q.get("id")
        project, qid = _line(raw_project if raw_project is not None else "?", 80), _line(raw_id if raw_id is not None else "?", 80)
        b.append(("li", f"{project} / {qid}: {_line(_get(q, 'question'))}"))
        b.append(("p", f"Background: {_line(_get(q, 'background'))}"))
        b.append(("p", f"Recommendation: {_line(_get(q, 'recommendation'))}"))
        if events.valid_id(raw_project) and events.valid_id(raw_id):
            b.append(("code", f'sf-status answer --project {shlex.quote(raw_project)} --id {shlex.quote(raw_id)} "..."'))
        else:
            b.append(("p", "id invalid, no answer line."))
    ts = _dicts(state.tasks)
    b.append(("h3", f"Open tasks ({len(ts)})"))
    if not ts:
        b.append(("p", "None."))
    for t in ts:
        b.append(("li", f"{_line(_get(t, 'project', '?'), 80)} / {_line(_get(t, 'id', '?'), 80)}: "
                        f"{_line(_get(t, 'title'))} (why: {_line(_get(t, 'why'))})"))
    ns = _dicts(state.notices)
    b.append(("h3", f"Notices ({len(ns)})"))
    if not ns:
        b.append(("p", "None."))
    for n in ns:
        b.append(("li", f"[{_line(_get(n, 'level'), 20)}] {_line(_get(n, 'title'))}: {_line(_get(n, 'text'))}"))
        raw_project, raw_time, raw_title = n.get("project"), n.get("time"), n.get("title")
        if events.valid_id(raw_project) and isinstance(raw_time, str) and raw_time and isinstance(raw_title, str) and raw_title:
            b.append(("code", f"sf-status dismiss --project {shlex.quote(raw_project)} "
                              f"--time {shlex.quote(raw_time)} --title {shlex.quote(raw_title)}"))
    return b


def _strands(state: State) -> list:
    rows = []
    for key in sorted(state.strands):
        v = state.strands[key]
        rows.append([_cell(v.project), _cell(v.strand), _cell(v.state), _cell(v.since),
                     _cell(v.branch or ""), _cell(v.text)])
    if not rows:
        return [("p", "None.")]
    return [("table", ["project", "strand", "state", "since", "branch", "last message"], rows)]


def _local(state: State) -> list:
    rows = [[_cell(_get(e, "project")), _cell(_get(e, "id")), _cell(_get(e, "strand")),
             _cell(_get(e, "step")), _cell(_get(e, "branch")), _cell(str(e.get("commit") or "")[:12]),
             _cell(_get(e, "since")), _cell(e.get("last_result") or "")]
            for e in _dicts(state.local)]
    if not rows:
        return [("p", "None.")]
    return [("table", ["project", "id", "strand", "step", "branch", "commit", "waiting since", "last result"],
             rows)]


def _tickets(state: State) -> list:
    b: list = []
    for o in _dicts(state.tickets):
        b.append(("h3", _line(_get(o, "project", "?"), 80)))
        bugs = _dicts(o.get("bugs"))
        b.append(("h3", f"Open bugs ({len(bugs)})"))
        b.append(("table", ["nr", "rank", "state", "version", "summary"],
                  [[_cell(_get(x, k, "")) for k in ("nr", "rank", "state", "version", "summary")]
                   for x in bugs]) if bugs else ("p", "None."))
        nxt = _dicts(o.get("next"))
        b.append(("h3", "Next versions"))
        b.append(("table", ["version", "line", "state", "tickets"],
                  [[_cell(_get(x, "version", "")), _cell(_get(x, "line", "")), _cell(_get(x, "state", "")),
                    _cell(", ".join(str(n) for n in x["tickets"]) if isinstance(x.get("tickets"), list) else "")]
                   for x in nxt]) if nxt else ("p", "None."))
        new = _dicts(o.get("new"))
        b.append(("h3", "New, not assessed"))
        b.append(("table", ["nr", "kind", "rank", "summary"],
                  [[_cell(_get(x, k, "")) for k in ("nr", "kind", "rank", "summary")] for x in new])
                 if new else ("p", "None."))
    return b


def _stalls(state: State) -> list:
    out = [("li", f"{_line(k, 160)}: {_line(v.state, 40)} since {_line(v.since, 40)}")
           for k, v in sorted(state.strands.items()) if v.stalled]
    return out or [("p", "None.")]


def _supervisor(state: State) -> list:
    b: list = []
    runs = _dicts(state.runs)[:5]
    b.append(("h3", "Last runs"))
    if not runs:
        b.append(("p", "No runs."))
    else:
        rows = []
        for r in runs:
            trig = r.get("triggers")
            trig_s = ", ".join(_line(t, 60) for t in trig) if isinstance(trig, list) else UNKNOWN
            rows.append([_cell(_get(r, "start")), _cell(_get(r, "end")), _cell(_get(r, "result")), _cell(trig_s)])
        b.append(("table", ["start", "end", "result", "triggers"], rows))
    trig = state.triggers if isinstance(state.triggers, dict) else None
    for label in ("open", "parked"):
        b.append(("h3", f"{label.capitalize()} triggers"))
        items = _dicts(trig.get(label)) if trig else []
        if not items:
            b.append(("p", "None."))
        for t in items:
            b.append(("li", f"{_line(_get(t, 'id'), 120)} (since {_line(_get(t, 'since'), 40)}, "
                            f"tries {_line(_get(t, 'tries'), 10)})"))
    return b


def _usage(usage: dict) -> list:
    b: list = [("p", f"Day: {_line(_get(usage, 'day'), 40)}. Costs are a {USAGE_NOTE}.")]

    def mapping(title: str, key: str) -> None:
        data = usage.get(key)
        rows = []
        if isinstance(data, dict):
            for k in sorted(data, key=str):
                v = data[k]
                if isinstance(v, dict):
                    v = ", ".join(f"{n} {_get(v, n)}" for n in sorted(v, key=str))
                elif isinstance(v, list):
                    v = None
                rows.append([_cell(k), _cell(_get({"v": v}, "v"))])
        b.append(("h3", title))
        b.append(("table", ["name", "value"], rows) if rows else ("p", UNKNOWN))

    mapping("By model", "by_model")
    mapping("By project", "by_project")
    share = usage.get("helper_share")
    if isinstance(share, dict) and share:
        share_s = ", ".join(f"{k} {_percent(share[k])}" for k in sorted(share, key=str))
    else:
        share_s = UNKNOWN
    b.append(("p", f"Helper share: {_line(share_s, 300)}"))
    b.append(("p", f"Unknown lines: {_line(_get(usage, 'unknown_lines'), 60)}"))
    top = _dicts(usage.get("top_context"))
    b.append(("h3", "Top context (main sessions by cache read)"))
    if top:
        b.append(("table", ["session", "project", "responses", "cache read"],
                  [[_cell(_get(t, k)) for k in ("session", "project", "responses", "cache_read")] for t in top]))
    else:
        b.append(("p", UNKNOWN))
    return b


def _recent(state: State) -> list:
    rows = [[_cell(_get(e, "time")), _cell(_get(e, "project")), _cell(_get(e, "strand")),
             _cell(_get(e, "kind")), _cell(e.get("text") or e.get("title") or e.get("question") or e.get("step") or "")]
            for e in _dicts(state.recent)]
    if not rows:
        return [("p", "None.")]
    return [("table", ["time", "project", "strand", "kind", "text"], rows)]


def _sections(state: State) -> list[tuple[str, list]]:
    secs = [("Needs you", _needs_you(state)), ("Waiting for local step", _local(state))]
    if _dicts(state.tickets):
        secs.append(("Tickets", _tickets(state)))
    secs += [("Strands", _strands(state)), ("Stalls", _stalls(state)), ("Supervisor", _supervisor(state))]
    if isinstance(state.usage, dict):
        secs.append(("Usage", _usage(state.usage)))
    secs.append(("Recent events", _recent(state)))
    return secs


def _stamp(now: datetime) -> str:
    return now.strftime("%Y-%m-%dT%H:%M:%SZ")


def _md(text: str) -> str:
    """Defuse Markdown/HTML in free text: no raw HTML, links or code spans."""
    for ch, rep in (("\\", "\\\\"), ("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"), ("`", "\\`"), ("[", "\\["), ("]", "\\]")):
        text = text.replace(ch, rep)
    return text


def _fence(text: str) -> str:
    """A backtick fence longer than any backtick run in text, so a title with ``` cannot close it."""
    longest = max((len(m) for m in re.findall(r"`+", text)), default=0)
    return "`" * max(3, longest + 1)


def render_markdown(state: State, now: datetime) -> str:
    out = ["# Status", "", f"Generated: {_stamp(now)}", ""]
    for title, blocks in _sections(state):
        out += [f"## {title}", ""]
        for blk in blocks:
            kind = blk[0]
            if kind == "h3":
                out += [f"### {_md(blk[1])}", ""]
            elif kind == "p":
                out += [_md(blk[1]), ""]
            elif kind == "li":
                out.append(f"- {_md(blk[1])}")
            elif kind == "code":
                fence = _fence(blk[1])
                out += [fence, blk[1], fence, ""]
            elif kind == "table":
                out.append("| " + " | ".join(blk[1]) + " |")
                out.append("|" + " --- |" * len(blk[1]))
                for row in blk[2]:
                    out.append("| " + " | ".join(_md(c).replace("|", "\\|") for c in row) + " |")
                out.append("")
        if out[-1] != "":
            out.append("")
    return "\n".join(out).rstrip("\n") + "\n"


def render_html(state: State, now: datetime) -> str:
    e = html.escape
    out = ["<!DOCTYPE html>", '<html lang="en"><head><meta charset="utf-8">', "<title>Status</title>",
           f"<style>{CSS}</style></head><body>", "<h1>Status</h1>", f"<p>Generated: {e(_stamp(now))}</p>"]
    for title, blocks in _sections(state):
        out.append(f"<h2>{e(title)}</h2>")
        in_list = False
        for blk in blocks:
            if blk[0] != "li" and in_list:
                out.append("</ul>")
                in_list = False
            kind = blk[0]
            if kind == "li":
                if not in_list:
                    out.append("<ul>")
                    in_list = True
                out.append(f"<li>{e(blk[1])}</li>")
            elif kind == "h3":
                out.append(f"<h3>{e(blk[1])}</h3>")
            elif kind == "p":
                out.append(f"<p>{e(blk[1])}</p>")
            elif kind == "code":
                out.append(f"<pre>{e(blk[1])}</pre>")
            elif kind == "table":
                out.append("<table><tr>" + "".join(f"<th>{e(h)}</th>" for h in blk[1]) + "</tr>")
                for row in blk[2]:
                    out.append("<tr>" + "".join(f"<td>{e(c)}</td>" for c in row) + "</tr>")
                out.append("</table>")
        if in_list:
            out.append("</ul>")
    out.append("</body></html>")
    return "\n".join(out) + "\n"


ATTENTION_LEVELS = ("approval", "decision", "warning")
ATTENTION_STATES = ("waiting", "blocked")


def _pick(d: dict, keys: tuple[str, ...]) -> dict:
    return {k: d[k] for k in keys if k in d}


def attention(state: State) -> dict:
    """What needs the human, without fields that change while nothing new happens."""
    out = {
        "questions": [_pick(q, ("project", "id", "question")) for q in _dicts(state.questions)],
        "tasks": [_pick(t, ("project", "id", "title")) for t in _dicts(state.tasks)],
        "notices": [_pick(n, ("project", "strand", "time", "level", "title")) for n in _dicts(state.notices)
                    if n.get("level") in ATTENTION_LEVELS],
        "strands": [{"project": v.project, "strand": v.strand, "state": v.state}
                    for _, v in sorted(state.strands.items()) if v.state in ATTENTION_STATES],
    }
    critical = [{"project": o.get("project"), "nr": b.get("nr")}
                for o in _dicts(state.tickets) for b in _dicts(o.get("bugs")) if b.get("rank") == "critical"]
    if critical:
        out["tickets"] = critical
    return out


def _atomic(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _load_triggers(state_dir: Path) -> dict | None:
    try:
        data = json.loads((state_dir / "supervisor" / "triggers.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def write(state_dir, state: State, now: datetime) -> None:
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    full = dataclasses.replace(state, triggers=_load_triggers(state_dir))
    _atomic(state_dir / "STATUS.md", render_markdown(full, now))
    _atomic(state_dir / "status.html", render_html(full, now))
    _atomic(state_dir / "attention.json", json.dumps(attention(state), ensure_ascii=False, indent=1) + "\n")
