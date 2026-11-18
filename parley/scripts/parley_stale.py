#!/usr/bin/env python3
r"""parley_stale.py: the daily recheck list.

Lists every open card (not Completed, not Superseded) whose newest dated line (the newest update, the checked line,
or the opened stamp) is more than N days old, oldest first, for the session and, on a manager's page, per report.

  python parley_stale.py <SEAT>_PARLEY.json [--report <REPORT>_PARLEY.json ...] [--days 3]
  python parley_stale.py <SEAT>_PARLEY.html [--days 3]        (a compiled page: its reports are already inside)

Read only: it prints, writes nothing, and its exit code is always 0. What the session does with the list is the daily
recheck described in SKILL.md: recheck each card against the system of record, write a dated checked line, re-rate
important and urgent, rewrite or close it. A manager sends each report its own stale card ids.
"""
import argparse
import datetime
import io
import json
import re
import sys

DAY = re.compile(r"(20\d\d)-(\d\d)-(\d\d)")
CLOSED = ("done", "completed", "superseded")


def load(path):
    text = io.open(path, encoding="utf-8").read()
    if path.lower().endswith((".html", ".htm")):
        a = "const DATA = "
        i = text.index(a) + len(a)
        j = text.index("</script>", i)
        body = text[i:j].rstrip()
        if body.endswith(";"):
            body = body[:-1]
        return json.loads(body)
    return json.loads(text)


def newest_day(q, today):
    texts = [str(u.get("when") or "") for u in (q.get("updates") or []) if isinstance(u, dict)]
    texts += [str(q.get("checked") or ""), str(q.get("opened") or "")]
    days = []
    for s in texts:
        for y, m, d in DAY.findall(s):
            try:
                day = datetime.date(int(y), int(m), int(d))
            except ValueError:
                continue
            if day <= today + datetime.timedelta(days=1):      # a date in the future is a plan, not a check
                days.append(day)
    return max(days) if days else None


def main():
    ap = argparse.ArgumentParser(description="List a parley's stale open cards (the daily recheck).")
    ap.add_argument("page", help="<SEAT>_PARLEY.json, or a compiled <SEAT>_PARLEY.html")
    ap.add_argument("--report", action="append", default=[], help="a direct report's <SEAT>_PARLEY.json; repeat per report")
    ap.add_argument("--days", type=int, default=3, help="a card is stale when its newest dated line is older than this (default 3)")
    a = ap.parse_args()
    today = datetime.date.today()
    data = load(a.page)
    seats = [(data.get("seat") or "seat", data.get("questions") or [])]
    for r in data.get("reports") or []:
        seats.append((r.get("seat") or "report", r.get("questions") or []))
    for rp in a.report:
        r = load(rp)
        seats.append((r.get("seat") or "report", r.get("questions") or []))
    total = 0
    blocks = []
    for seat, qs in seats:
        rows = []
        for q in qs:
            if str(q.get("status") or q.get("stage") or "open").lower() in CLOSED:
                continue
            nd = newest_day(q, today)
            if nd is None:
                rows.append((99999, "undated", q))
                continue
            age = (today - nd).days
            if age > a.days:
                rows.append((age, nd.isoformat(), q))
        rows.sort(key=lambda x: -x[0])
        total += len(rows)
        blocks.append((seat, len(qs), rows))
    print("STALE %d open card(s) with no dated line in more than %d day(s), as of %s; by seat: %s" % (
        total, a.days, today.isoformat(), ", ".join("%s %d" % (s, len(rows)) for s, _, rows in blocks) or "none"))
    for seat, n, rows in blocks:
        if not rows:
            continue
        print("%s (%d of %d cards):" % (seat, len(rows), n))
        for age, since, q in rows:
            rating = "IU" if q.get("important") and q.get("urgent") else "I" if q.get("important") else "U" if q.get("urgent") else "-"
            stage = str(q.get("stage") or q.get("status") or "open").lower()
            print("  %5s  %-10s  %-2s  %-9s  %-24s  %s" % (
                ("%dd" % age) if age != 99999 else "?", since, rating, stage, str(q.get("id") or "")[:24],
                str(q.get("codename") or q.get("title") or "")[:70]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
