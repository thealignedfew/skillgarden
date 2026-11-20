"""Outliers and interesting facts for the last N hours (default 12): a short list of plain observations that a
person would want to hear, computed from the collector's database. The page shows the newest run open and older runs
folded.

Each run is {at, window_from, window_to, items: [{title, detail}]} and is appended to history_dir/insights.json
(the last 30 runs are kept). An agent can add its own observations to the run with --add-item TITLE DETAIL; those are
the "interesting facts" a counting script cannot see. Dollar figures are API-equivalent list-price benchmarks, never spend.

Usage:
    python outliers.py                      compute, append, print
    python outliers.py --hours 24
    python outliers.py --print-only         compute and print, do not append
    python outliers.py --add-item "Title" "Detail sentence."
"""
from __future__ import annotations

import argparse
import bisect
import datetime as dt
import json
import sqlite3
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import collect  # noqa: E402

KEEP_RUNS = 30


def plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def money(x: float) -> str:
    return "$" + (f"{x:,.0f}" if x >= 100 else f"{x:,.2f}")


def load_window(cfg: dict, start: dt.datetime, end: dt.datetime) -> tuple[list, dict, list, list]:
    """(calls, turns_by_session, compactions, titles) for [start, end]. calls: dict rows with usd and turn class."""
    rtbl, _, _ = common.load_rates(cfg["rates_file"])
    con = sqlite3.connect(collect.db_path(cfg))
    s, e = common.iso_z(start)[:19], common.iso_z(end)[:19]
    titles: dict = {}
    for sid, src, title in con.execute("select session_id, src, title from titles"):
        titles.setdefault(sid, {})[src] = title
    turns: dict[str, list] = {}
    for sid, ts, origin in con.execute("select session_id, ts, origin from turns where origin != 'command' order by ts"):
        turns.setdefault(sid, []).append((ts, origin))
    tkeys = {k: [t[0] for t in v] for k, v in turns.items()}
    own = collect.owners(con)
    calls = []
    q = "select msg_id, session_id, home, kind, ts, model, input, cw5m, cw1h, cr, output from calls where ts >= ? and ts <= ? order by ts"
    for mid, sid, home, kind, ts, model, inp, cw5, cw1, cr, out in con.execute(q, (s, e)):
        if mid in own:
            home, kind = own[mid][0], own[mid][1]
        rt = common.rate_for(model, rtbl)
        origin = "none"
        tk = tkeys.get(sid)
        if tk:
            i = bisect.bisect_right(tk, ts) - 1
            if i >= 0:
                origin = turns[sid][i][1]
        cw = cw5 + cw1
        cold_extra = 0.0
        if kind == "main" and rt and cw >= collect.COLD_WRITE and cr < cw:
            cold_extra = ((cw1 * rt["write_1h"] + cw5 * rt["write_5m"]) - cw * rt["read"]) / 1e6
        calls.append({"sid": sid, "home": home, "ts": ts, "model": model, "usd": common.price(rt, inp, cw5, cw1, cr, out),
                      "origin": origin, "tokens": inp + cw + cr + out, "cold_extra": cold_extra, "priced": rt is not None})
    comps = con.execute("select session_id, trigger from events where kind='compaction' and ts >= ? and ts <= ?", (s, e)).fetchall()
    con.close()
    return calls, titles, comps, list(own)


def session_name(sid: str, titles: dict) -> str:
    t = titles.get(sid, {})
    return (t.get("custom-title") or t.get("agent-name") or t.get("ai-title") or t.get("summary") or sid[:8])[:60]


def compute(cfg: dict, hours: int = 12, now: dt.datetime | None = None) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    clock = common.Clock(cfg["timezone"])
    start = now - dt.timedelta(hours=hours)
    calls, titles, comps, _ = load_window(cfg, start, now)
    items: list[dict] = []
    lf, lt = clock.local(start).strftime("%Y-%m-%d %H:%M"), clock.local(now).strftime("%Y-%m-%d %H:%M")
    run = {"at": lt, "window_from": lf, "window_to": lt, "hours": hours, "items": items}
    if not calls:
        items.append({"title": f"No responses recorded in the last {hours} hours",
                      "detail": "Either nothing ran, or the collector has not read the newest transcript bytes yet."})
        return run
    total = sum(c["usd"] for c in calls)
    unpriced = sum(1 for c in calls if not c["priced"])
    # compare with the trailing 7 days in windows of the same length
    prior_calls, _, _, _ = load_window(cfg, start - dt.timedelta(days=7), start)
    buckets: dict[int, float] = {}
    for c in prior_calls:
        t = common.parse_ts(c["ts"])
        if t is not None:
            k = int((start - t).total_seconds() // (hours * 3600))
            buckets[k] = buckets.get(k, 0.0) + c["usd"]
    n_win = int(7 * 24 // hours)
    series = [buckets.get(k, 0.0) for k in range(n_win)]
    med = statistics.median(series) if series and any(series) else 0.0
    if med > 0:
        ratio = total / med
        word = (f"{ratio:.1f} times the usual {hours} hours" if ratio >= 1.5 else
                f"about {1 / ratio:.1f} times lower than the usual {hours} hours" if ratio <= 0.67 else
                f"in line with the usual {hours} hours")
        items.append({"title": f"{money(total)} API-equivalent in the last {hours} hours, {word}",
                      "detail": f"The usual is the median of the {n_win} previous windows of the same length, {money(med)}. "
                                "A list-price benchmark, never spend."})
    else:
        items.append({"title": f"{money(total)} API-equivalent in the last {hours} hours",
                      "detail": "There is not enough earlier history to say whether that is usual. A list-price benchmark, never spend."})
    if unpriced:
        items.append({"title": f"{plural(unpriced, 'response', 'responses')} could not be priced",
                      "detail": "Their model is not in the rates file, so the dollar figures leave them out. Add the model to the rates file."})
    # unattended share
    auto = sum(c["usd"] for c in calls if c["origin"] == "scheduled")
    if total > 0 and auto / total >= 0.25:
        items.append({"title": f"{auto / total * 100:.0f}% of the cost answered timed self-prompts",
                      "detail": f"{money(auto)} of {money(total)} came from turns a session prompted itself with (loops, "
                                "ticks, scripted runs), not from typed prompts."})
    # hours
    hb: dict[str, float] = {}
    for c in calls:
        t = common.parse_ts(c["ts"])
        if t is not None:
            k = clock.local(t).strftime("%Y-%m-%d %H:00")
            hb[k] = hb.get(k, 0.0) + c["usd"]
    if len(hb) >= 3:
        top = sorted(hb.items(), key=lambda kv: kv[1], reverse=True)[:2]
        floor = statistics.median(hb.values())
        items.append({"title": "Busiest hours: " + " and ".join(f"{k[11:]} ({money(v)})" for k, v in top),
                      "detail": f"The typical hour in this window cost {money(floor)}. A steady floor with no quiet hour usually "
                                "means something is running unattended."})
    # sessions
    per: dict[str, float] = {}
    for c in calls:
        per[c["sid"]] = per.get(c["sid"], 0.0) + c["usd"]
    top3 = sorted(per.items(), key=lambda kv: kv[1], reverse=True)[:3]
    if total > 0 and top3:
        share = sum(v for _, v in top3) / total * 100
        items.append({"title": "Largest sessions: " + ", ".join(f"{session_name(k, titles)} ({money(v)})" for k, v in top3),
                      "detail": f"Together {share:.0f}% of the window's {money(total)} across {len(per)} sessions."})
    # cache rebuilds
    cold = [c for c in calls if c["cold_extra"] > 0]
    if cold:
        extra = sum(c["cold_extra"] for c in cold)
        items.append({"title": f"{plural(len(cold), 'cold cache rebuild', 'cold cache rebuilds')} cost about {money(extra)} more than warm reads",
                      "detail": "A main response that wrote a large block to the prompt cache and read back less than it wrote. "
                                "Common causes: the cache expired while idle, a compaction, a model or account switch."})
    if comps:
        man = sum(1 for _, trig in comps if trig == "manual")
        items.append({"title": f"{plural(len(comps), 'context compaction', 'context compactions')} ({len(comps) - man} automatic, {man} manual)",
                      "detail": "Each one rewrites the session's context, so the next response rebuilds the cache."})
    big = max(calls, key=lambda c: c["usd"])
    if big["usd"] >= max(1.0, total * 0.05):
        items.append({"title": f"One response cost {money(big['usd'])}",
                      "detail": f"In {session_name(big['sid'], titles)} at {clock.local(common.parse_ts(big['ts'])).strftime('%H:%M')}, "
                                f"model {big['model']}, {big['tokens']:,} tokens counting cache reads."})
    return run


def append_run(history_dir: Path, run: dict) -> int:
    p = Path(history_dir) / "insights.json"
    try:
        runs = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(runs, list):
            runs = []
    except (OSError, ValueError):
        runs = []
    runs.append(run)
    runs = runs[-KEEP_RUNS:]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(runs, indent=1), encoding="utf-8")
    return len(runs)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config")
    ap.add_argument("--hours", type=int, default=12)
    ap.add_argument("--print-only", action="store_true")
    ap.add_argument("--add-item", nargs=2, action="append", metavar=("TITLE", "DETAIL"), default=[])
    a = ap.parse_args(argv)
    try:
        cfg = common.load_config(a.config)
    except common.ConfigError as e:
        common.die(str(e))
    run = compute(cfg, a.hours)
    for t, d in a.add_item:
        run["items"].append({"title": t, "detail": d})
    for it in run["items"]:
        common.say(f"- {it['title']}: {it['detail']}")
    if not a.print_only:
        n = append_run(cfg["history_dir"], run)
        common.say(f"OUTLIERS run saved ({n} runs kept) window {run['window_from']} to {run['window_to']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
