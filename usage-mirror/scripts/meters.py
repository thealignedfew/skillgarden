"""Plan meters for usage-mirror: read each account's usage meter, keep every reading, forecast the run-out.

Source of the live reading: the account usage endpoint that Claude Code's own sign-in is allowed to call,
    GET https://api.anthropic.com/api/oauth/usage
It is undocumented and may change without notice. The endpoint facts (URL, headers, field names) come from the community
tool jens-duttke/usage-monitor-for-claude; they were not guessed.

Rules this file keeps:
  * The access token is read from the account's own .credentials.json, used in one request header and never printed,
    logged, stored, or put in an error message. Only the HTTP status code of a failure is kept.
  * One request per account per refresh at most; results are reused for live_reuse_seconds.
  * Read only. This file never writes to an account home.
  * Readings are kept as percentages and times only, in history_dir/meters_history.jsonl.

Usage (the real endpoint is called only by "read" without --fixture):
    python meters.py read [--fixture FILE]    read, store, print a one-line summary per account
    python meters.py forecast                 print the run-out forecast from the stored readings
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
ANTHROPIC_BETA = "oauth-2025-04-20"
HISTORY_FILE = "meters_history.jsonl"
LIVE_FILE = "meters_live.json"

MESSAGES = {
    "no_credentials": "No sign-in file was found in this account's folder, so no live reading. On macOS the sign-in is "
                      "usually kept in the system keychain, which this tool does not read.",
    "http_401": "The sign-in was refused (expired). Start Claude Code in this account once so it renews the sign-in.",
    "http_403": "The usage endpoint refused this sign-in. Some plans or sign-in kinds cannot read it.",
    "http_404": "The usage endpoint was not found. It is undocumented and may have moved.",
    "http_429": "The usage endpoint asked for slower requests. Try again later.",
    "connection_error": "Could not reach the usage endpoint.",
    "bad_payload": "The usage endpoint answered with something this tool does not recognise.",
}


# ---------- reading ----------
def read_token(home: Path) -> str | None:
    """The account's access token, or None. Never print or store the return value."""
    try:
        creds = json.loads((Path(home) / ".credentials.json").read_text(encoding="utf-8"))
        return (creds.get("claudeAiOauth") or {}).get("accessToken") or None
    except (OSError, ValueError):
        return None


def fetch_raw(home: Path, user_agent: str, timeout: int = 10) -> dict:
    """The unshaped payload, or {"error": code}. The token never leaves this function."""
    token = read_token(home)
    if not token:
        return {"error": "no_credentials"}
    req = urllib.request.Request(USAGE_URL, headers={
        "Authorization": "Bearer " + token,
        "Content-Type": "application/json",
        "User-Agent": user_agent,
        "anthropic-beta": ANTHROPIC_BETA,
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"error": f"http_{e.code}"}
    except Exception:
        return {"error": "connection_error"}
    return raw if isinstance(raw, dict) else {"error": "bad_payload"}


def saved_payload(home: Path) -> tuple[dict | None, dt.datetime | None]:
    """The older route: Claude Code used to keep cachedUsageUtilization in .claude.json. Around Nov 2026 the CLI stopped
    refreshing it, so a saved copy can be old; its fetch time is returned so the page can say so."""
    home = Path(home)
    cands = [home / ".claude.json"]
    if home == Path.home() / ".claude":
        cands.append(Path.home() / ".claude.json")
    for p in cands:
        try:
            cu = json.loads(p.read_text(encoding="utf-8")).get("cachedUsageUtilization")
        except (OSError, ValueError):
            continue
        if isinstance(cu, dict) and isinstance(cu.get("utilization"), dict):
            ms = cu.get("fetchedAtMs")
            t = dt.datetime.fromtimestamp(int(ms) / 1000, dt.timezone.utc) if ms else None
            return cu["utilization"], t
    return None, None


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _window(w) -> dict | None:
    if isinstance(w, dict) and _num(w.get("utilization")) is not None:
        return {"pct": w["utilization"], "resets_at": w.get("resets_at") or ""}
    return None


def normalize(raw: dict) -> dict:
    """Map a raw payload to what the page uses. Tolerant: a missing or renamed field is simply absent, never a crash.

    five_hour, seven_day        the two plan windows
    scoped                      per-model weekly windows, from keys named seven_day_<name> and from limits[] entries
    limits                      the limits[] array (a newer field that carries per-limit severity and per-model weekly
                                limits); its item shape is read defensively, see the whitepaper
    extra_usage                 pay-as-you-go credits: present only on accounts that have the feature; the credit
                                figures are in minor currency units
    """
    out: dict = {"five_hour": _window(raw.get("five_hour")), "seven_day": _window(raw.get("seven_day")),
                 "scoped": [], "limits": [], "extra_usage": None, "spend": None}
    for k, v in raw.items():
        m = re.match(r"^seven_day_(.+)$", k)
        w = _window(v) if m else None
        if w:
            out["scoped"].append({"key": m.group(1), "label": m.group(1).replace("_", " "), **w})
    lim = raw.get("limits")
    if isinstance(lim, list):
        for it in lim:
            if not isinstance(it, dict):
                continue
            pick = lambda *ks: next((it[k] for k in ks if it.get(k) not in (None, "")), None)  # noqa: E731
            pct = pick("utilization", "percent", "pct", "used_percent")
            row = {"kind": str(pick("kind", "type", "id", "key") or ""),
                   "label": str(pick("label", "name", "title", "model", "scope", "display_name") or ""),
                   "pct": _num(pct), "resets_at": str(pick("resets_at", "reset_at") or ""),
                   "severity": str(pick("severity", "status", "level") or ""),
                   "active": it.get("is_active") if isinstance(it.get("is_active"), bool) else None,
                   "keys_seen": sorted(it.keys())[:20]}
            out["limits"].append(row)
    ex = raw.get("extra_usage")
    if isinstance(ex, dict):
        dp = ex.get("decimal_places") if isinstance(ex.get("decimal_places"), int) else 2
        div = 10 ** dp
        used, lim_ = _num(ex.get("used_credits")), _num(ex.get("monthly_limit"))
        out["extra_usage"] = {
            "enabled": ex.get("is_enabled"), "user_disabled": ex.get("user_disabled"),
            "used": None if used is None else used / div, "monthly_limit": None if lim_ is None else lim_ / div,
            "pct": _num(ex.get("utilization")), "currency": ex.get("currency") or "",
            "limit_reached": ex.get("spend_limit_reached"), "disabled_reason": ex.get("disabled_reason") or "",
        }
    sp = raw.get("spend")
    if isinstance(sp, dict):
        out["spend"] = {k: v for k, v in sp.items() if _num(v) is not None or isinstance(v, (str, bool))}
    return out


def read_all(cfg: dict, live: bool = True, fixture: dict | None = None, now: dt.datetime | None = None) -> dict:
    """{label: reading}. reading = {source, fetched_utc, error, message, **normalize()}.
    source: live | saved | fixture | none. Never raises for one account's failure."""
    now = now or dt.datetime.now(dt.timezone.utc)
    hdir = Path(cfg["history_dir"])
    cache_p = hdir / LIVE_FILE
    reuse = float(cfg.get("live_reuse_seconds") or 0)
    if fixture is None and live and reuse:
        try:
            prev = json.loads(cache_p.read_text(encoding="utf-8"))
            age = (now - dt.datetime.fromisoformat(prev["read_utc"])).total_seconds()
            if age < reuse and set(prev["meters"]) >= {a["label"] for a in cfg["accounts"]}:
                return prev["meters"]
        except (OSError, ValueError, KeyError):
            pass
    out: dict = {}
    for a in cfg["accounts"]:
        label, home = a["label"], a["path"]
        rd: dict = {"source": "none", "fetched_utc": "", "error": "", "message": ""}
        if fixture is not None:
            if isinstance(fixture.get(label), dict):
                rd.update(source="fixture", fetched_utc=common.iso_z(now), **normalize(fixture[label]))
            else:
                rd.update(error="no_credentials", message="no fixture for this account")
        else:
            raw = fetch_raw(home, cfg["user_agent"]) if live else {"error": "live_off"}
            if "error" not in raw:
                rd.update(source="live", fetched_utc=common.iso_z(now), **normalize(raw))
            else:
                err = raw["error"]
                saved, st = saved_payload(home)
                if saved:
                    rd.update(source="saved", fetched_utc=common.iso_z(st) if st else "", **normalize(saved))
                    rd["error"], rd["message"] = err, ("Live reading failed (" + err + "); showing the copy Claude Code "
                                                       "saved, which may be old.")
                else:
                    rd["error"] = err
                    rd["message"] = ("Live meters are switched off in the config." if err == "live_off"
                                     else MESSAGES.get(err, "The usage endpoint returned an error: " + err))
        out[label] = rd
    if fixture is not None or live:
        try:
            hdir.mkdir(parents=True, exist_ok=True)
            cache_p.write_text(json.dumps({"read_utc": now.isoformat(timespec="seconds"), "meters": out}), encoding="utf-8")
        except OSError:
            pass
    return out


def load_live_cache(history_dir: Path) -> dict:
    try:
        return json.loads((Path(history_dir) / LIVE_FILE).read_text(encoding="utf-8")).get("meters") or {}
    except (OSError, ValueError):
        return {}


# ---------- history ----------
def load_history(history_dir: Path) -> list[dict]:
    rows = []
    try:
        for line in (Path(history_dir) / HISTORY_FILE).read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if isinstance(r, dict):
                    rows.append(r)
    except OSError:
        pass
    return rows


def append_history(history_dir: Path, meters: dict) -> int:
    """Add each reading that has a fetch time and is not already stored (account plus time). Returns rows added."""
    hdir = Path(history_dir)
    have = {(r.get("account"), r.get("at")) for r in load_history(hdir)}
    new = []
    for label, m in meters.items():
        if not m or m.get("source") not in ("live", "saved", "fixture") or not m.get("fetched_utc"):
            continue
        t = common.parse_ts(m["fetched_utc"])
        if t is None:
            continue
        at = t.astimezone(dt.timezone.utc).isoformat(timespec="seconds")
        if (label, at) in have:
            continue
        have.add((label, at))
        f5, f7 = m.get("five_hour") or {}, m.get("seven_day") or {}
        ex = m.get("extra_usage") or {}
        new.append({"account": label, "at": at, "five_hour": f5.get("pct"), "seven_day": f7.get("pct"),
                    "five_hour_resets": f5.get("resets_at") or "", "seven_day_resets": f7.get("resets_at") or "",
                    "extra_pct": ex.get("pct"), "source": m["source"]})
    if new:
        hdir.mkdir(parents=True, exist_ok=True)
        with open(hdir / HISTORY_FILE, "a", encoding="utf-8") as fh:
            for r in new:
                fh.write(json.dumps(r, separators=(",", ":")) + "\n")
    return len(new)


# ---------- forecast ----------
def forecast(rows: list[dict], window: str, resets_at: str = "", now: dt.datetime | None = None) -> dict:
    """Run-out forecast for one account and one window ("five_hour" or "seven_day").

    Method: the readings of that window since it last dropped (a drop means the window reset and restarts the rate).
    Two linear rates: over the last two readings, and from the newest reading back to the latest reading that is at
    least 60 minutes older. Rate = rise in points / hours between them. Time to 100% = points left / rate.
    Example: 75% to 81% over 50 minutes is 7.2 points an hour; 19 points left is 2.6 hours.
    The forecast says whether that lands before the window's reset time. Fewer than two readings, or a flat or falling
    meter, gives no projection and a reason. It assumes the rate holds; it is not a prediction of your behaviour."""
    now = now or dt.datetime.now(dt.timezone.utc)
    pts = []
    for r in rows:
        t, p = common.parse_ts(r.get("at") or ""), r.get(window)
        if t is not None and isinstance(p, (int, float)):
            pts.append((t, float(p)))
    pts.sort()
    seg: list = []
    for t, p in pts:
        if seg and p < seg[-1][1]:
            seg = []
        seg.append((t, p))
    reset = common.parse_ts(resets_at) if resets_at else None
    out = {"window": window, "n": len(seg), "rates": [], "status": "no_projection", "why": "",
           "reset_at": reset.isoformat(timespec="seconds") if reset else "",
           "last_at": seg[-1][0].isoformat(timespec="seconds") if seg else ""}
    if not seg:
        out["why"] = "no readings yet"
        return out
    if reset and now > reset and (now - reset).total_seconds() > 60:
        out["status"], out["why"] = "stale", "the window has reset since the last reading; take a new reading"
        return out
    if len(seg) < 2:
        out["why"] = "fewer than two readings since the window last reset"
        return out
    b = seg[-1]

    def mk(a, label):
        hrs = (b[0] - a[0]).total_seconds() / 3600
        rate = (b[1] - a[1]) / hrs if hrs > 0 else 0.0
        o = {"label": label, "from_at": a[0].isoformat(timespec="seconds"), "from_pct": a[1],
             "to_at": b[0].isoformat(timespec="seconds"), "to_pct": b[1], "hours": round(hrs, 4),
             "rate_per_hour": round(rate, 3), "left": round(100 - b[1], 3)}
        if rate > 0:
            to_full = (100 - b[1]) / rate
            full_at = b[0] + dt.timedelta(hours=to_full)
            o.update(to_full_hours=round(to_full, 3), full_at=full_at.isoformat(timespec="seconds"),
                     before_reset=(full_at < reset) if reset else None)
        return o
    out["rates"].append(mk(seg[-2], "the last two readings"))
    older = [x for x in seg[:-1] if (b[0] - x[0]).total_seconds() >= 3600 - 1]
    if older:
        out["rates"].append(mk(older[-1], "the last hour or more"))
    rising = [r for r in out["rates"] if r["rate_per_hour"] > 0]
    if not rising:
        out["why"] = "the meter is flat or falling over these readings"
    elif any(r.get("before_reset") is True for r in rising):
        out["status"] = "runs_out_before_reset"
    else:
        out["status"] = "resets_first"
    return out


def forecasts_for(history: list[dict], label: str, meter: dict | None, now: dt.datetime | None = None) -> dict:
    rows = [r for r in history if r.get("account") == label]
    res = {}
    for w in ("five_hour", "seven_day"):
        resets = ((meter or {}).get(w) or {}).get("resets_at") or (rows[-1].get(w + "_resets") if rows else "")
        res[w] = forecast(rows, w, resets, now)
    return res


# ---------- command line ----------
def _summary(label: str, m: dict) -> str:
    f5, f7 = (m.get("five_hour") or {}).get("pct"), (m.get("seven_day") or {}).get("pct")
    bits = [f"{label}: {m['source']}"]
    if f5 is not None:
        bits.append(f"5-hour {f5}%")
    if f7 is not None:
        bits.append(f"7-day {f7}%")
    if m.get("error"):
        bits.append("note: " + m["error"])
    return " ".join(bits)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["read", "forecast"])
    ap.add_argument("--config")
    ap.add_argument("--fixture", help="read synthetic payloads from this JSON file ({label: payload}) instead of calling the endpoint")
    a = ap.parse_args(argv)
    try:
        cfg = common.load_config(a.config)
    except common.ConfigError as e:
        common.die(str(e))
    if a.cmd == "read":
        fx = json.loads(Path(a.fixture).read_text(encoding="utf-8")) if a.fixture else None
        m = read_all(cfg, live=bool(cfg["live_meters"]), fixture=fx)
        n = append_history(cfg["history_dir"], m)
        for label, r in m.items():
            common.say(_summary(label, r))
        common.say(f"history rows added: {n}")
        return 0
    hist = load_history(cfg["history_dir"])
    live = load_live_cache(cfg["history_dir"])
    for acct in cfg["accounts"]:
        fc = forecasts_for(hist, acct["label"], live.get(acct["label"]))
        for w, f in fc.items():
            top = f["rates"][0] if f["rates"] else None
            line = f"{acct['label']} {w}: {f['status']}"
            if top and top["rate_per_hour"] > 0:
                line += f", {top['rate_per_hour']} points an hour, {top['to_full_hours']} h to 100%"
            elif f["why"]:
                line += f" ({f['why']})"
            common.say(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
