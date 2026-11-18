#!/usr/bin/env python3
"""time_stamp.py: one timestamp line from the machine clock, in the local time zone by default.

Use it whenever a page, note or log line needs a time, and use the SAME returned value for every
stamp in one response, so the stamps agree. A hand-typed time drifts from the clock.

    python time_stamp.py                         ->  2025-01-15 09:00 EST
    python time_stamp.py --seconds               ->  2025-01-15 09:00:12 EST
    python time_stamp.py --date                  ->  2025-01-15
    python time_stamp.py --zone Europe/Berlin    ->  2025-01-15 15:00 CET

The zone label is the zone's own short name when it has one (EST, CET); otherwise the offset from
UTC (UTC+05:30). An unknown zone name is an error (exit 2). It never falls back to UTC, because a
wrong-zone stamp looks as authoritative as a right one. Named zones need the zoneinfo database:
built into most Linux and macOS systems; on Windows run  python -m pip install tzdata.
"""
import argparse
import datetime as dt
import sys


def now_in(zone=None):
    if not zone:
        return dt.datetime.now().astimezone()
    from zoneinfo import ZoneInfo
    return dt.datetime.now(ZoneInfo(zone))


def label(t):
    name = t.tzname() or ""
    if name.isalpha() and len(name) <= 5:
        return name
    off = t.utcoffset() or dt.timedelta(0)
    mins = int(off.total_seconds() // 60)
    sign = "+" if mins >= 0 else "-"
    mins = abs(mins)
    return "UTC%s%02d:%02d" % (sign, mins // 60, mins % 60)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Print the current time as one stamp line.")
    ap.add_argument("--zone", default=None, help="an IANA zone name such as Europe/Berlin; default is the machine's local zone")
    ap.add_argument("--seconds", action="store_true", help="include seconds")
    ap.add_argument("--date", action="store_true", help="print the date only")
    a = ap.parse_args(argv)
    try:
        t = now_in(a.zone)
    except Exception as e:
        sys.stderr.write("REFUSING TO STAMP: could not use zone %r (%s). Check the name, or install the tzdata "
                         "package on Windows. No fallback to UTC is made.\n" % (a.zone, e))
        return 2
    if a.date:
        print(t.strftime("%Y-%m-%d"))
    elif a.seconds:
        print("%s %s" % (t.strftime("%Y-%m-%d %H:%M:%S"), label(t)))
    else:
        print("%s %s" % (t.strftime("%Y-%m-%d %H:%M"), label(t)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
