#!/usr/bin/env python3
r"""keepwarm_tick.py: one bare command for a reprompt tick or arming.

A reprompt loop is a chain of one-shot, session-only cron jobs. Each tick runs this script once,
and the script says what the tick is and when the next one should fire.

WHY A ONE-SHOT CHAIN AND NOT A RECURRING CRON. A 5-field cron cannot say "every 50 minutes":
`*/50` fires at :00 and :50 (gaps of 50 and 10), and any expression whose hour field repeats
hourly gives gaps that sum to 60. A recurring job also gets late jitter (up to 10% of its period),
which can push a 50 minute gap past a one hour cache lifetime. A one-shot job has none. So each tick
schedules the next one-shot, and this script prints the exact cron expression for it.

WHAT IT DOES, in one call:
  1. decides whether to re-arm: REARM (with the cron expression) or DUPLICATE (a second chain: the
     last tick of this session ran under 0.8 of the period ago, so this copy lapses)
  2. reads the session's own --watch files and prints the lines that are new since the last tick
  3. prints the CONTEXT reading (needs --session, the transcript path)
  4. prints the compaction lines when they are due, the hybrid, plan, quiet and parley lines
  5. optionally records a signature through a command of yours (REPROMPT_SIGNATURE_CMD, off by default)
  6. prints REPLY <one line>, which the session echoes as its whole reply

It writes only its own state, under the state folder: the environment variable REPROMPT_STATE_DIR,
default ~/.reprompt. It reads the watch files and the transcript and changes nothing else.

Environment variables (all optional):
  REPROMPT_STATE_DIR       the state folder, default ~/.reprompt
  REPROMPT_CONTEXT_WINDOW  the model's context window in tokens, default 200000 (see keepwarm_common.py)
  REPROMPT_SIGNATURE_CMD   a command to run after each tick, for example a generator that writes a
                           record of the tick to a file. Placeholders {seat} {session} {stamp} {out}.
                           {stamp} comes from time_stamp.py; {out} is a path inside the state folder.

Examples:
  python keepwarm_tick.py --seat api --arm --plan "2 0 8" --session "<transcript>" --watch notes.md
  python keepwarm_tick.py --seat api --loop Plan --session "<transcript>" --watch notes.md
  python keepwarm_tick.py --seat api --loop KeepWarmHigh --session "<transcript>" --watch notes.md
  python keepwarm_tick.py --session "<transcript>" --stop
"""
import argparse
import datetime as dt
import hashlib
import io
import json
import os
import shlex
import subprocess
import sys

sys.dont_write_bytecode = True      # never litter the folder the scripts live in with __pycache__
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
try:
    import keepwarm_common as kc
except Exception as _e:          # never let a missing helper end a chain
    kc = None
    _KC_ERR = str(_e)

STATE_DIR = kc.STATE_DIR if kc else os.path.expanduser(os.environ.get("REPROMPT_STATE_DIR") or os.path.join("~", ".reprompt"))
TIME_STAMP = os.path.join(HERE, "time_stamp.py")
SIGNATURE_CMD = (os.environ.get("REPROMPT_SIGNATURE_CMD") or "").strip()
PERIOD_MIN = 50
SHOW_LINES = 12

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def load_state(key):
    if kc:
        return kc.load_state(key)
    try:
        return json.loads(io.open(os.path.join(STATE_DIR, "%s.json" % key), encoding="utf-8").read())
    except Exception:
        return {}


def save_state(key, upd):
    """Read, merge, atomically replace (keepwarm_common does it; this is the fallback)."""
    if kc:
        return kc.save_state(key, upd)
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        cur = load_state(key)
        cur.update(upd)
        p = os.path.join(STATE_DIR, "%s.json" % key)
        with io.open(p + ".tmp", "w", encoding="utf-8") as fh:
            fh.write(json.dumps(cur))
        os.replace(p + ".tmp", p)
        return cur
    except Exception:
        return None


def key_for(session, seat):
    """The state key: the transcript's file name without .jsonl, else the seat name."""
    b = os.path.basename(session or "")
    if b.endswith(".jsonl"):
        return b[:-6]
    return seat or b or None


ap = argparse.ArgumentParser(description="One bare command for a reprompt tick or arming.")
ap.add_argument("--seat", default=None, help="a short name for this session; required for a tick or an arming")
ap.add_argument("--loop", default=None,
                help="KeepWarmHigh, KeepWarmLow, StandReadyLow, StandReadyMid, StandReadyHigh, CompactionForm, "
                     "or Plan (the numbered plan); aliases such as Warm and Ready are accepted; sets the period")
ap.add_argument("--session", default="", help="path of this session's transcript .jsonl (a hook can supply it each turn)")
ap.add_argument("--watch", action="append", default=[], help="a file the user may leave something in; repeatable")
ap.add_argument("--arm", action="store_true", help="arming turn: record a baseline, print the first cron")
ap.add_argument("--period", type=int, default=None,
                help="minutes between ticks, overriding the loop's own; the duplicate window is 0.8 of it")
ap.add_argument("--compaction-prompt", default=None,
                help="register the prepared compaction prompt file for this session, then exit")
ap.add_argument("--prev-prompt", default=None,
                help="with --loop CompactionForm --arm: file holding the previous loop's wake prompt, or none")
ap.add_argument("--hybrid", type=int, default=None,
                help="every Nth tick is a full #StandReadyLow check; default 10 for KeepWarmHigh, 0 otherwise")
ap.add_argument("--plan", default=None,
                help='with --arm: "a[/p] [b[/y]] [c]". a level 1 KeepWarmHigh, 2 StandReadyLow, 3 StandReadyHigh; '
                     'p the fast period with level 3 (5 to 30, default 15); b ticks per level before stepping down (0 never), '
                     'or b/y with level 3 (b ticks at 3, then y at 2); c quiet ticks before level a starts; 0 or off stops')
ap.add_argument("--parley", default=None,
                help="the URL of this session's parley page: stored in the state file and shown on every full tick; "
                     "with only --session it registers and exits; 'none' clears it")
ap.add_argument("--stop", action="store_true",
                help="record that this session's loop was ended on purpose, so it is not reported lost, then exit")
a = ap.parse_args()


def need_key():
    k = key_for(a.session, a.seat)
    if not k:
        print("Needs --session (the transcript path) or --seat to know which session's state to use.")
        sys.exit(1)
    return k


# The stop words: --plan 0, off or stop act as --stop (only a plan that is exactly one of these; "2 0 7" keeps its meaning).
if a.plan is not None and a.plan.strip().lower() in ("0", "off", "stop"):
    a.stop = True

# --stop: the user ended the loop. Needs only the transcript path or the seat name.
if a.stop:
    _k = need_key()
    _st = load_state(_k)
    save_state(_k, {"stopped": True, "stopped_at": dt.datetime.now().isoformat(timespec="minutes"),
                    "stopped_loop": _st.get("form") or _st.get("armed_loop"), "form": None})
    print("STOP recorded: %s will not be reported lost. Delete its pending job with CronDelete."
          % (_st.get("form") or _st.get("armed_loop") or "no loop"))
    sys.exit(0)

# --compaction-prompt: register and leave (compaction prep).
if a.compaction_prompt:
    _k = need_key()
    if not os.path.isfile(a.compaction_prompt):
        print("COMPACTION PROMPT not registered: %s does not exist" % a.compaction_prompt)
        sys.exit(1)
    f, c, _m = kc.measure(a.session) if kc else (None, None, None)
    save_state(_k, {"compaction_prompt": os.path.abspath(a.compaction_prompt),
                    "prep_at_compactions": c,
                    "prep_at": dt.datetime.now().isoformat(timespec="minutes")})
    print("COMPACTION PROMPT registered: %s (compaction %s, context %s). Read it first after any compaction."
          % (os.path.abspath(a.compaction_prompt), c, ("%.0f%%" % f) if f is not None else "unavailable"))
    sys.exit(0)

# --parley alone: register and leave. Needs only the transcript path.
if a.parley and not a.seat:
    _k = need_key()
    _pu = "none" if a.parley.strip().lower() == "none" else a.parley.strip()
    save_state(_k, {"parley_url": _pu})
    print("PARLEY registered: %s. Every full tick now ends its REPLY line with it." % _pu if _pu != "none"
          else "PARLEY set to none for this session: full ticks carry no link.")
    sys.exit(0)

if not a.seat:
    ap.error("--seat is required for a tick or an arming")

LOOPS = {"keepwarm": ("#KeepWarmHigh", 50), "warm": ("#KeepWarmHigh", 50), "staywarm": ("#KeepWarmHigh", 50),
         "keepwarmhigh": ("#KeepWarmHigh", 50), "warmhigh": ("#KeepWarmHigh", 50), "staywarmhigh": ("#KeepWarmHigh", 50),
         "keepwarmlow": ("#KeepWarmLow", 50), "warmlow": ("#KeepWarmLow", 50), "staywarmlow": ("#KeepWarmLow", 50),
         "standready": ("#StandReadyLow", 50), "ready": ("#StandReadyLow", 50), "stayready": ("#StandReadyLow", 50),
         "standreadylow": ("#StandReadyLow", 50), "readylow": ("#StandReadyLow", 50),
         "stayreadylow": ("#StandReadyLow", 50),
         "standreadymid": ("#StandReadyMid", 30), "readymid": ("#StandReadyMid", 30), "stayreadymid": ("#StandReadyMid", 30),
         "standreadyhigh": ("#StandReadyHigh", 15), "readyhigh": ("#StandReadyHigh", 15),
         "stayreadyhigh": ("#StandReadyHigh", 15),
         "compactionform": ("#CompactionForm", 10), "compaction": ("#CompactionForm", 10)}
PERIODS = {v[0]: v[1] for v in LOOPS.values()}

# The numbered plan (/reprompt a b c). Resolved here, before anything reads the loop, so the rest of the tick is unchanged.
LEVELS = {1: "#KeepWarmHigh", 2: "#StandReadyLow", 3: "#StandReadyHigh"}


def _parse_plan(txt):
    """"a[/p] [b[/y]] [c]". p: level 3's period, 5 to 30 minutes (15 when left out). b/y: ticks at level 3, then at level 2
    (y 0: hold at 2). A single b keeps its meaning: the same count at each level. Returns ([a, b, c], p, [b, y])."""
    t = txt.replace(",", " ").split()
    assert 1 <= len(t) <= 3
    h = t[0].split("/")
    assert 1 <= len(h) <= 2
    lv, pp = int(h[0]), (int(h[1]) if len(h) == 2 else None)
    assert lv in LEVELS and (pp is None or (lv == 3 and 5 <= pp <= 30))
    bs = [int(x) for x in t[1].split("/")] if len(t) > 1 else [0]
    assert 1 <= len(bs) <= 2 and all(x >= 0 for x in bs) and (len(bs) == 1 or lv == 3)
    c = int(t[2]) if len(t) > 2 else 0
    assert c >= 0
    return [lv, bs[0], c], pp, bs


def _plan_limit(p, lvl):
    """Ticks to run at level lvl before stepping down; 0 = hold there."""
    bs = p.get("bs")
    if isinstance(bs, list) and bs:
        i = p["a"] - lvl
        return bs[i] if 0 <= i < len(bs) else 0
    return p.get("b", 0)


def _plan_text(p):
    if p.get("text"):
        return p["text"]
    h = "%d/%d" % (p["a"], p["p"]) if p.get("p") else "%d" % p["a"]
    m = "/".join(str(x) for x in p["bs"]) if isinstance(p.get("bs"), list) and len(p["bs"]) > 1 else "%d" % p.get("b", 0)
    return "%s %s %d" % (h, m, p.get("c", 0))


PLAN = None
PLAN_NOTE = ""
_plan_wanted = bool(a.plan) or (a.loop or "").strip().lstrip("#").lower() in ("plan", "reprompt")
key = key_for(a.session, a.seat)
if _plan_wanted:
    _pnow = dt.datetime.now().replace(second=0, microsecond=0)
    _pst = load_state(key) or {}
    if a.arm:
        try:
            _n, _pp, _bs = _parse_plan(a.plan)
        except Exception:
            ap.error('--plan %r must be "a[/p] [b[/y]] [c]": a is 1, 2 or 3; p (level 3 only) 5 to 30 minutes; b, y and c whole '
                     'numbers, 0 or more; b/y only when a is 3' % a.plan)
        PLAN = {"a": _n[0], "b": _n[1], "c": _n[2], "level": 0 if _n[2] > 0 else _n[0], "k": 0,
                "delay_loop": LEVELS[1], "armed_at": _pnow.isoformat()}   # the quiet-first ticks are always #KeepWarmHigh
        if _pp:
            PLAN["p"] = _pp                        # level 3's own period (/reprompt 3/10)
        if len(_bs) > 1:
            PLAN["bs"] = _bs                       # one count per level (/reprompt 3 n/y)
        PLAN["text"] = _plan_text(PLAN)
    else:
        PLAN = _pst.get("plan") if isinstance(_pst.get("plan"), dict) else None
        if PLAN is None:
            PLAN_NOTE = "PLAN none recorded for this session: running as #KeepWarmHigh. Re-arm with --arm --plan \"a b c\"."
            a.loop = "KeepWarmHigh"
        else:
            PLAN = dict(PLAN)
            _lt, _ppd = _pst.get("last_tick"), _pst.get("period")
            _dup0 = False
            try:
                if _lt and isinstance(_ppd, int):
                    _dup0 = (_pnow - dt.datetime.fromisoformat(_lt)).total_seconds() / 60 < int(_ppd * 0.8)
            except Exception:
                _dup0 = False
            if not _dup0:
                _moved = False
                if PLAN.get("level", 0) == 0 and PLAN.get("k", 0) >= PLAN.get("c", 0):
                    PLAN["level"], PLAN["k"], _moved = PLAN["a"], 0, True
                while PLAN["level"] > 1 and _plan_limit(PLAN, PLAN["level"]) > 0 and PLAN.get("k", 0) >= _plan_limit(PLAN, PLAN["level"]):
                    PLAN["level"], PLAN["k"], _moved = PLAN["level"] - 1, 0, True
                PLAN["k"] = PLAN.get("k", 0) + 1
                PLAN["moved"] = _moved
    if PLAN is not None:
        _eff = PLAN.get("delay_loop", LEVELS[1]) if PLAN["level"] == 0 else LEVELS[PLAN["level"]]
        a.loop = _eff.lstrip("#")
        a.period = PLAN["p"] if (PLAN.get("p") and PLAN["level"] == 3) else None   # /reprompt 3/10
        if PLAN["level"] == 0:
            _where = "quiet %d/%d as %s, then level %d %s" % (PLAN["k"], PLAN["c"], _eff, PLAN["a"], LEVELS[PLAN["a"]])
        elif PLAN["level"] > 1 and _plan_limit(PLAN, PLAN["level"]) > 0:
            _where = "level %d %s %d/%d, then level %d %s" % (PLAN["level"], _eff, PLAN["k"], _plan_limit(PLAN, PLAN["level"]),
                                                               PLAN["level"] - 1, LEVELS[PLAN["level"] - 1])
        else:
            _where = "level %d %s, holding" % (PLAN["level"], _eff)
        PLAN_NOTE = "PLAN %s: %s" % (_plan_text(PLAN), _where)
if a.loop:
    _k = a.loop.strip().lstrip("#").lower()
    if _k not in LOOPS:
        ap.error("--loop %r is not one of KeepWarmHigh, KeepWarmLow, StandReadyLow, StandReadyMid, StandReadyHigh, "
                 "CompactionForm, Plan" % a.loop)
    LOOP, PERIOD_MIN = LOOPS[_k]
    if a.period:
        PERIOD_MIN = a.period
else:
    PERIOD_MIN = a.period or PERIOD_MIN
    LOOP = "#KeepWarmHigh" if PERIOD_MIN >= 50 else ("#StandReadyHigh" if PERIOD_MIN <= 15 else "#StandReadyMid")
DUPLICATE_MIN = int(PERIOD_MIN * 0.8)

now = dt.datetime.now().replace(second=0, microsecond=0)
os.makedirs(STATE_DIR, exist_ok=True)
state = load_state(key)
prev_tick_fill = state.get("tick_fill")
if PLAN is not None and (a.arm or PLAN.get("moved")):
    state["hybrid_k"] = 0          # a new phase starts its own 1-in-10 count

# The blocked-seat upgrade. blocked_ticks and abandoned are written by an optional alerting hook of
# yours, never by these scripts. #KeepWarm loops are never upgraded into a full loop.
ARMED_LOOP = LOOP
_blocked = state.get("blocked_ticks") or 0
UPGRADED = False
HYBRID_N = a.hybrid if a.hybrid is not None else (10 if LOOP == "#KeepWarmHigh" else 0)
if LOOP in ("#StandReadyMid", "#StandReadyLow") and isinstance(_blocked, int) and _blocked > 2:
    LOOP, PERIOD_MIN, UPGRADED = "#StandReadyHigh", 15, True
    DUPLICATE_MIN = int(PERIOD_MIN * 0.8)
# An ignored seat runs as #StandReadyLow until the user's next prompt.
ABANDONED = bool(state.get("abandoned")) and LOOP in ("#StandReadyMid", "#StandReadyLow", "#StandReadyHigh")
if ABANDONED:
    LOOP, PERIOD_MIN, UPGRADED = "#StandReadyLow", 50, False
# A tick that has just changed period is measured against the shorter period, not taken for a second chain
_pp = state.get("period")
if isinstance(_pp, int) and 0 < _pp < PERIOD_MIN and LOOP != "#CompactionForm":
    DUPLICATE_MIN = int(_pp * 0.8)

# 0. Measure first, so the compaction lines can come first.
fill = comps = None
SHIFT_DUE = RECOVERED = False
if kc and a.session:
    try:
        fill, comps, _model = kc.measure(a.session)
        if LOOP == "#CompactionForm":
            _sa = state.get("shifted_at_compactions")
            if not a.arm and comps is not None and isinstance(_sa, int) and comps > _sa:
                RECOVERED = True
        elif not a.arm and kc.form_due(key, fill, comps):
            SHIFT_DUE = True
        elif kc.prep_due(key, fill, comps):
            print("COMPACTION PREP DUE: context %.1f%% (compaction %d). Write <SEAT>_COMPACTION_PROMPT_<YYYYMMDD>.md "
                  "in a folder you keep for this session and register it: keepwarm_tick.py --session \"<transcript>\" "
                  "--compaction-prompt \"<path>\" (reprompt skill). Its one-line alert comes first." % (fill, comps))
    except Exception:
        fill = comps = None


def lines_of(p):
    try:
        return io.open(p, encoding="utf-8", errors="replace").read().splitlines()
    except Exception:
        return None


def h(s):
    return hashlib.sha256(s.strip().encode("utf-8", "replace")).hexdigest()[:12]


def next_fire():
    t = now + dt.timedelta(minutes=PERIOD_MIN)
    if t.minute in (0, 30):          # keep off the :00 and :30 marks that many schedulers share
        t -= dt.timedelta(minutes=1)
    return t, "%d %d %d %d *" % (t.minute, t.hour, t.day, t.month)


print("%s %s for %s at %s local (period %d min)"
      % (LOOP, "ARM" if a.arm else "tick", a.seat, now.strftime("%Y-%m-%d %H:%M"), PERIOD_MIN))
if PLAN_NOTE:
    print(PLAN_NOTE)
if UPGRADED:
    print("UPGRADED %s -> #StandReadyHigh: blocked %d ticks in a row; back to %s at the first tick that is not blocked"
          % (ARMED_LOOP, _blocked, ARMED_LOOP))
if ABANDONED:
    print("IGNORED: the user has not answered this session's #StandReadyHigh ticks, so it runs as #StandReadyLow until "
          "the next prompt (armed %s). Re-arm with the same wake prompt at the cron below." % ARMED_LOOP)

# 1. Re-arm decision, printed before anything else that could block it.
last = state.get("last_tick")
gap = (now - dt.datetime.fromisoformat(last)).total_seconds() / 60 if (last and not a.arm) else None
t, cron = next_fire()
if RECOVERED:
    _prev, _pf = state.get("prev_loop"), state.get("prev_prompt_file") or "none"
    print("RECOVERED: compaction happened (count %s -> %s). Do NOT re-arm #CompactionForm." % (state.get("shifted_at_compactions"), comps))
    print("1. Read first: %s" % (state.get("compaction_prompt") or "no compaction prompt was registered; rebuild from your own notes"))
    if _prev and _pf.lower() != "none":
        PERIOD_MIN = PERIODS.get(_prev, 30)
        t, cron = next_fire()
        print('2. Shift back to %s: CronCreate(cron="%s", recurring=false, prompt=<the text of %s, verbatim>)   next tick %s'
              % (_prev, cron, _pf, t.strftime("%H:%M")))
    else:
        print("2. No previous loop: the chain ends here.")
elif SHIFT_DUE:
    print("SHIFT TO #CompactionForm: context %.1f%% (compaction %s). Do NOT re-arm %s. Save THIS wake prompt verbatim "
          "to <SEAT>_PREV_FORM_PROMPT.md in a folder you keep for this session, then run keepwarm_tick.py --seat <SEAT> "
          "--loop CompactionForm --session \"<transcript>\" --arm --prev-prompt \"<that file>\" and CronCreate its FIRST "
          "cron with the #CompactionForm wake prompt (reprompt skill). If no compaction prompt is registered, write "
          "and register one first." % (fill, comps, LOOP))
elif gap is not None and gap < DUPLICATE_MIN:
    print("DUPLICATE: the last tick in this session ran %.0f min ago, so this is a second chain." % gap)
    print("Do NOT re-arm from this tick; the other chain carries on.")
else:
    print('%s cron="%s"   recurring=false   next tick %s' % ("FIRST" if a.arm else "REARM", cron, t.strftime("%H:%M")))

# 2. Watch files: new lines since the last tick.
old_watch = state.get("watch", {})
new_watch = {}
changed = 0
for p in a.watch:
    ls = lines_of(p)
    if ls is None:
        print("MISSING %s" % p)
        continue
    hs = [h(x) for x in ls]
    new_watch[p] = {"size": os.path.getsize(p), "mtime": os.path.getmtime(p), "hashes": sorted(set(hs))}
    prev = old_watch.get(p)
    if a.arm or prev is None:
        continue
    if prev["size"] == new_watch[p]["size"] and prev["mtime"] == new_watch[p]["mtime"]:
        continue
    seen = set(prev["hashes"])
    fresh = [(i + 1, x) for i, (x, y) in enumerate(zip(ls, hs)) if y not in seen and x.strip()]
    changed += 1
    print("CHANGED %s (modified %s, %d new or edited lines)" % (
        p, dt.datetime.fromtimestamp(new_watch[p]["mtime"]).strftime("%H:%M"), len(fresh)))
    for n, x in fresh[:SHOW_LINES]:
        print("  + L%d: %s" % (n, x.strip()[:160]))
    if len(fresh) > SHOW_LINES:
        print("  ... %d more" % (len(fresh) - SHOW_LINES))
if a.arm:
    print("watch baseline recorded for %d file(s)" % len(new_watch))
elif not changed:
    print("watch: no change in %d file(s)" % len(new_watch))

# 3. Context reading.
if fill is not None:
    was = ("was %.0f%%" % prev_tick_fill) if isinstance(prev_tick_fill, (int, float)) else "no earlier reading"
    print("CONTEXT %.0f%% (%s, %s compactions)"
          % (fill, was, comps if comps is not None else "unavailable"))
elif not kc:
    print("CONTEXT unavailable: keepwarm_common missing (%s)" % _KC_ERR)
elif getattr(kc, "WINDOW_EXCEEDED", False):
    print("CONTEXT unavailable: the last turn held more tokens than the window of %d; "
          "set REPROMPT_CONTEXT_WINDOW to your model's context window" % kc.context_window())
else:
    print("CONTEXT unavailable: no readable transcript, or no measured assistant turn yet")

upd = {"seat": a.seat, "watch": new_watch, "period": PERIOD_MIN, "loop": LOOP, "armed_loop": ARMED_LOOP,
       "stopped": False}   # a tick or an arming means the loop runs again, so it is no longer stopped
if fill is not None:
    upd["tick_fill"] = round(fill, 1)
if a.parley:
    upd["parley_url"] = "none" if a.parley.strip().lower() == "none" else a.parley.strip()
if PLAN is not None:
    if not a.arm and gap is not None and gap < DUPLICATE_MIN:
        pass                       # a duplicate tick leaves the recorded plan as it was
    else:
        upd["plan"] = {k: v for k, v in PLAN.items() if k != "moved"}
elif a.arm:
    upd["plan"] = None             # arming a plain loop ends any plan
# Hybrid counter: advances only on a real (not duplicate) tick; an arming starts it at 0.
HYBRID_K, HYBRID_DUE = 0, False
if HYBRID_N > 0:
    _hk = state.get("hybrid_k") if isinstance(state.get("hybrid_k"), int) else 0
    if a.arm:
        HYBRID_K = 0
    elif gap is not None and gap < DUPLICATE_MIN:
        HYBRID_K = _hk
    else:
        HYBRID_K = _hk % HYBRID_N + 1
        HYBRID_DUE = HYBRID_K == HYBRID_N
    upd.update({"hybrid_k": HYBRID_K, "hybrid_n": HYBRID_N})
    if HYBRID_DUE:
        print("HYBRID DUE (%d/%d): run this tick as #StandReadyLow (the session's full check), then re-arm the same wake prompt verbatim at the REARM cron" % (HYBRID_K, HYBRID_N))
if a.arm:
    upd["armed"] = now.isoformat()
    upd["last_tick"] = None
elif not (gap is not None and gap < DUPLICATE_MIN):
    upd["last_tick"] = now.isoformat()
if LOOP == "#CompactionForm" and a.arm:
    _pl = state.get("loop") if (a.prev_prompt and a.prev_prompt.lower() != "none") else None
    if _pl == "#CompactionForm":
        _pl = state.get("prev_loop")
    upd.update({"form": "#CompactionForm", "prev_loop": _pl, "prev_prompt_file": a.prev_prompt or "none",
                "shifted_at_compactions": comps, "form_at_compactions": comps})
elif RECOVERED:
    upd.update({"form": state.get("prev_loop"), "loop": state.get("prev_loop") or LOOP, "last_tick": None})
elif LOOP != "#CompactionForm":
    upd["form"] = LOOP
save_state(key, upd)

# 4. The one-line reply, printed before anything below can exit.
if not a.arm:
    if gap is not None and gap < DUPLICATE_MIN:
        REPLY = "%s, duplicate chain, not re-armed" % LOOP
    else:
        _ctx = ("context %.0f%%" % fill) if fill is not None else "context n/a"
        if fill is not None and isinstance(prev_tick_fill, (int, float)):
            _ctx += " (was %.0f%%)" % prev_tick_fill
        _what = "noop" if not changed else "%d watch file(s) changed" % changed
        REPLY = "%s, %s, %s, next tick %s" % (LOOP, _what, _ctx, t.strftime("%H:%M"))
        if UPGRADED:
            REPLY += " (upgraded from %s: blocked %d ticks)" % (ARMED_LOOP, _blocked)
        if ABANDONED:
            REPLY += " (ignored: down from #StandReadyHigh until the user prompts)"
        if HYBRID_DUE:
            REPLY = "#StandReadyLow (hybrid %d/%d)" % (HYBRID_K, HYBRID_N) + REPLY[len(LOOP):]
        elif HYBRID_N > 0:
            REPLY += " (hybrid %d/%d)" % (HYBRID_K, HYBRID_N)
        if PLAN_NOTE and PLAN is not None:
            REPLY += " (plan" + PLAN_NOTE[4:] + ")"
    _dupt = gap is not None and gap < DUPLICATE_MIN
    _full = LOOP.startswith("#StandReady") or HYBRID_DUE
    # A quiet notice: quiet_notice.json in the state folder, matched by the start of the seat name
    if not _dupt:
        try:
            import time as _qt
            with open(os.path.join(STATE_DIR, "quiet_notice.json"), encoding="utf-8") as _qf:
                _q = json.load(_qf)
            if not (_qt.time() < float(_q.get("expires_epoch", 0))):
                _q = None
        except Exception:
            _q = None
        try:
            _ql, _qn = int(state.get("quiet_left") or 0), int(state.get("quiet_total") or 0)
            if _q and state.get("quiet_id") != _q.get("id") and any((a.seat or "").upper().startswith(str(p).upper()) for p in _q.get("prefixes", [])):
                _qn = int(_q.get("ticks", 8))
                save_state(key, {"quiet_id": _q.get("id"), "quiet_left": _qn, "quiet_total": _qn})
                print("QUIET NOTICE (%s): %s Run THIS tick as it is; it counts as your next full turn if it is a full "
                      "tick. Your next %d ticks are then QUIET whatever your loop: the script will say QUIET TICK. "
                      "Do not message anyone about this notice." % (_q.get("id"), _q.get("text", ""), _qn))
            elif _ql > 0:
                save_state(key, {"quiet_left": _ql - 1})
                _full = False
                print("QUIET TICK %d/%d (the user is away): warm tick only. Re-arm, one comment read and one heartbeat "
                      "write on your parley if you own one, and nothing else: no sweep, no builds, no messages, "
                      "no publishes, no alerts that ask for the user. A comment from the user on your parley is still "
                      "answered. Reply with the REPLY line only." % (_qn - _ql + 1, _qn))
                REPLY += " (quiet %d/%d)" % (_qn - _ql + 1, _qn)
        except Exception:
            pass
    if _plan_wanted and not _dupt:
        print("MODE %s" % ("full: run this session's full check this tick" if _full
                           else "minimal: warm only, no sweep"))
    # Every full tick carries the session's parley link, when one is registered.
    if _full and not _dupt:
        _pu = upd.get("parley_url") if "parley_url" in upd else state.get("parley_url")
        if _pu and _pu != "none":
            print("PARLEY %s" % _pu)
            REPLY += " | Parley: %s" % _pu
            # Once a day, on the first full tick at or after the recheck hour, remind the session of the
            # parley skill's daily recheck. Warm ticks neither print it nor use the day up.
            try:
                _rn = dt.datetime.now()
                _rday = _rn.strftime("%Y-%m-%d")
                if _rn.hour >= int(os.environ.get("REPROMPT_RECHECK_HOUR") or 7) and state.get("parley_recheck_day") != _rday:
                    save_state(key, {"parley_recheck_day": _rday})
                    print("PARLEY DAILY RECHECK DUE (shown once a day, on the first full tick at or after the recheck hour): "
                          "in THIS turn run the parley skill's scripts/parley_stale.py on your parley JSON (a manager adds "
                          "--report <file> for each report). For every card it lists, and for every open card that waits on "
                          "something that can move without you hearing of it whose newest dated line is over 24 hours old: "
                          "look in the system of record, not in memory, write a dated 'checked' line on the card, re-rate "
                          "Important and Urgent, then rewrite, update or close it. Publish only if something on the page "
                          "changed. No card listed and none waiting on an outside party: nothing to do and nothing to report.")
            except Exception:
                pass
            if not state.get("crew_rule_shown"):
                save_state(key, {"crew_rule_shown": True})
                print("PARLEY CREW RULE: only the session that OWNS a parley links it. If the page above is another "
                      "session's (a manager's, with you on its crew), leave the link out of this reply and run once: "
                      "keepwarm_tick.py --session \"<transcript>\" --parley none. Comments and the heartbeat on that "
                      "page are its owner's. Shown once.")
    if RECOVERED:
        REPLY = "#CompactionForm, recovered after compaction %s, shifting back to %s" % (comps, state.get("prev_loop") or "no loop")
    elif SHIFT_DUE:
        REPLY = "%s, context %.0f%%: shifting into #CompactionForm" % (LOOP, fill)
    elif LOOP == "#CompactionForm":
        REPLY = REPLY.replace("#CompactionForm, noop", "#CompactionForm, waiting for compaction")

# The standing rule on comments and the page heartbeat, on every tick and arming of every loop, when a parley is registered.
_pu3 = upd.get("parley_url") if "parley_url" in upd else state.get("parley_url")
if _pu3 and _pu3 != "none":
    print("COMMENTS RULE (every loop level, warm ticks included): a comment the user sends to Claude on this session's "
          "parley is the user's own instruction, the same as a typed prompt. Answering it is authorized and expected at "
          "any time as a full working turn: read the thread, reply in it with ArtifactComments, update the card, "
          "republish. The 'do as little as possible' limit on a warm tick does not cover the user's comments. The "
          "automatic reply to a comment can be refused before you see it, so on EVERY tick also make one "
          "ArtifactComments read of that page and answer every thread marked awaiting reply, and read the page's "
          "status collection with ArtifactData (a status the user set is a ruling; see the parley skill). Also on EVERY "
          "tick, one ArtifactData write of heartbeat/owner on that page: last_seen now, next_tick the REARM time, "
          "period_min this tick's period, watching_comments true.")

# 5. Optional signature, from a command of yours, to a file only.
if a.arm:
    sys.exit(0)
if SIGNATURE_CMD and a.session and os.path.isfile(a.session):
    try:
        stamp = subprocess.check_output([sys.executable, TIME_STAMP], timeout=30).decode("utf-8", "replace").strip()
        out = os.path.join(STATE_DIR, "sig_%s.txt" % key)
        subs = {"{seat}": a.seat, "{session}": a.session, "{stamp}": stamp, "{out}": out}
        parts = shlex.split(SIGNATURE_CMD, posix=(os.name != "nt"))
        cmd = []
        for part in parts:
            if os.name == "nt" and len(part) >= 2 and part[0] == part[-1] and part[0] in "\"'":
                part = part[1:-1]
            for k_, v_ in subs.items():
                part = part.replace(k_, v_)
            cmd.append(part)
        r = subprocess.run(cmd, capture_output=True, timeout=180)
        if r.returncode != 0:
            print("SIGNATURE unavailable: command exit %d: %s" % (
                r.returncode, r.stderr.decode("utf-8", "replace").strip()[-300:]))
        else:
            print("SIGNATURE recorded to %s (not for the reply)" % out)
    except Exception as e:
        print("SIGNATURE unavailable: %s" % e)
print("REPLY " + REPLY)
print("Reply with the REPLY line only: no signature, no fence.")
