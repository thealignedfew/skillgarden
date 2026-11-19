"""Collector for usage-mirror: read Claude Code transcripts from one or more account homes, keep one row per model
response, and write the aggregate the page is built from.

Reads only metadata: timestamps, model, token counts, working-folder name, session id, the session's title records,
whether a user record is a typed prompt, and compaction markers. Message text is never stored.
Incremental by byte offset, so a normal run reads only new bytes. A response found in several files (a resume or an
account move copies a transcript) is counted once.

State lives in history_dir/usage.sqlite; the page data is output_dir/usage_data.json. Nothing is written inside the
skill folder and nothing is written into a Claude account home.

Usage:
    python collect.py                 scan new bytes, then build usage_data.json
    python collect.py --no-build      scan only
    python collect.py --no-scan       build only
"""
from __future__ import annotations

import argparse
import bisect
import datetime as dt
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import meters as meters_mod  # noqa: E402

SCHEMA = """
create table if not exists files(path text primary key, home text, kind text, offset integer, size integer,
  mtime real, max_ts text);
create table if not exists occ(msg_id text, path text, primary key(msg_id, path)) without rowid;
create table if not exists calls(msg_id text primary key, session_id text, home text, kind text, ts text, model text,
  input integer, cw5m integer, cw1h integer, cr integer, output integer, project text, effort text);
create table if not exists turns(uuid text primary key, session_id text, home text, ts text, origin text);
create table if not exists events(uuid text primary key, session_id text, home text, ts text, kind text,
  pre_tokens integer, trigger text);
create table if not exists titles(session_id text, src text, title text, seen real, primary key(session_id, src));
create table if not exists meta(k text primary key, v text);
create index if not exists calls_ts on calls(ts);
create index if not exists turns_ts on turns(ts);
"""

ASSIST = b'"type":"assistant"'
USER = b'"type":"user"'
BOUNDARY = b'"compact_boundary"'
TITLE_KEYS = (b'"type":"custom-title"', b'"type":"agent-name"', b'"type":"summary"', b'"type":"ai-title"')
# turn type of a response: the turn it answered
TC_TYPED, TC_SCHEDULED, TC_OTHERS, TC_NONE = 0, 1, 2, 3
TC_OF = {"typed": TC_TYPED, "scheduled": TC_SCHEDULED, "peer": TC_OTHERS, "task": TC_OTHERS}
ORIGINS = ("typed", "scheduled", "peer", "task")
COLD_WRITE = 20_000   # a main response that wrote this many tokens to the cache and read back less than it wrote


def db_path(cfg: dict) -> Path:
    return Path(cfg["history_dir"]) / "usage.sqlite"


def kind_of(path: Path) -> str:
    parts = [x.lower() for x in path.parts]
    if "workflows" in parts:
        return "workflow"
    if "subagents" in parts:
        return "subagent"
    return "main"


# ---------- scanning ----------
def scan_file(con, path: Path, home: str, kind: str, start: int, now: float) -> tuple[int, int, str]:
    n = 0
    max_ts = ""
    sp = str(path)
    with open(path, "rb") as fh:
        fh.seek(start)
        pos = start
        for line in fh:
            if not line.endswith(b"\n"):
                break  # a partial line still being written; picked up next run
            pos += len(line)
            if ASSIST in line[:400] or (ASSIST in line and b'"usage"' in line):
                if b'"usage"' not in line:
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r.get("type") != "assistant":
                    continue
                m = r.get("message") or {}
                u = m.get("usage") or {}
                mid = m.get("id") or r.get("requestId") or r.get("uuid")
                model = m.get("model") or "?"
                if not mid or not u or model == "<synthetic>":
                    continue
                cc = u.get("cache_creation") or {}
                cw1h = int(cc.get("ephemeral_1h_input_tokens") or 0)
                cw5m = int(cc.get("ephemeral_5m_input_tokens") or 0)
                cwt = int(u.get("cache_creation_input_tokens") or 0)
                if cw1h + cw5m < cwt:
                    cw5m += cwt - cw1h - cw5m
                cwd = r.get("cwd") or ""
                project = re.split(r"[\\/]", cwd.rstrip("\\/"))[-1] if cwd else ""
                ts = r.get("timestamp") or ""
                max_ts = max(max_ts, ts)
                con.execute("insert or ignore into occ values(?,?)", (mid, sp))
                con.execute("insert or ignore into calls values(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (mid, r.get("sessionId") or "", home, kind, ts, model, int(u.get("input_tokens") or 0),
                             cw5m, cw1h, int(u.get("cache_read_input_tokens") or 0), int(u.get("output_tokens") or 0),
                             project, str(r.get("effort") or "")))
                n += 1
            elif kind == "main" and USER in line and not line.startswith(b'{"type":"attachment"'):
                if b'"tool_use_id"' in line or len(line) > 400_000:
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r.get("type") != "user" or r.get("isSidechain") or not r.get("uuid"):
                    continue
                if r.get("isCompactSummary") or r.get("isVisibleInTranscriptOnly"):
                    continue
                c = (r.get("message") or {}).get("content")
                text = c if isinstance(c, str) else next(
                    (b.get("text") or "" for b in c if isinstance(b, dict) and b.get("type") == "text"), None) \
                    if isinstance(c, list) else None
                if text is None:
                    continue
                org = r.get("origin") if isinstance(r.get("origin"), dict) else {}
                to = r.get("turnOrigin")
                # The text is looked at here, in memory, only to tell a slash command from a prompt. It is not stored.
                if (org.get("kind") == "peer" or to == "peer") and org.get("handback"):
                    origin = "task"      # a session's own subagent handing back its result
                elif org.get("kind") == "peer" or to == "peer":
                    origin = "peer"      # a message from another session
                elif org.get("kind") == "task-notification" or to == "task-notification":
                    origin = "task"
                elif to in ("scheduled", "sdk"):
                    origin = "scheduled"  # a timed self-prompt, or a scripted run (claude -p)
                elif r.get("isMeta"):
                    continue
                elif text.lstrip().startswith(("<command-name>", "<local-command", "<command-message>")):
                    origin = "command"
                else:
                    origin = "typed"
                con.execute("insert or ignore into turns values(?,?,?,?,?)",
                            (r["uuid"], r.get("sessionId") or "", home, r.get("timestamp") or "", origin))
                n += 1
            elif kind == "main" and BOUNDARY in line and len(line) < 400_000:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r.get("subtype") != "compact_boundary":
                    continue
                cm = r.get("compactMetadata") or {}
                con.execute("insert or ignore into events values(?,?,?,?,?,?,?)",
                            (r.get("uuid") or "", r.get("sessionId") or "", home, r.get("timestamp") or "", "compaction",
                             int(cm.get("preTokens") or 0), str(cm.get("trigger") or "")))
            elif any(k in line[:200] for k in TITLE_KEYS) and len(line) < 20_000:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                val = r.get("customTitle") or r.get("agentName") or r.get("summary") or r.get("title")
                sid = r.get("sessionId") or ""
                if val and sid:
                    con.execute("insert or replace into titles values(?,?,?,?)", (sid, r.get("type"), str(val)[:160], now))
    return pos, n, max_ts


def scan(cfg: dict, verbose: bool = False, rescan_main: bool = False) -> dict:
    dbp = db_path(cfg)
    dbp.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(dbp)
    con.executescript(SCHEMA)
    if rescan_main:
        con.execute("update files set offset = 0 where kind = 'main'")
        con.commit()
    now = time.time()
    cutoff = now - int(cfg["scan_days"]) * 86400
    st = {"files_seen": 0, "files_read": 0, "records": 0, "bytes": 0, "missing_homes": []}
    t0 = time.time()
    for acct in cfg["accounts"]:
        root = Path(acct["path"]) / "projects"
        if not root.is_dir():
            st["missing_homes"].append(acct["label"])
            continue
        for dirpath, _dirs, files in os.walk(root):
            for fn in files:
                if not fn.endswith(".jsonl"):
                    continue
                p = Path(dirpath) / fn
                try:
                    stt = p.stat()
                except OSError:
                    continue
                st["files_seen"] += 1
                row = con.execute("select offset from files where path=?", (str(p),)).fetchone()
                if row is None and stt.st_mtime < cutoff:
                    continue  # never-seen file older than the scan window
                start = row[0] if row else 0
                if stt.st_size < start:
                    start = 0  # the file was rewritten; read again (responses dedupe on message id)
                if stt.st_size == start:
                    continue
                pos, n, mts = scan_file(con, p, acct["label"], kind_of(p), start, now)
                prev = con.execute("select max_ts from files where path=?", (str(p),)).fetchone()
                if prev and prev[0] and prev[0] > mts:
                    mts = prev[0]
                st["files_read"] += 1
                st["records"] += n
                st["bytes"] += pos - start
                con.execute("insert or replace into files values(?,?,?,?,?,?,?)",
                            (str(p), acct["label"], kind_of(p), pos, stt.st_size, stt.st_mtime, mts))
                if st["files_read"] % 50 == 0:
                    con.commit()
                    if verbose:
                        common.say(f"  {st['files_read']} files, {st['bytes'] / 1e9:.2f} GB, {time.time() - t0:.0f}s")
    con.execute("insert or replace into meta values('last_collect', ?)", (dt.datetime.now(dt.timezone.utc).isoformat(),))
    con.commit()
    con.close()
    st["seconds"] = round(time.time() - t0, 1)
    return st


# ---------- aggregate ----------
def owners(con) -> dict:
    """A response found in several files belongs to the home of the copy that stopped growing first: the original stops
    growing when a session moves. A tie on the last response goes to the file written first."""
    own: dict = {}
    q = ("select o.msg_id, f.home, f.kind, f.max_ts, f.mtime from occ o join files f on f.path = o.path "
         "where o.msg_id in (select msg_id from occ group by msg_id having count(*) > 1)")
    for mid, h, k, mts, mt in con.execute(q):
        rank = (mts or "~", mt if mt is not None else float("inf"))
        if mid not in own or rank < own[mid][2]:
            own[mid] = (h, k, rank)
    return own


def project_of(s: dict) -> str:
    return max(s["projects"], key=s["projects"].get) if s["projects"] else ""


def build(cfg: dict, now_utc: dt.datetime | None = None) -> dict:
    now_utc = now_utc or dt.datetime.now(dt.timezone.utc)
    days = int(cfg["days"])
    clock = common.Clock(cfg["timezone"])
    rtbl, rver, rprob = common.load_rates(cfg["rates_file"])
    since = common.iso_z(now_utc - dt.timedelta(days=days + 1))[:19]
    hours_keep = clock.local(now_utc - dt.timedelta(days=14)).strftime("%Y-%m-%d")
    labels = [a["label"] for a in cfg["accounts"]]
    aidx = {l: i for i, l in enumerate(labels)}
    models: list[str] = []
    projects: list[str] = []

    def idx(lst, v):
        if v not in lst:
            lst.append(v)
        return lst.index(v)

    dbp = db_path(cfg)
    if not dbp.is_file():
        common.die(f"no state database at {dbp}; run a scan first (python collect.py)")
    con = sqlite3.connect(dbp)
    titles: dict = {}
    for sid, src, title in con.execute("select session_id, src, title from titles"):
        titles.setdefault(sid, {})[src] = title
    turns: dict[str, list] = {}
    for sid, ts, origin in con.execute(
            "select session_id, ts, origin from turns where ts >= ? and origin != 'command' order by ts", (since,)):
        turns.setdefault(sid, []).append([ts, origin, 0])
    tkeys = {sid: [t[0] for t in tl] for sid, tl in turns.items()}
    comps = [(sid, ts, trig) for sid, ts, trig in con.execute(
        "select session_id, ts, trigger from events where kind='compaction' and ts >= ? order by ts", (since,))]
    own = owners(con)
    sess: dict[str, dict] = {}
    agg: dict[tuple, list] = {}
    hours: dict[tuple, list] = {}
    timeline: dict[str, list] = {}
    cold_rows = []
    unpriced: dict[str, int] = {}
    q = ("select msg_id, session_id, home, kind, ts, model, input, cw5m, cw1h, cr, output, project from calls "
         "where ts >= ? order by ts")
    for mid, sid, home, kind, ts, model, inp, cw5, cw1, cr, out, project in con.execute(q, (since,)):
        if mid in own:
            home, kind = own[mid][0], own[mid][1]
        if home not in aidx:
            continue  # a home that is no longer in the config
        t = common.parse_ts(ts)
        if t is None:
            continue
        e = clock.local(t)
        day = e.strftime("%Y-%m-%d")
        s = sess.setdefault(sid, {"homes": {}, "first": ts, "last": ts, "projects": {}, "models": {}})
        s["last"] = ts
        if kind == "main":
            timeline.setdefault(sid, []).append((ts, home))
        s["homes"][home] = s["homes"].get(home, 0) + 1
        if project:
            s["projects"][project] = s["projects"].get(project, 0) + 1
        s["models"][model] = s["models"].get(model, 0) + 1
        tr = None
        tk = tkeys.get(sid)
        if tk:
            i = bisect.bisect_right(tk, ts) - 1
            if i >= 0:
                tr = turns[sid][i]
        tc = TC_OF.get(tr[1], TC_NONE) if tr else TC_NONE
        rt = common.rate_for(model, rtbl)
        if rt is None:
            unpriced[model] = unpriced.get(model, 0) + 1
        usd = common.price(rt, inp, cw5, cw1, cr, out)
        a = agg.setdefault((day, sid, aidx[home], idx(models, model), 0 if kind == "main" else 1, tc), [0, 0, 0, 0, 0, 0.0])
        a[0] += 1
        a[1] += inp
        a[2] += cw5 + cw1
        a[3] += cr
        a[4] += out
        a[5] += usd
        if day >= hours_keep:
            h = hours.setdefault((day, e.hour, aidx[home], tc), [0, 0.0])
            h[0] += 1
            h[1] += usd
        if kind == "main" and cw5 + cw1 >= COLD_WRITE and cr < cw5 + cw1 and rt:
            cold_rows.append((day, sid, (cw1 * rt["write_1h"] + cw5 * rt["write_5m"]) / 1e6,
                              ((cw1 * rt["write_1h"] + cw5 * rt["write_5m"]) - (cw1 + cw5) * rt["read"]) / 1e6))
        if tr:
            tr[2] += 1
    con.close()

    sids = sorted(sess, key=lambda k: sess[k]["last"], reverse=True)
    sidx = {k: i for i, k in enumerate(sids)}
    session_rows = []
    for k in sids:
        s = sess[k]
        tt = titles.get(k, {})
        title = (tt.get("custom-title") or tt.get("agent-name") or tt.get("ai-title") or tt.get("summary")
                 or (next(iter(tt.values())) if tt else ""))
        f, l = common.parse_ts(s["first"]), common.parse_ts(s["last"])
        session_rows.append([
            k, title, max(s["homes"], key=s["homes"].get), sorted(s["homes"]), idx(projects, project_of(s)) if project_of(s) else -1,
            clock.local(f).strftime("%Y-%m-%d %H:%M") if f else "", clock.local(l).strftime("%Y-%m-%d %H:%M") if l else "",
            sorted(s["models"], key=s["models"].get, reverse=True)])

    # a turn belongs to the account that answered it: the first main response at or after the turn
    tcount: dict[tuple, list] = {}
    for sid, tl in turns.items():
        tml = timeline.get(sid)
        if sid not in sidx or not tml:
            continue
        for ts, origin, _n in tl:
            t = common.parse_ts(ts)
            if t is None or origin not in ORIGINS:
                continue
            i = bisect.bisect_left(tml, (ts, ""))
            home = tml[min(i, len(tml) - 1)][1]
            c = tcount.setdefault((clock.local(t).strftime("%Y-%m-%d"), sidx[sid], aidx[home]), [0, 0, 0, 0])
            c[ORIGINS.index(origin)] += 1

    rows = [[day, sidx[sid], ai, mi, sub, *a[:5], round(a[5], 4), tc] for (day, sid, ai, mi, sub, tc), a in sorted(agg.items())]
    turn_rows = [[d, s_, a_, *c] for (d, s_, a_), c in sorted(tcount.items())]
    hour_rows = [[d, h, ai, tc, v[0], round(v[1], 4)] for (d, h, ai, tc), v in sorted(hours.items())]
    compactions = []
    for sid, ts, trig in comps:
        t = common.parse_ts(ts)
        if t is not None and sid in sidx:
            te = clock.local(t)
            compactions.append([te.strftime("%Y-%m-%d"), te.hour * 60 + te.minute, sidx[sid], 1 if trig == "manual" else 0])

    # meters: the stored readings, the forecast, and what this machine measured in each meter's own window
    live = meters_mod.load_live_cache(cfg["history_dir"])
    hist_all = meters_mod.load_history(cfg["history_dir"])
    cut9 = common.iso_z(now_utc - dt.timedelta(days=9))[:19]
    meter_out = {}
    for lab in labels:
        m = live.get(lab)
        hist = [r for r in hist_all if r.get("account") == lab and (r.get("at") or "") >= cut9]
        hist.sort(key=lambda r: r.get("at") or "")
        meter_out[lab] = {
            "reading": m,
            "history": [[r.get("at"), r.get("five_hour"), r.get("seven_day"), r.get("source")] for r in hist],
            "forecast": meters_mod.forecasts_for(hist_all, lab, m, now_utc) if (m or hist) else None,
            "measured": measured_in_windows(cfg, lab, m, rtbl) if m else {},
        }
    coll = None
    con = sqlite3.connect(dbp)
    r_ = con.execute("select v from meta where k='last_collect'").fetchone()
    con.close()
    if r_:
        coll = common.parse_ts(r_[0])
    return {
        "schema": 1, "tool_version": common.VERSION,
        "generated_utc": now_utc.isoformat(timespec="seconds"),
        "generated_local": clock.local(now_utc).strftime("%Y-%m-%d %H:%M"),
        "collected_local": clock.local(coll).strftime("%Y-%m-%d %H:%M") if coll else "",
        "timezone": clock.requested, "timezone_effective": clock.effective, "timezone_warning": clock.warning,
        "days": days, "rates_version": rver, "rates_problem": rprob, "unpriced_models": unpriced,
        "accounts": [{"label": a["label"], "color": a["color"]} for a in cfg["accounts"]],
        "models": models, "projects": projects,
        "sessions": session_rows,
        "session_cols": ["id", "title", "account", "accounts", "project", "first", "last", "models"],
        "rows": rows,
        "row_cols": ["day", "session", "account", "model", "sub", "calls", "input", "cache_write", "cache_read", "output",
                     "usd", "turn_class"],
        "turn_class_names": ["typed", "scheduled", "from others", "no turn recorded"],
        "turn_rows": turn_rows, "turn_row_cols": ["day", "session", "account", "typed", "scheduled", "peer", "task"],
        "hours": hour_rows, "hour_cols": ["day", "hour", "account", "turn_class", "calls", "usd"],
        "compactions": compactions, "compaction_cols": ["day", "minute", "session", "manual"],
        "cache_rebuilds": [[d, sidx[s_], round(u, 4), round(x, 4)] for d, s_, u, x in cold_rows if s_ in sidx],
        "cache_rebuild_cols": ["day", "session", "usd_rebuild", "usd_extra"],
        "meters": meter_out,
    }


def measured_in_windows(cfg: dict, label: str, m: dict, rtbl: dict) -> dict:
    """Tokens and API-equivalent dollars this machine saw for one account inside each meter window, ending at the reading."""
    out = {}
    end = common.parse_ts(m.get("fetched_utc") or "")
    if end is None:
        return out
    con = sqlite3.connect(db_path(cfg))
    try:
        for k, span in (("five_hour", dt.timedelta(hours=5)), ("seven_day", dt.timedelta(days=7))):
            w = m.get(k)
            r = common.parse_ts(w["resets_at"]) if w and w.get("resets_at") else None
            if not r:
                continue
            a, b = common.iso_z(r - span)[:19], common.iso_z(min(end, r))[:19]
            tot = [0, 0, 0, 0, 0.0]
            for model, inp, cw5, cw1, cr, o in con.execute(
                    "select model, input, cw5m, cw1h, cr, output from calls where home=? and ts>=? and ts<=?", (label, a, b)):
                tot[0] += 1
                tot[1] += inp + cw5 + cw1
                tot[2] += cr
                tot[3] += o
                tot[4] += common.price(common.rate_for(model, rtbl), inp, cw5, cw1, cr, o)
            out[k] = {"calls": tot[0], "fresh": tot[1], "cache_read": tot[2], "output": tot[3], "usd": round(tot[4], 2),
                      "from": a, "to": b}
    finally:
        con.close()
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config")
    ap.add_argument("--days", type=int)
    ap.add_argument("--scan-days", type=int)
    ap.add_argument("--no-scan", action="store_true")
    ap.add_argument("--no-build", action="store_true")
    ap.add_argument("--rescan-main", action="store_true", help="re-read main transcripts from the start (turns and compactions)")
    ap.add_argument("-v", action="store_true")
    a = ap.parse_args(argv)
    try:
        cfg = common.load_config(a.config)
    except common.ConfigError as e:
        common.die(str(e))
    if a.days:
        cfg["days"] = a.days
    if a.scan_days:
        cfg["scan_days"] = a.scan_days
    if not a.no_scan:
        st = scan(cfg, a.v, a.rescan_main)
        common.say("COLLECT " + json.dumps(st))
        if st["missing_homes"]:
            common.say("NOTE account folders with no projects directory: " + ", ".join(st["missing_homes"]))
    if a.no_build:
        return 0
    data = build(cfg)
    out = Path(cfg["output_dir"])
    out.mkdir(parents=True, exist_ok=True)
    (out / "usage_data.json").write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    common.say(f"BUILD sessions={len(data['sessions'])} rows={len(data['rows'])} bytes={(out / 'usage_data.json').stat().st_size}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
