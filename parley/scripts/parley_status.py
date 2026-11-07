#!/usr/bin/env python3
r"""parley_status.py: the live facts for a parley's status strip, read from disk.

  python parley_status.py --session <transcript.jsonl> [--json <SEAT>_PARLEY.json] [--measure-dir <folder>]

Prints the session's context capacity and whether Remote Control is on, and with --json writes them into
the fragment's `capacity` and `remote_control` fields.

- capacity: the last request's context fill. It needs a helper module named parley_measure (parley_measure.py)
  that exposes measure(transcript_path) -> (fill_percent, _, _), where fill_percent is a number from 0 to 100 or
  None; that module is an optional companion you write yourself and is not shipped here.
  Put its folder on --measure-dir or in the PARLEY_MEASURE_DIR environment variable. Without it capacity
  prints "unavailable" and the fragment's capacity field is left alone.
- remote_control: ON when this session's live record in <config dir>/sessions/*.json carries a
  bridgeSessionId, OFF when the record has none, "unknown" when no live record names this session.
  <config dir> is CLAUDE_CONFIG_DIR, or ~/.claude.
"""
import argparse
import glob
import io
import json
import os
import sys

KW = os.environ.get("PARLEY_MEASURE_DIR", "")


def remote_control(session_id):
    home = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    for f in glob.glob(os.path.join(home, "sessions", "*.json")):
        try:
            d = json.load(io.open(f, encoding="utf-8"))
        except Exception:
            continue
        if d.get("sessionId") == session_id:
            return "ON" if d.get("bridgeSessionId") else "OFF"
    return "unknown"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", required=True)
    ap.add_argument("--json")
    ap.add_argument("--measure-dir", default=KW, help="folder holding the optional parley_measure module")
    a = ap.parse_args()
    if a.measure_dir:
        sys.path.insert(0, a.measure_dir)
    cap = None
    try:
        import parley_measure as kc
        fill, _, _ = kc.measure(a.session)
        cap = "%d%%" % round(fill) if fill is not None else None
    except Exception:
        cap = None
    sid = os.path.basename(a.session)[:-6] if a.session.endswith(".jsonl") else os.path.basename(a.session)
    rc = remote_control(sid)
    print("capacity %s · remote control %s" % (cap or "unavailable", rc))
    if a.json:
        d = json.load(io.open(a.json, encoding="utf-8"))
        if cap:
            d["capacity"] = cap
        d["remote_control"] = rc
        tmp = a.json + ".tmp"
        json.dump(d, io.open(tmp, "w", encoding="utf-8", newline="\n"), indent=2, ensure_ascii=False)
        os.replace(tmp, a.json)
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
