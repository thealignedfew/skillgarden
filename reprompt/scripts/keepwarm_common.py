#!/usr/bin/env python3
r"""keepwarm_common.py: the shared state and measurement module for the reprompt skill.

keepwarm_tick.py uses it, and so can any per-prompt hook you write yourself. Two readers
computing the context fill two ways would disagree, so both call measure() here.

STATE FOLDER. One JSON file per session, <state folder>/<session-id>.json, keyed on the
transcript file name without .jsonl (or on the session's name when no transcript is given).
The folder is the environment variable REPROMPT_STATE_DIR, default ~/.reprompt. Keys this
module owns: last_fill, last_compactions, scan_offset (bytes already counted for compactions,
so a hook never re-reads a long transcript), prep_at_compactions. Keys owned by
keepwarm_tick.py (seat, watch, period, loop, armed_loop, armed, last_tick, plan, hybrid_k and
the rest) are preserved untouched: every write is read, merge, atomic replace.

Two keys are read but never written by these scripts: blocked_ticks (an integer, consecutive
ticks that were blocked on the user) and abandoned (a bool, the user has stopped answering).
An optional alerting hook of your own can write them; without one they stay absent and the
blocked-seat upgrade and the ignored-seat drop never happen.

THE FILL is input_tokens + cache_creation_input_tokens + cache_read_input_tokens of the last
real assistant turn in the transcript, over the model's context window. The transcript does not
say how large the window is, so the window is the environment variable REPROMPT_CONTEXT_WINDOW
(tokens, an integer), default 200000. Set it if your model has a larger window.
Compactions are the transcript records marked isCompactSummary.

After a compaction: if the newest compaction record is later in the transcript than the last
measured assistant request, that request measured the context BEFORE the compaction, so the
fill is unavailable until the next request.

Never raises to its callers: a hook that throws noises up every prompt. Failures return None,
and None is rendered as unavailable, never as zero.

  python keepwarm_common.py --session "<transcript>"       # print the reading
"""
import io
import json
import os
import sys

STATE_DIR = os.path.expanduser(os.environ.get("REPROMPT_STATE_DIR") or os.path.join("~", ".reprompt"))
DEFAULT_WINDOW = 200000
WINDOW_EXCEEDED = False         # set by measure() when the last turn held more tokens than the window
TAIL_BYTES = 1_048_576          # the last assistant usage is always near the end
COMPACT_PREP_PCT = 50.0         # context fill at which compaction prep is due
COMPACT_FORM_PCT = 92.0         # context fill at which the compaction watch is due


def session_key(transcript_path):
    b = os.path.basename(transcript_path or "")
    return b[:-6] if b.endswith(".jsonl") else (b or None)


def state_path(key):
    return os.path.join(STATE_DIR, "%s.json" % key)


def load_state(key):
    try:
        return json.loads(io.open(state_path(key), encoding="utf-8").read())
    except Exception:
        return {}


def save_state(key, updates):
    """Read, merge, atomically replace. Keys the caller does not name are kept as they were."""
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        cur = load_state(key)
        cur.update(updates)
        tmp = state_path(key) + ".tmp.%d" % os.getpid()
        with io.open(tmp, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(cur))
        os.replace(tmp, state_path(key))
        return cur
    except Exception:
        return None


def context_window():
    try:
        w = int(os.environ.get("REPROMPT_CONTEXT_WINDOW") or DEFAULT_WINDOW)
        return w if w > 0 else DEFAULT_WINDOW
    except ValueError:
        return DEFAULT_WINDOW


def _last_turn_usage(path):
    """(model, fill_tokens) for the last real assistant turn, read from the file tail."""
    try:
        size = os.path.getsize(path)
        with io.open(path, "rb") as fh:
            fh.seek(max(0, size - TAIL_BYTES))
            chunk = fh.read().decode("utf-8", "replace")
    except Exception:
        return None, None
    for line in reversed(chunk.splitlines()):
        if '"isCompactSummary"' in line or '"compact_boundary"' in line:
            try:
                row = json.loads(line)
            except Exception:
                row = {}
            if row.get("isCompactSummary") or row.get("subtype") == "compact_boundary":
                return None, None       # the newest request predates the newest compaction
        if '"assistant"' not in line or '"usage"' not in line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        m = row.get("message") or {}
        u = m.get("usage")
        if row.get("type") != "assistant" or not u or m.get("model") == "<synthetic>":
            continue
        parts = [u.get("input_tokens"), u.get("cache_creation_input_tokens"),
                 u.get("cache_read_input_tokens")]
        vals = [p for p in parts if isinstance(p, (int, float))]
        return m.get("model"), (sum(vals) if vals else None)
    return None, None


def _count_compactions(path, key, state):
    """Incremental: count isCompactSummary records past the stored offset, complete lines only."""
    offset = state.get("scan_offset") or 0
    count = state.get("last_compactions") or 0
    if not offset:
        count = 0
    try:
        size = os.path.getsize(path)
        if offset > size:                       # replaced or truncated: rebuild
            offset, count = 0, 0
        with io.open(path, "rb") as fh:
            fh.seek(offset)
            data = fh.read()
    except Exception:
        return None, offset
    end = data.rfind(b"\n")
    if end < 0:
        return count, offset
    for line in data[:end].split(b"\n"):
        if b"isCompactSummary" not in line:
            continue
        try:
            if json.loads(line).get("isCompactSummary"):
                count += 1
        except Exception:
            pass
    return count, offset + end + 1


def measure(transcript_path, state=None, persist=True):
    """Return (fill_pct or None, compactions or None, model). Updates the shared state file."""
    key = session_key(transcript_path)
    if not key or not transcript_path or not os.path.isfile(transcript_path):
        return None, None, None
    state = load_state(key) if state is None else state
    model, tokens = _last_turn_usage(transcript_path)
    window = context_window()
    fill = (100.0 * tokens / window) if tokens is not None else None
    global WINDOW_EXCEEDED
    WINDOW_EXCEEDED = False
    if fill is not None and fill > 100.0:
        # More tokens than the window allows: the window setting is too small for this model.
        # A reading above 100 percent would raise false compaction alerts, so report none.
        WINDOW_EXCEEDED = True
        fill = None
    compactions, new_offset = _count_compactions(transcript_path, key, state)
    upd = {"scan_offset": new_offset}
    if compactions is not None:
        upd["last_compactions"] = compactions
    if fill is not None:
        upd["last_fill"] = round(fill, 1)
    if persist:
        save_state(key, upd)
    return fill, compactions, model


def prep_due(key, fill, compactions):
    """COMPACT_PREP_PCT or more, and no compaction prompt registered at this compaction count."""
    if fill is None or compactions is None or fill < COMPACT_PREP_PCT:
        return False
    return load_state(key).get("prep_at_compactions") != compactions


def form_due(key, fill, compactions):
    """COMPACT_FORM_PCT or more, not already in #CompactionForm, and not already shifted at this count."""
    if fill is None or compactions is None or fill < COMPACT_FORM_PCT:
        return False
    st = load_state(key)
    return st.get("form") != "#CompactionForm" and st.get("form_at_compactions") != compactions


# Lost loops. Session-only crons live in the session's memory, so a window reload or a close
# and reopen can drop the chain while the state file still says it is armed.
LOST_GRACE_MIN = 10
HERE = os.path.dirname(os.path.abspath(__file__))


def lost_loop(key, now=None, state=None):
    """{loop, last, late} when this session's armed loop is more than half a period plus
    LOST_GRACE_MIN past its next tick, else None. A loop ended with keepwarm_tick.py --stop
    is never lost."""
    import datetime as dt
    st = load_state(key) if state is None else state
    loop = st["form"] if "form" in st else st.get("armed_loop")   # form is None after a shift back to nothing
    stamp = st.get("last_tick") or st.get("armed")              # an arming whose first cron never fired
    if not loop or st.get("stopped") or not stamp:
        return None
    try:
        last = dt.datetime.fromisoformat(stamp)
    except Exception:
        return None
    try:
        period = 10 if loop == "#CompactionForm" else int(st.get("period") or 50)
        current = now or (dt.datetime.now(last.tzinfo) if last.tzinfo else dt.datetime.now())
        late = (current - last).total_seconds() / 60 - period
    except (ValueError, TypeError, OverflowError):
        return None
    if late <= period * 0.5 + LOST_GRACE_MIN:
        return None
    return {"loop": loop, "last": last, "late": late}


def lost_loop_line(key, transcript_path, restarted=False, state=None):
    """The line a hook of yours can inject for a lost loop, or "". restarted=True is for a
    session start or resume: the process is new, so a loop the state still holds may have lost
    its cron whatever the clock says."""
    st = load_state(key) if state is None else state
    loop = st["form"] if "form" in st else st.get("armed_loop")
    lost = lost_loop(key, state=st)
    if not lost and restarted and loop and not st.get("stopped"):
        lost = {"loop": loop, "last": None, "late": None}
    if not lost:
        return ""
    when = ("this session restarted (window reload, or closed and reopened), and session-only crons may not survive "
            "that, so CronList decides"
            if lost["late"] is None else
            "its last tick ran %s and the next is %.0f min overdue" % (lost["last"].strftime("%m-%d %H:%M"), lost["late"]))
    return ("#LostLoop: this session's %s chain may have no cron: %s. Re-arm it before the turn's own work: CronList; if "
            "no job of that loop is pending, run the keepwarm_tick.py command from your wake prompt (it prints REARM) "
            "and CronCreate that cron, recurring=false, with the wake prompt verbatim. Then say \"#LostLoop re-armed, "
            "next tick HH:MM\" in the reply. If the loop was ended on purpose, run python \"%s/keepwarm_tick.py\" "
            "--session \"%s\" --stop instead."
            % (lost["loop"], when, HERE.replace("\\", "/"), transcript_path))


if __name__ == "__main__":
    import argparse
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Print the context reading for a transcript.")
    ap.add_argument("--session", required=True, help="path of the session's transcript .jsonl")
    a = ap.parse_args()
    k = session_key(a.session)
    f, c, mdl = measure(a.session)
    print("CONTEXT %s (%s compactions, model %s)"
          % (("%.1f%%" % f) if f is not None else "unavailable",
             c if c is not None else "unavailable", mdl or "unavailable"))
    print("COMPACTION PREP DUE" if prep_due(k, f, c) else "compaction prep not due")
