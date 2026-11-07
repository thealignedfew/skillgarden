#!/usr/bin/env python3
r"""parley_tokens.py: token use for one parley activity row, summed across every prompt and comment wake
in a time window.

Reads the session transcript (.jsonl) and adds up the usage of every distinct model call whose timestamp
falls in [since, until). Prints the row's `tokens` string:
    "7.34M cached · 33k fresh · 18k out"            (one prompt in the window)
    "12.6M cached · 61k fresh · 27k out · 3 wakes"  (several prompts or comment wakes)
cached = cache-read input; fresh = uncached input plus cache-write; out = output.

  python parley_tokens.py --session <transcript.jsonl> --since "2025-01-15 04:41 EST" [--until "2025-01-15 04:46 EST"]

Times carry a zone abbreviation (UTC, GMT, EST, EDT, CST, CDT, MST, MDT, PST, PDT); --until defaults to now.
A model call is counted once even when the transcript splits it over several records.
"""
import argparse
import datetime as dt
import io
import json
import sys

ZONES = {"UTC": 0, "GMT": 0, "EDT": -4, "EST": -5, "CDT": -5, "CST": -6, "MDT": -6, "MST": -7, "PDT": -7, "PST": -8}


def parse_et(s):
    s = s.strip()
    zone = s[-3:]
    if zone not in ZONES:
        raise SystemExit("time needs a zone (%s): %r" % (", ".join(sorted(ZONES)), s))
    t = dt.datetime.strptime(s[:-3].strip(), "%Y-%m-%d %H:%M")
    return (t - dt.timedelta(hours=ZONES[zone])).replace(tzinfo=dt.timezone.utc)


def parse_ts(s):
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def human(n):
    if n >= 1e6:
        return "%.2fM" % (n / 1e6)
    if n >= 1e3:
        return "%dk" % round(n / 1e3)
    return str(int(n))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", required=True)
    ap.add_argument("--since", required=True)
    ap.add_argument("--until")
    a = ap.parse_args()
    t0 = parse_et(a.since)
    t1 = parse_et(a.until) if a.until else dt.datetime.now(dt.timezone.utc)
    seen, cached, fresh, out, prompts = set(), 0, 0, 0, 0
    with io.open(a.session, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if '"timestamp"' not in line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            ts = parse_ts(r.get("timestamp") or "")
            if not ts or not (t0 <= ts < t1):
                continue
            if r.get("type") == "user" and not r.get("isMeta") and not r.get("toolUseResult"):
                c = (r.get("message") or {}).get("content")
                if isinstance(c, str) or (isinstance(c, list) and not any(isinstance(x, dict) and x.get("type") == "tool_result" for x in c)):
                    prompts += 1
            m = r.get("message") or {}
            u = m.get("usage")
            if r.get("type") != "assistant" or not u or m.get("model") == "<synthetic>":
                continue
            key = (m.get("id"), r.get("requestId"))
            if key in seen:
                continue
            seen.add(key)
            cached += u.get("cache_read_input_tokens") or 0
            fresh += (u.get("input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0)
            out += u.get("output_tokens") or 0
    if not seen:
        print("no model calls in that window")
        return 1
    s = "%s cached · %s fresh · %s out" % (human(cached), human(fresh), human(out))
    if prompts > 1:
        s += " · %d wakes" % prompts
    print(s)
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
