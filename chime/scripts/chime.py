#!/usr/bin/env python3
r"""chime: sound and toast alerts for Claude Code sessions (skillgarden).

One copy per account, installed with the skill; the account's settings.json points its hooks here. Python 3.8 or later,
standard library only. Windows is the supported platform for sound and toasts.

  python chime.py decision      Stop hook. Picks ONE sound for the finished turn, from the reply's first line:
                                  first line opens MAJOR PROBLEM FOUND          -> urgent, boing, important (one blocked seat)
                                  first line opens RED ALERT                    -> red_alert, alone
                                  first line opens URGENT DECISION NEEDED       -> urgent
                                  first line opens IMPORTANT DECISION NEEDED
                                        or "Decision needed"                    -> important
                                  a reply that hands over a compaction prompt (first line opens
                                        #CompactionPrep or #SmartCompact, or a line opens "Type /compact")
                                        also plays compact, LAST                -> ... + compact
                                  otherwise by what started the turn: a #KeepWarm/#StandReady tick -> tick,
                                  another session's message -> peer, anything else (the person) -> default
  python chime.py autocompact   PreCompact hook (matcher auto): compact.
  python chime.py play urgent|major|important|compact|redalert "<SEAT>" "<what to look at>"
                                Mid-turn, from a shell command, so the person can refocus while the turn runs.
  python chime.py prompt        UserPromptSubmit hook: injects the per-turn chime rules.
  python chime.py redalert check|fire|card|uncarded|verdict|list|example ...
                                The red alert log and its commands.
  python chime.py usage status|mute|unmute ...      The per-account low-usage mute.
  python chime.py sounds list|set|generate|reset|styles ...
                                A person's own sounds, kept outside the skill folder.

Phrases count ONLY where they open the reply (its first non-empty line, leading markdown ignored).
A reply that merely mentions a phrase does not set off its alarm.

Where a person's own choices live. Nothing a person chooses is stored in the skill folder, because an update replaces
that folder whole.
  <skill>/chime.json            the skill's defaults. Every event's default sound is a tone this script generates
                                itself ("gen:<style>"), so a fresh install makes sound with nothing downloaded.
  <chime home>/config.json      the person's overrides: the same keys as chime.json, merged over it key by key (names,
                                labels, account_names, words, spoken_names and texts one level deep).
  <chime home>/sounds/          the person's own sound files, and the tones this script generates on first use. A path
                                written "user:<file>" resolves there; "sounds/<file>" means the skill's own folder.
  <chime home>/usage_mute.json  usage mutes. Other state files (silence.json, heads.json, voices.json, red_alerts.jsonl,
                                usage_log.txt) live there too.
<chime home> is ~/.threadops/chime, or the folder named by the environment variable CHIME_HOME. A missing, broken or
wrongly typed override means the default; it never stops a sound.

The seat named in the toast comes from the reply's closing Sound line, then the session's registered name, then a seat id
in the text, then the session id. Sound files come from chime.json and the person's config.json.

Never blocks or fails a session: every error is swallowed and every hook mode exits 0. A turn is never played twice, even
if two hook entries fire for it. Set CHIME_DRY_RUN=1 to print the decision instead of playing it (used by the tests).

What the hooks do, in the order the behaviours were added:
  - ticks: a turn that a #KeepWarm or #StandReady loop started plays its tick sound (tick, tick_ready, tick_high,
    tick_low, tick_compaction by loop). A blocked seat (MAJOR PROBLEM FOUND) on a #StandReady-family tick plays urgent
    three times and counts blocked ticks in the shared keepwarm state; after three the loop is run as #StandReadyHigh
    and the tick adds escalate. A seat whose #StandReadyHigh ticks need the person ignore_after_ticks times in a row with
    no prompt from them is ignored: that tick adds abandon, the loop drops to #StandReadyLow, and while it still needs
    the person its ticks play ignored alone.
  - the person's own prompt: the prompt hook plays ack the moment it arrives, in a detached process, and not for a
    prompt the session's transcript already records as scheduled or system-sent. The Stop hook then plays done first
    (not after MAJOR PROBLEM FOUND), then any phrase or baton sound.
  - a reply that carries a [BATON ...] block at the start of a line plays relay after the opener sound, or in place of
    tick, peer or default.
  - questions: from the second tick in a row whose report has a line opening "Report questions for <person>:" the tick
    plays questions, at most once per questions_cooldown_min across the machine.
  - a seat listed in ~/.threadops/parley/delegated.json makes no attention sound (its manager does), except RED ALERT.
  - brakes: while ~/.threadops/brakes/<session_id>.json exists, only the brakes sound plays (and the low-usage alarm).
  - mute: the file ~/.chime_muted (or chime.json "mute_file"), a Zoom meeting window, and clocked out in
    ~/.threadops/presence.json all silence sounds; toasts show without sound.
  - toasts name the session by its tab title (the newest custom-title in its transcript, else its ai-title). A quiet tick
    plays its sound and shows no toast.
  - spoken names: after the sounds, a turn that needs the person has the session's name spoken (speak_names:
    attention | all | off), in a neural voice per seat when the edge-tts package is installed, else the Windows voice.
  - dictation: while a dictation app (dictation_apps) records from a microphone, a turn's toasts, sounds and spoken name
    wait in a detached process, at most dictation_hold_max_s, and then play one after another.
  - low usage: at the end of every turn the account's usage is read through the module named by usage_server (the file
    must offer fetch_raw() or fetch_usage()), cached five minutes. At or above usage_alert_pct (90) the alarm plays
    low_health first, at most once per usage_alert_every_min (30) per account, and every reading near the line and every
    decision is logged to usage_log.txt. A muted turn leaves the alarm unspent.
  - usage mute: "usage mute <ACCOUNT>" silences one account's alarm until the reset of the limit that is over the line
    (read from the usage reading's resets_at), or 24 hours when no reset is known. The cache keeps each limit's reset
    time, and finds the cache under either spelling of the account home path.
  - RED ALERT: a reply whose first non-empty line opens RED ALERT (capitals, leading markdown ignored; RED ALERTS does
    not count) plays red_alert alone and first. The log red_alerts.jsonl and the commands "redalert check|fire|verdict|
    list|example" keep a record of every firing and of the person's verdicts, and the prompt hook adds a short paragraph
    saying how to fire and which kinds the person ruled merited or not.
  - sounds: "sounds set" copies an mp3 or wav (5 MB cap) into the sounds folder and maps the event to it; "sounds
    generate" writes a short tone (standard library only; styles beep double rise fall chord alarm tick soft, one table
    that "sounds styles --json" prints and the code synthesises from); "sounds list --json" says what each event
    plays and which file types the player accepts.

Texts. Every sentence this script injects into a session (the per-turn rules, the clock, mute, brakes and red alert
paragraphs) is a default in DEFAULT_TEXTS below. A person's config.json "texts" replaces any of them by key, so a
household can word them its own way without touching this file.
"""
import datetime
import glob
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
_CFG_PATH = os.path.join(os.path.dirname(HERE), "chime.json")
if not os.path.isfile(_CFG_PATH):
    _CFG_PATH = os.path.join(HERE, "chime.json")
try:
    _DEFAULTS = json.load(open(_CFG_PATH, encoding="utf-8"))
    if not isinstance(_DEFAULTS, dict):
        _DEFAULTS = {}
except Exception:
    _DEFAULTS = {}

# A person's own choices live outside the skill folder, which an update replaces.
# <chime home> is ~/.threadops/chime unless the environment variable CHIME_HOME names another folder.
CHIME_HOME = (os.path.normpath(os.environ["CHIME_HOME"]) if os.environ.get("CHIME_HOME")
              else os.path.join(os.path.expanduser("~"), ".threadops", "chime"))
USER_CONFIG = os.path.join(CHIME_HOME, "config.json")
USER_SOUNDS = os.path.join(CHIME_HOME, "sounds")
USAGE_MUTE_FILE = os.path.join(CHIME_HOME, "usage_mute.json")
# the sound events, in the order the board shows them
EVENTS = ("urgent", "important", "boing", "default", "tick", "tick_ready", "tick_high", "tick_low", "peer", "compact",
          "relay", "tick_compaction", "ack", "done", "questions", "low_health", "brakes", "red_alert", "escalate",
          "abandon", "ignored")
_DEEP_KEYS = ("names", "labels", "account_names", "words", "spoken_names", "texts")     # merged one level deep
_NUM_KEYS = ("usage_alert_pct", "usage_alert_every_min", "usage_log_from_pct", "questions_cooldown_min",
             "ignore_after_ticks", "dictation_hold_max_s", "head_gain", "red_alert_gain")
_STR_KEYS = EVENTS + ("mute_file", "usage_server", "sessions_glob", "speak_names", "tick_dir", "stop_gate",
                      "transcripts_glob", "seat_id_regex", "seat_suffix_regex", "rules_text")
_BOOL_KEYS = ("mute_during_zoom", "hold_during_dictation")
_LIST_KEYS = ("dictation_apps", "voice_pool", "question_addressees", "peer_prefixes", "notification_prefixes")


def _type_ok(key, val):
    """An override of the wrong type is dropped, so a typo in config.json cannot break an import."""
    if key in _DEEP_KEYS:
        return isinstance(val, dict)
    if key in _NUM_KEYS:
        try:
            float(val)
            return not isinstance(val, bool)
        except Exception:
            return False
    if key in _STR_KEYS:
        return isinstance(val, str)
    if key in _BOOL_KEYS:
        return isinstance(val, bool)
    if key in _LIST_KEYS:
        return isinstance(val, list)
    return True


def user_sound_path(ref):
    """The file a "user:<file>" reference names inside the sounds folder, or None (also for a path that climbs out)."""
    try:
        name = str(ref)[5:].strip().replace("\\", "/")
        if not name or name.startswith("/") or re.match(r"^[A-Za-z]:", name):
            return None
        p = os.path.normpath(os.path.join(USER_SOUNDS, name))
        base = os.path.normcase(os.path.normpath(USER_SOUNDS))
        return p if os.path.normcase(p).startswith(base + os.sep) else None
    except Exception:
        return None


def load_user_config():
    """(dict, error). The person's config.json; {} with an error text when missing (None) or unreadable."""
    try:
        if not os.path.isfile(USER_CONFIG):
            return {}, None
        with io.open(USER_CONFIG, encoding="utf-8-sig") as fh:
            d = json.load(fh)
        if not isinstance(d, dict):
            return {}, "config.json is not a JSON object"
        return d, None
    except Exception as e:
        return {}, "config.json is unreadable (%s)" % e.__class__.__name__


def merge_config(defaults, user):
    """Defaults with the person's overrides on top, key by key; _DEEP_KEYS one level deep."""
    out = dict(defaults)
    for k, v in (user or {}).items():
        if not _type_ok(k, v):
            continue
        if k in _DEEP_KEYS and isinstance(out.get(k), dict):
            m = dict(out[k])
            m.update(v)
            out[k] = m
        else:
            out[k] = v
    return out


def gen_sound_path(ev, ref):
    """A "gen:<style>" reference as the file its tone is generated into: inside the sounds folder, never the skill folder."""
    style = str(ref)[4:].strip().lower()
    return os.path.join(USER_SOUNDS, "gen-%s-%s.wav" % (ev, style)) if re.match(r"^[a-z]+$", style) else None


def _resolved_config():
    user, _err = load_user_config()
    c = merge_config(_DEFAULTS, user)
    for ev in EVENTS:     # a user: reference becomes its file, a gen: one the file its tone is made in; a missing file means the default
        v = c.get(ev)
        if isinstance(v, str) and v.startswith("user:"):
            p = user_sound_path(v)
            if p and os.path.isfile(p):
                c[ev] = p
            elif _DEFAULTS.get(ev):
                c[ev] = _DEFAULTS[ev]
            else:
                c.pop(ev, None)
        v = c.get(ev)
        if isinstance(v, str) and v.startswith("gen:"):
            g = gen_sound_path(ev, v)
            if g:
                c[ev] = g
            else:
                c.pop(ev, None)
    return c


try:
    _C = _resolved_config()
except Exception:
    _C = dict(_DEFAULTS)


# Every sentence this script injects into a session. A person's config.json "texts" replaces any of them by key; a text
# whose %-placeholders do not fit is ignored and the default here is used. Placeholders are in the order of the code.
DEFAULT_TEXTS = {
    # (python path, script path)
    "prompt_rules": (
        "CHIME RULES (skillgarden chime, every turn). "
        "When this session stops on something only the person it works for can clear (a build blocked, a decision held), "
        "the reply's FIRST line opens with MAJOR PROBLEM FOUND, and the session also plays it mid-turn as soon as it "
        "knows: \"%s\" \"%s\" play major \"<SEAT>\" \"<what is blocked>\". A baton line alone is not enough. Phrases count "
        "only on the reply's first line: open with URGENT DECISION NEEDED, IMPORTANT DECISION NEEDED or URGENT AND "
        "IMPORTANT when a decision is waiting on the person; merely mentioning a phrase elsewhere plays nothing. Every "
        "reply ends with ONE last line naming the sound this turn will play and the seat, for example: Sound: done "
        "(turn the person started) \u00b7 <SEAT>. Name the sound by the rules: a first-line phrase decides it (on a turn "
        "the person started, done plays first unless it opens MAJOR PROBLEM FOUND), otherwise a #KeepWarm/#StandReady "
        "tick plays tick, another session's message plays peer, and anything else plays done. List any mid-turn plays "
        "on the same line, for example: Sound: done + default + boing + important (decision) \u00b7 mid-turn: important "
        "\u00b7 <SEAT>."),
    # (since, " (note)" or "")
    "clock_out": (
        " THE PERSON IS CLOCKED OUT since %s%s. Do not try to get their attention: no decision phrase or MAJOR PROBLEM "
        "FOUND opener, no mid-turn chime play, no wake of a cold peer on their behalf. Keep every question on your "
        "parley card or in the 'Questions for you:' line and carry on with work that needs nothing from them; they see "
        "the queue when they clock in."),
    # (since)
    "clock_in": (
        " THE PERSON CLOCKED IN at %s: questions that waited while they were out can be raised again now."),
    # (names, comma separated)
    "silenced": (
        " SILENCED on the soundboard (never plays): %s. When this turn's sound is one of them, write the closing line "
        "as: Sound: silenced (would play <name>) \u00b7 <SEAT>."),
    # (reason)
    "muted": (
        " CHIME IS MUTED (%s): nothing plays and toasts are silent. Keep the first-line phrases, and write the closing "
        "line as: Sound: muted (would play <name>) \u00b7 <SEAT>."),
    "person_clocked_out": "the person is clocked out",
    # 22 placeholders: the sound names (urgent, default, boing, important, urgent, boing, important, tick, tick_high,
    # tick_low, peer, done, ack, urgent, escalate), the ignore count (%d), abandon, ignored, questions, the cooldown
    # in minutes (%d), relay, compact
    "grid": (
        " Sounds on this machine (urgent/important grid): URGENT DECISION NEEDED plays %s; IMPORTANT DECISION NEEDED or "
        "Decision needed plays %s + %s + %s; URGENT AND IMPORTANT, or MAJOR PROBLEM FOUND, plays %s + %s + %s. Otherwise "
        "a #KeepWarm or #StandReady tick plays %s, #StandReadyHigh %s, #StandReadyLow %s; another session plays %s; the "
        "person's own prompt finished plays %s (first, before any phrase or baton sound; not after MAJOR PROBLEM FOUND), "
        "and %s already played when the prompt arrived (the hook plays it; do not list it on the Sound line). A blocked "
        "seat (report opens MAJOR PROBLEM FOUND) on any #StandReady-family tick plays %s x3 instead, and after more than "
        "two blocked ticks its loop runs as #StandReadyHigh: the tick that upgrades it adds %s. A seat whose "
        "#StandReadyHigh ticks need the person %d times in a row with no prompt from them is ignored: that tick adds %s, "
        "the loop drops to #StandReadyLow until their next prompt, and while it still needs the person its ticks play %s "
        "alone. A tick whose seat still has questions for the person says so in its report (a line opening 'Questions "
        "for you:' with the count, ending with the seat's page address, or a baton to the person ending with that "
        "address), and sounds each one by its first-line phrase above. Only a parley head surfacing its reports' "
        "questions writes a line opening 'Report questions for you:'; from the second such tick in a row with no prompt "
        "from the person, that tick plays %s instead of its usual sound, at most once every %d minutes across all "
        "sessions. A seat whose parley is delegated to a manager sends its questions and blockers to that manager and "
        "makes no attention sound itself: no decision phrase, no MAJOR PROBLEM FOUND. A reply carrying a [BATON ...] "
        "block to paste ends with %s. Auto-compact plays %s; a seat handing over a compaction prompt plays it only as its "
        "very last act, once the prompt is ready and nothing else is left to do; the Stop hook plays it last by itself "
        "when the reply opens #CompactionPrep or #SmartCompact, or has a line opening 'Type /compact', so do not also "
        "play it mid-turn."),
    # v21: the short line a session gets on every prompt after the first (rules_text full_once or short_always); at most
    # 350 characters, no placeholders. It carries what a seat needs every turn and says where the rest is.
    "prompt_rules_short": (
        "CHIME (full rules: the chime skill). Last line of every reply, exactly: Sound: <sound name> · <SEAT>. The name only, n"
        "ever an explanation: jobs-done after the person's prompt, the loop's sound on a tick, sonar after a peer's message. Only a re"
        "ply's FIRST line sets an alert off: MAJOR PROBLEM FOUND, URGENT or IMPORTANT DECISION NEEDED, RED ALERT."),
    # shown once when a clock-out, mute or silenced-sound notice that an earlier prompt carried no longer holds
    "rules_status_clear": (
        "Earlier chime status notices (clocked out, muted, silenced sounds) no longer apply."),
    "brakes_rules": (
        "BRAKES ON for this session (brakes skill). Do no new work. Finish only the step in hand if stopping mid-way "
        "would leave something broken, then stop. The only loop is #KeepWarm; a #KeepWarm tick does the warm-and-card "
        "step and replies with its one REPLY line. Play no sounds yourself, never call chime play, and open no reply "
        "with a decision phrase or MAJOR PROBLEM FOUND: the Stop hook plays only the brakes sound (and the low-usage "
        "alarm). End every reply with: Sound: brakes \u00b7 <SEAT>. The person lifts this with /brakes off."),
    "ra_base": (
        "RED ALERT: a material risk or deficiency you found yourself, something that will cost money, data, access or "
        "working time if nobody acts soon, or a control or equipment not doing its job. It is about the finding, not "
        "being stuck (MAJOR PROBLEM FOUND) or a decision waiting. To fire, run chime.py the same way as for MAJOR "
        "PROBLEM FOUND with `redalert check --kind <slug>`, then `redalert fire --seat <SEAT> --kind <slug> --title .. "
        "--why .. --evidence ..`, then record the alert where the person will see it (for example on your parley "
        "page), then open the reply RED ALERT only if it has not sounded yet."),
    "ra_merited": " The person ruled merited: ",
    "ra_not_merited": " The person ruled not merited: ",
    "ra_advice_not_merited": "ADVICE do not fire: the person ruled a comparable alert not merited on %s",
    "ra_example_tag": " (example given)",
    "ra_example_note": "example given",
    "ra_default_by": "the person",
}


def itext(key, args=None):
    """The injected text for key: the person's own from config.json "texts", else the default. With args, %-formatted;
    a person's text that does not fit its placeholders falls back to the default."""
    mine = (_C.get("texts") or {}).get(key) if isinstance(_C.get("texts"), dict) else None
    for t in ((mine,) if isinstance(mine, str) else ()) + (DEFAULT_TEXTS[key],):
        try:
            return t if args is None else t % tuple(args)
        except Exception:
            continue
    return ""


FALLBACK_WAV = r"C:\Windows\Media\Windows Notify Messaging.wav"
SOUNDS = {k: _C.get(k) or FALLBACK_WAV for k in
          ("urgent", "important", "boing", "default", "tick", "tick_ready", "tick_high", "tick_low",
           "peer", "compact", "relay", "tick_compaction")}
SOUNDS["done"] = _C.get("done") or SOUNDS["default"]
ACK = _C.get("ack") or ""                      # unset: no sound when a prompt arrives
if ACK:
    SOUNDS["ack"] = ACK
if _C.get("questions"):
    SOUNDS["questions"] = _C["questions"]
if _C.get("low_health"):
    SOUNDS["low_health"] = _C["low_health"]
if _C.get("brakes"):
    SOUNDS["brakes"] = _C["brakes"]
SOUNDS["red_alert"] = _C.get("red_alert") or SOUNDS["urgent"]   # without the key, a red alert sounds as urgent
for _k in ("escalate", "abandon", "ignored"):  # the upgrade to #StandReadyHigh, and the abandoned seat's sounds
    if _C.get(_k):
        SOUNDS[_k] = _C[_k]
_ROOT = os.path.dirname(_CFG_PATH)             # relative sound paths resolve against the skill root
SOUNDS = {k: (v if os.path.isabs(v) else os.path.normpath(os.path.join(_ROOT, v))) for k, v in SOUNDS.items()}
IGNORE_AFTER = int(_C.get("ignore_after_ticks") or 4)   # needy #StandReadyHigh ticks before a seat is ignored


def _alts(key, default):
    """A config list of words as a regex alternation."""
    v = _C.get(key)
    v = [str(x) for x in v if str(x).strip()] if isinstance(v, list) and v else default
    return "|".join(re.escape(x) for x in v)


ADDRESSEES = _alts("question_addressees", ["you"])           # who a "Questions for ..." line is addressed to
QFM_RX = re.compile(r"^\s*(?:[*_>`]+\s*)?(?:Report )?questions for (?:%s)\b" % ADDRESSEES, re.M | re.I)
QUESTIONS_AFTER = 2                            # ticks in a row with questions before the nudge plays
ASKS_RX = re.compile(r"^\s*(?:\*\*)?Report questions for (?:%s)\b" % ADDRESSEES, re.M | re.I)   # parley heads only
DELEGATED_FILE = os.path.join(os.path.expanduser("~"), ".threadops", "parley", "delegated.json")
SILENCE_FILE = os.path.join(CHIME_HOME, "silence.json")          # sounds the person silenced on the soundboard
PRESENCE_FILE = os.path.join(os.path.expanduser("~"), ".threadops", "presence.json")   # the person's clock in / out
QUESTIONS_LAST = os.path.join(CHIME_HOME, "questions_last.json")
QUESTIONS_COOLDOWN = 60 * float(_C.get("questions_cooldown_min") or 120)


def _jload(path):
    try:
        with io.open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def silenced(key):
    """True when the person silenced this sound on the soundboard (keyed by its name, e.g. cricket)."""
    s = _jload(SILENCE_FILE).get("sounds") or {}
    return sound_name(key) in s or key in s


def presence():
    """The person's clock, {"state": "out"|"in", "since": ..., "note": ...}; in when the file is missing."""
    p = _jload(PRESENCE_FILE)
    return p if p.get("state") in ("out", "in") else {"state": "in"}


def clocked_out():
    return presence().get("state") == "out"


def questions_cooldown():
    """Seconds between questions plays; the soundboard's setting wins over the config."""
    try:
        return 60 * float(_jload(SILENCE_FILE).get("questions_cooldown_min") or 0) or QUESTIONS_COOLDOWN
    except Exception:
        return QUESTIONS_COOLDOWN


def questions_due():
    """The questions sound plays at most once per cooldown across the machine."""
    try:
        last = float(_jload(QUESTIONS_LAST).get("ts") or 0)
    except Exception:
        last = 0
    return time.time() - last >= questions_cooldown()


def questions_played():
    try:
        os.makedirs(CHIME_HOME, exist_ok=True)
        with open(QUESTIONS_LAST, "w", encoding="utf-8") as fh:
            json.dump({"ts": time.time()}, fh)
    except Exception:
        pass


# Brakes: the brakes skill writes ~/.threadops/brakes/<session_id>.json; while it exists the Stop hook plays only
# "brakes" (and low_health), the prompt hook plays no ack, and auto-compact is silent.
BRAKES_DIR = os.path.join(os.path.expanduser("~"), ".threadops", "brakes")


def brakes_on(session_id):
    return bool(session_id) and os.path.isfile(os.path.join(BRAKES_DIR, "%s.json" % session_id))



def delegated_to(seat):
    """The manager a seat's parley is delegated to, or None."""
    try:
        with io.open(DELEGATED_FILE, encoding="utf-8") as fh:
            d = json.load(fh)
        return ((d.get(seat or "") or {}).get("to")) or None
    except Exception:
        return None
PEER_PREFIXES = ("<cross-session-message",) + tuple(str(x) for x in (_C.get("peer_prefixes") or []) if str(x))
NOT_PERSON_RX = re.compile(r"^\s*(?:<cross-session-message|<agent-message|<task-notification|<local-command|<command-name>|"
                           r"Another Claude session sent a message"
                           + "".join("|" + re.escape(str(x)) for x in (_C.get("peer_prefixes") or []) if str(x))
                           + "".join("|" + re.escape(str(x)) for x in (_C.get("notification_prefixes") or []) if str(x))
                           + ")", re.I)


def ack_log(data, prompt):
    """One line per ack sound, so a stray one can be traced to its session (no prompt text kept)."""
    try:
        d = os.path.join(tempfile.gettempdir(), "chime")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "ack_log.txt"), "a", encoding="utf-8") as fh:
            fh.write("%s %s %s keys=%s first=%r\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), (data.get("session_id") or "")[:8],
                     os.path.basename(os.path.dirname(data.get("transcript_path") or "")), ",".join(sorted(data)),
                     (prompt or "")[:24]))
    except Exception:
        pass


def direct_request(prompt):
    """True when the prompt is the person's own words: not a tick, a peer message or a notification."""
    p = (prompt or "").strip()
    return bool(p) and not TICK_RX.match(p) and not NOT_PERSON_RX.match(p)


CONTINUATION_RX = re.compile(r"(?:<artifact-content-authored-by-others/>\s*)?(?:This session is being continued from a "
                             r"previous conversation|Continue from where you left off)", re.I)


def system_prompt(data):
    """True for a prompt the person did not type, so the ack sound does not play for it. The hook payload carries no
    origin, so: a continuation after compaction, or a prompt this session's transcript has already recorded as
    scheduled or system-sent (cron prompts repeat verbatim, so a prompt is known from its second firing on)."""
    prompt = (data.get("prompt") or "").strip()
    if CONTINUATION_RX.match(prompt):
        return True
    return bool(prompt) and prompt_key(prompt) in transcript_facts(data.get("transcript_path") or "")["sys"]


def play_detached(key, seat=""):
    """Start the sound in its own process so the hook returns at once. The seat rides along for its volume."""
    global _SEAT
    if DRY or muted():
        _SEAT = seat or _SEAT
        play(key)
        return
    try:
        subprocess.Popen([sys.executable, os.path.abspath(__file__), "sound", key] + ([seat] if seat else []),
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=0x00000008 | 0x00000200, close_fds=True)   # DETACHED_PROCESS | NEW_PROCESS_GROUP
    except Exception:
        pass
TICK_DIR = os.path.expanduser(_C.get("tick_dir") or os.path.join("~", ".reprompt", "scripts"))   # the reprompt scripts
STATE = {}
TICK_SOUND = {"high": "tick_high", "low": "tick_low", "ready": "tick_ready", "keepwarm": "tick",
              "compaction": "tick_compaction"}
FLAGS = {"major": (True, True), "uandi": (True, True), "urgent": (True, False), "important": (False, True)}


def loop_kind(name):
    n = (name or "").lstrip("#").lower()
    if n.startswith("compaction"):
        return "compaction"
    if "warm" in n:          # #KeepWarmHigh and #KeepWarmLow are #KeepWarm ticks, not High/Low ready ticks
        return "keepwarm"
    if n.endswith("high"):
        return "high"
    if n.endswith("low"):
        return "low"
    if n in ("standready", "ready", "stayready", "standreadymid", "readymid", "stayreadymid"):
        return "ready"
    return "keepwarm"


def kw():
    try:
        if TICK_DIR not in sys.path:
            sys.path.insert(0, TICK_DIR)
        sys.dont_write_bytecode = True
        import keepwarm_common
        return keepwarm_common
    except Exception:
        return None


def flag_seq(u, i):
    return (["urgent"] if u else ["default"]) + (["boing", "important"] if i else [])
RELAY_RX = re.compile(r"^\s*\[BATON [A-Z0-9][A-Za-z0-9_-]*\]", re.M)
SOUND_NAMES = _C.get("names", {})            # optional friendly names for the Sound line
SESSIONS_GLOB = _C.get("sessions_glob", "")  # optional: where session name records live
DRY = os.environ.get("CHIME_DRY_RUN") == "1"
DEDUPE_SECONDS = 90
MUTE_FILE = _C.get("mute_file") or os.path.join(os.path.expanduser("~"), ".chime_muted")


ZOOM_MEETING_CLASSES = ("ConfMultiTabContentWndClass", "ZPContentViewWndClass")
_ZOOM = []
# A finished turn holds its toasts back and shows each one with its sound, in the order heard
# so that the notifications come in the same order as the sounds.
_DEFER = {"on": False, "items": []}


def zoom_meeting():
    """True while a Zoom meeting window is open (the mute during a meeting). About 20 ms, cached per run."""
    if _ZOOM:
        return _ZOOM[0]
    hit = False
    try:
        if _C.get("mute_during_zoom", True) and os.name == "nt":
            import ctypes
            import ctypes.wintypes as w
            u, k = ctypes.windll.user32, ctypes.windll.kernel32

            def exe(pid):
                h = k.OpenProcess(0x1000, False, pid)
                if not h:
                    return ""
                buf, n = ctypes.create_unicode_buffer(260), w.DWORD(260)
                ok = k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n))
                k.CloseHandle(h)
                return buf.value.rsplit("\\", 1)[-1].lower() if ok else ""

            # A meeting is open only while the zoom.exe process that owns a meeting-class window also
            # shows a real window (meeting view, minimized meeting, or the screen-share toolbar). Zoom
            # keeps the meeting process and its hidden meeting windows after a call ends; counting
            # those muted every session for hours.
            meeting, shown, names = set(), set(), {}

            @ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
            def cb(hwnd, lp):
                pid = w.DWORD()
                u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                p = pid.value
                if p not in names:
                    names[p] = exe(p)
                if names[p] != "zoom.exe":
                    return True
                cls = ctypes.create_unicode_buffer(256)
                u.GetClassNameW(hwnd, cls, 256)
                if cls.value in ZOOM_MEETING_CLASSES:
                    meeting.add(p)
                if u.IsWindowVisible(hwnd):
                    r = w.RECT()
                    u.GetWindowRect(hwnd, ctypes.byref(r))
                    if (r.right - r.left) * (r.bottom - r.top) >= 2000:
                        shown.add(p)
                return True

            u.EnumWindows(cb, 0)
            hit = bool(meeting & shown)
    except Exception:
        hit = False
    _ZOOM.append(hit)
    return hit


def muted():
    try:
        return os.path.exists(MUTE_FILE) or zoom_meeting() or clocked_out()
    except Exception:
        return False


# Sounds wait while the person dictates, so no alert or spoken seat name lands in a dictation transcript.
HOLD = bool(_C.get("hold_during_dictation", True))
DICTATION_APPS = tuple(str(a).lower() for a in (_C.get("dictation_apps") or ["wispr flow"]))
HOLD_MAX = float(_C.get("dictation_hold_max_s") or 300)
HOLD_SETTLE = 0.6
HOLD_LOG = os.path.join(CHIME_HOME, "hold_log.txt")       # not %TEMP%/chime: that folder is swept hourly


def capture_sessions():
    """[(exe name, state)] for every session on every active microphone endpoint; state 1 means recording now.
    Plain ctypes over the Windows audio session API: no package to install, a few milliseconds."""
    import ctypes
    import ctypes.wintypes as w
    ole, k = ctypes.windll.ole32, ctypes.windll.kernel32
    P, PP = ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)

    class GUID(ctypes.Structure):
        _fields_ = [("a", w.DWORD), ("b", w.WORD), ("c", w.WORD), ("d", ctypes.c_ubyte * 8)]

    clsid_from = ole.CLSIDFromString
    clsid_from.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p]
    create = ole.CoCreateInstance
    create.argtypes = [ctypes.c_void_p, ctypes.c_void_p, w.DWORD, ctypes.c_void_p, PP]
    open_process = k.OpenProcess
    open_process.restype = ctypes.c_void_p
    open_process.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    image_name = k.QueryFullProcessImageNameW
    image_name.argtypes = [ctypes.c_void_p, w.DWORD, ctypes.c_wchar_p, ctypes.POINTER(w.DWORD)]
    close = k.CloseHandle
    close.argtypes = [ctypes.c_void_p]

    def guid(s):
        g = GUID()
        clsid_from(s, ctypes.byref(g))
        return g

    def call(ptr, index, types, *args):
        vt = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *types)(vt[index])(ptr, *args)

    names = {}

    def exe(pid):
        if pid not in names:
            name = ""
            h = open_process(0x1000, False, pid)
            if h:
                buf, n = ctypes.create_unicode_buffer(520), w.DWORD(520)
                if image_name(h, 0, buf, ctypes.byref(n)):
                    name = buf.value.rsplit("\\", 1)[-1].lower()
                close(h)
            names[pid] = name
        return names[pid]

    out = []
    ole.CoInitializeEx(None, 0)
    clsid, iid_en = guid("{BCDE0395-E52F-467C-8E3D-C4579291692E}"), guid("{A95664D2-9614-4F35-A746-DE8DB63617E6}")
    iid_mgr, iid_c2 = guid("{77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F}"), guid("{BFB7FF88-7239-4FC9-8FA2-07C950BE9C6D}")
    en, col = P(), P()
    if create(ctypes.byref(clsid), None, 23, ctypes.byref(iid_en), ctypes.byref(en)) != 0 or not en:
        return out
    # IMMDeviceEnumerator.EnumAudioEndpoints(eCapture, DEVICE_STATE_ACTIVE)
    if call(en, 3, (ctypes.c_int, w.DWORD, PP), 1, 1, ctypes.byref(col)) == 0 and col:
        nd = ctypes.c_uint()
        call(col, 3, (ctypes.POINTER(ctypes.c_uint),), ctypes.byref(nd))
        for d in range(nd.value):
            dev, mgr, se = P(), P(), P()
            if call(col, 4, (ctypes.c_uint, PP), d, ctypes.byref(dev)) != 0 or not dev:
                continue
            # IMMDevice.Activate(IAudioSessionManager2), then IAudioSessionManager2.GetSessionEnumerator
            if call(dev, 3, (ctypes.c_void_p, w.DWORD, ctypes.c_void_p, PP),
                    ctypes.byref(iid_mgr), 23, None, ctypes.byref(mgr)) == 0 and mgr:
                if call(mgr, 5, (PP,), ctypes.byref(se)) == 0 and se:
                    ns = ctypes.c_int()
                    call(se, 3, (ctypes.POINTER(ctypes.c_int),), ctypes.byref(ns))
                    for i in range(ns.value):
                        s, s2 = P(), P()
                        if call(se, 4, (ctypes.c_int, PP), i, ctypes.byref(s)) != 0 or not s:
                            continue
                        st, pid = ctypes.c_int(), w.DWORD()
                        call(s, 3, (ctypes.POINTER(ctypes.c_int),), ctypes.byref(st))          # GetState
                        if call(s, 0, (ctypes.c_void_p, PP), ctypes.byref(iid_c2), ctypes.byref(s2)) == 0 and s2:
                            call(s2, 14, (ctypes.POINTER(w.DWORD),), ctypes.byref(pid))        # GetProcessId
                            call(s2, 2, ())
                        call(s, 2, ())
                        out.append((exe(pid.value) if pid.value else "", st.value))
                    call(se, 2, ())
                call(mgr, 2, ())
            call(dev, 2, ())
        call(col, 2, ())
    call(en, 2, ())
    return out


def dictating():
    """True while a dictation app is recording from a microphone. Never cached: it changes within a run."""
    fake = os.environ.get("CHIME_FAKE_DICTATING")
    if fake in ("0", "1"):
        return fake == "1"
    try:
        if not HOLD or os.name != "nt":
            return False
        return any(st == 1 and name.startswith(DICTATION_APPS) for name, st in capture_sessions())
    except Exception:
        return False


def hold_for_dictation():
    """Wait while the person dictates, at most HOLD_MAX seconds, then a short settle. Returns the seconds waited."""
    if DRY or not HOLD:
        return 0.0
    t0, held = time.time(), False
    while time.time() - t0 < HOLD_MAX and dictating():
        held = True
        time.sleep(0.4)
    if not held:
        return 0.0
    time.sleep(HOLD_SETTLE)
    return time.time() - t0


USAGE_SERVER = _C.get("usage_server") or ""                # a python file that offers fetch_raw() or fetch_usage(); none: no alarm
USAGE_ALERT_PCT = float(_C.get("usage_alert_pct", 90))     # within 10% of a limit
USAGE_CACHE_SECONDS = 300
USAGE_ALERT_EVERY = 60 * float(_C.get("usage_alert_every_min", 30))


def reset_iso(v):
    """A payload reset time (ISO 8601 text, or epoch seconds) as local "YYYY-MM-DDTHH:MM:SS", or None."""
    try:
        if isinstance(v, bool) or v is None:
            return None
        if isinstance(v, (int, float)):
            dt = datetime.datetime.fromtimestamp(v / 1000.0 if v > 1e11 else float(v))
        else:
            dt = datetime.datetime.fromisoformat(str(v).strip().replace("Z", "+00:00")).astimezone()
            dt = dt.replace(tzinfo=None)
        return dt.strftime("%Y-%m-%dT%H:%M:%S")
    except Exception:
        return None


def reset_utc(v):
    """A payload reset time as UTC "YYYY-MM-DDTHH:MM:SSZ", or None (v21). A naive time is taken as local, as reset_iso does."""
    try:
        if isinstance(v, bool) or v is None:
            return None
        if isinstance(v, (int, float)):
            dt = datetime.datetime.fromtimestamp(v / 1000.0 if v > 1e11 else float(v)).astimezone()
        else:
            dt = datetime.datetime.fromisoformat(str(v).strip().replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.astimezone()
        return dt.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return None


def _numeric(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def usage_values(mod, resets=None, extra=None):
    """[(label, pct)] for every limit the usage endpoint reports. The shaped fetch_usage() keeps only the 5-hour and
    all-model weekly figures, so a per-model weekly limit (the endpoint's "limits" list) and the monthly extra-usage
    spend would never reach the alarm: read the raw payload when the server offers it.

    v21: with `extra` (a dict) the raw payload's other facts are put in it, for the cache file: "five_hour" (None when
    the payload says no window is open, a dict with the percent and the reset times when one is; absent when the
    payload does not say), "extra_usage" ({"enabled": False}, or enabled with used, limit, pct, currency, limit_reached
    where the payload has them; absent when the payload does not say), "extra_usage_pct", and "resets_utc" (every reset
    time in `resets`, as UTC). Nothing about the returned list or `resets` changes."""
    vals = []
    raw = None
    utc = {}
    if hasattr(mod, "fetch_raw"):
        try:
            raw = mod.fetch_raw()
        except Exception:
            raw = None
    if isinstance(raw, dict) and not raw.get("error"):
        for k, lbl in (("five_hour", "5-hour"), ("seven_day", "weekly")):
            v = (raw.get(k) or {}).get("utilization")
            if v is not None:
                vals.append((lbl, float(v)))
                if isinstance(resets, dict):         # the server's own five_hour / seven_day "resets_at"
                    r = reset_iso((raw.get(k) or {}).get("resets_at"))
                    if r:
                        resets[lbl] = r
                        utc[lbl] = reset_utc((raw.get(k) or {}).get("resets_at"))
        if isinstance(extra, dict) and "five_hour" in raw:
            fh = raw.get("five_hour")
            if isinstance(fh, dict) and _numeric(fh.get("utilization")) is not None:
                w = {"pct": _numeric(fh["utilization"])}
                if reset_iso(fh.get("resets_at")):
                    w["resets"], w["resets_utc"] = reset_iso(fh.get("resets_at")), reset_utc(fh.get("resets_at"))
                extra["five_hour"] = w
            else:
                extra["five_hour"] = None            # an explicit "no window is open", unlike a field that is missing
        for lim in raw.get("limits") or []:
            if not isinstance(lim, dict):
                continue
            if isinstance(resets, dict) and str(lim.get("kind") or lim.get("type") or "").lower() in ("session", "five_hour") \
                    and "5-hour" not in resets and reset_iso(lim.get("resets_at")):
                resets["5-hour"] = reset_iso(lim.get("resets_at"))      # the 5-hour reset when only limits[] carries it
                utc["5-hour"] = reset_utc(lim.get("resets_at"))
            if lim.get("percent") is None:
                continue
            model = (((lim.get("scope") or {}).get("model") or {}).get("display_name")) or ""
            if model:
                vals.append(("%s weekly" % model, float(lim["percent"])))
                if isinstance(resets, dict):         # not confirmed for this list; kept only when an entry carries it
                    r = reset_iso(lim.get("resets_at"))
                    if r:
                        resets["%s weekly" % model] = r
                        utc["%s weekly" % model] = reset_utc(lim.get("resets_at"))
        ex = raw.get("extra_usage") or {}
        if ex.get("is_enabled") and ex.get("utilization") is not None:
            vals.append(("monthly extra-usage spend", float(ex["utilization"])))
        if isinstance(extra, dict) and "extra_usage" in raw:
            if isinstance(raw.get("extra_usage"), dict) and raw["extra_usage"].get("is_enabled"):
                e = raw["extra_usage"]
                dp = e.get("decimal_places") if isinstance(e.get("decimal_places"), int) and not isinstance(e.get("decimal_places"), bool) \
                    and 0 <= e.get("decimal_places") <= 6 else 2
                out = {"enabled": True}
                if _numeric(e.get("used_credits")) is not None:
                    out["used"] = round(_numeric(e["used_credits"]) / 10 ** dp, dp)
                if _numeric(e.get("monthly_limit")) is not None:
                    out["limit"] = round(_numeric(e["monthly_limit"]) / 10 ** dp, dp)
                if _numeric(e.get("utilization")) is not None:
                    out["pct"] = _numeric(e["utilization"])
                    extra["extra_usage_pct"] = out["pct"]
                if isinstance(e.get("currency"), str) and e["currency"]:
                    out["currency"] = e["currency"]
                if isinstance(e.get("spend_limit_reached"), bool):
                    out["limit_reached"] = e["spend_limit_reached"]
                extra["extra_usage"] = out
            else:
                extra["extra_usage"] = {"enabled": False}
        if isinstance(extra, dict):
            extra["resets_utc"] = {k: v for k, v in utc.items() if v}
        return vals
    u = mod.fetch_usage(refresh=True)
    if u and not u.get("error"):
        for k, lbl in (("session_pct", "5-hour"), ("weekly_pct", "weekly")):
            if u.get(k) is not None:
                vals.append((lbl, float(u[k])))
        for b in u.get("model_breakdowns") or []:
            if b.get("pct") is not None:
                vals.append(("%s weekly" % b.get("model"), float(b["pct"])))
    return vals


def cache_extras(now, extra):
    """The v21 additions to the usage cache file; the keys written before v21 (vals, at, resets, folder, home) are
    untouched, so a reader of the old format still reads the new file. schema 2. at_utc and at_offset give `at` (which
    stays local time with no zone) its zone; resets_utc is every reset time as UTC; five_hour is null when no 5-hour
    window is open and absent when the reading did not say; extra_usage says on or off with the dollars used and the
    dollar limit; extra_usage_pct is the percent of the monthly limit (the vals entry "monthly extra-usage spend"
    holds the same number under its old name, which misleads, and stays for the readers that use it)."""
    out = {"schema": 2}
    try:
        dt = datetime.datetime.fromtimestamp(now).astimezone()
        z = dt.strftime("%z")
        out["at_utc"] = dt.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        out["at_offset"] = (z[:3] + ":" + z[3:]) if len(z) == 5 else z
    except Exception:
        pass
    for k in ("resets_utc", "five_hour", "extra_usage", "extra_usage_pct"):
        if k in extra:
            out[k] = extra[k]
    return out


def account_home():
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")


def folder_of(home):
    """The account folder a config home belongs to (the parent of a trailing "home", else the last part)."""
    parts = [x for x in re.split(r"[\\/]+", home or "") if x]
    return parts[-2] if len(parts) >= 2 and parts[-1].lower() == "home" else (parts[-1] if parts else "")


def account_folder():
    return folder_of(account_home())


def color_of(folder):
    return (_C.get("account_names") or {}).get(folder) or folder


def account_name():
    """The account home's colour from chime.json "account_names" (keyed by the home's folder name), else the folder."""
    return color_of(account_folder())


def cache_tags(home):
    """The cache tags of one home path. A path written with backslashes and the same path with forward slashes (or a
    trailing separator) must not give two caches and two played markers. The first tag is the one for the path as given,
    and it is the one written; all are read."""
    out = []
    base = home.rstrip("\\/") or home
    for h in (home, base, base + "\\", base + "/"):
        for v in (h, h.replace("\\", "/"), h.replace("/", "\\")):
            t = hashlib.sha1(v.lower().encode("utf-8")).hexdigest()[:10]
            if t not in out:
                out.append(t)
    return out


def _newest(folder, prefix, tags, suffix=""):
    """The existing file among <prefix><tag><suffix> with the latest modified time (a future time counts), or None."""
    best, bt = None, None
    for t in tags:
        p = os.path.join(folder, "%s%s%s" % (prefix, t, suffix))
        try:
            m = os.path.getmtime(p)
        except OSError:
            continue
        if bt is None or m > bt:
            best, bt = p, m
    return best


def now_iso(t=None):
    return datetime.datetime.fromtimestamp(time.time() if t is None else t).strftime("%Y-%m-%dT%H:%M:%S")


def parse_local(s):
    """"YYYY-MM-DDTHH:MM:SS" or "YYYY-MM-DD HH:MM[:SS]" as a naive local datetime, or None."""
    try:
        return datetime.datetime.fromisoformat(str(s).strip().replace("Z", ""))
    except Exception:
        return None


def mute_entries():
    """{account folder (lower case): entry} from usage_mute.json; {} when missing or unreadable."""
    a = _jload(USAGE_MUTE_FILE).get("accounts")
    return a if isinstance(a, dict) else {}


def entry_live(e, now=None):
    u = parse_local((e or {}).get("until")) if isinstance(e, dict) else None
    return bool(u and u > (now or datetime.datetime.now()))


def account_mute(folder):
    """This account's live mute entry, or None. An expired entry is ignored here and dropped at the next write."""
    try:
        e = mute_entries().get((folder or "").lower())
        return e if entry_live(e) else None
    except Exception:
        return None


USAGE_LOG = os.path.join(CHIME_HOME, "usage_log.txt")
USAGE_LOG_FROM = float(_C.get("usage_log_from_pct", 70))


def _usage_log(decision, vals=None):
    """Why an alarm did or did not sound. One short line; the file is cut back when it passes 60 KB."""
    try:
        os.makedirs(CHIME_HOME, exist_ok=True)
        top = ", ".join("%s %.0f%%" % (l, float(v)) for l, v in (vals or []) if v is not None) or "no values"
        with open(USAGE_LOG, "a", encoding="utf-8") as fh:
            fh.write("%s | %s | %s | %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), account_name() or "?", decision, top))
        if os.path.getsize(USAGE_LOG) > 60000:
            with open(USAGE_LOG, encoding="utf-8", errors="replace") as fh:
                keep = fh.readlines()[-300:]
            with open(USAGE_LOG, "w", encoding="utf-8") as fh:
                fh.writelines(keep)
    except Exception:
        pass


def usage_alert():
    """(label, pct) when this account's 5-hour or weekly usage is at or above the alert line, else None.

    Reads the account's own usage through the module named by "usage_server" (CLAUDE_CONFIG_DIR picks the account),
    cached five minutes per account, and fires at most once per USAGE_ALERT_EVERY per account. With no usage_server
    there is no alarm.
    A muted turn does not use the alarm up, and readings and decisions are logged (_usage_log).
    """
    try:
        home = account_home()
        tags = cache_tags(home)                      # both spellings of the path find the same files
        tag = tags[0]
        d = os.path.join(tempfile.gettempdir(), "chime")
        os.makedirs(d, exist_ok=True)
        cache, fired = os.path.join(d, "usage_%s.json" % tag), os.path.join(d, "usage_fired_%s" % tag)
        failed = os.path.join(d, "usage_failed_%s" % tag)
        cache_r = _newest(d, "usage_", tags, ".json") or cache
        fired_r = _newest(d, "usage_fired_", tags) or fired     # a future-dated marker (a stopgap mute) counts as played
        failed_r = _newest(d, "usage_failed_", tags) or failed
        now = time.time()
        u, fresh = None, False
        if os.path.exists(cache_r) and now - os.path.getmtime(cache_r) < USAGE_CACHE_SECONDS:
            u = json.load(open(cache_r, encoding="utf-8"))
        elif os.path.exists(USAGE_SERVER):
            import importlib.util
            spec = importlib.util.spec_from_file_location("chime_usage_server", USAGE_SERVER)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            resets, extra = {}, {}
            u, fresh = {"vals": usage_values(mod, resets, extra)}, True
            if u["vals"]:                            # the cache also keeps when each limit resets, and when it was read
                u.update({"at": now_iso(now), "resets": resets, "folder": folder_of(home), "home": home})
                u.update(cache_extras(now, extra))
                with open(cache, "w", encoding="utf-8") as fh:
                    json.dump(u, fh)
            elif not (os.path.exists(failed_r) and now - os.path.getmtime(failed_r) < 900):
                open(failed, "w").write(str(now))
                _usage_log("reading failed or came back empty: no alarm is possible")
        if not u or u.get("error") or "vals" not in u or not u["vals"]:
            return None
        vals = u["vals"]
        hits = [(lbl, float(pct)) for lbl, pct in vals if pct is not None and float(pct) >= USAGE_ALERT_PCT]
        if not hits:
            if fresh and max([float(pct) for _, pct in vals if pct is not None] or [0]) >= USAGE_LOG_FROM:
                _usage_log("below the %.0f%% line: no alarm" % USAGE_ALERT_PCT, vals)
            return None
        am = account_mute(folder_of(home))          # this account's alarm muted (usage mute); nothing sounds or toasts
        if am:
            if fresh:
                _usage_log("at or above the line but this account's alarm is muted until %s (by %s)"
                           % (str(am.get("until")).replace("T", " ")[:16], am.get("by") or "?"), vals)
            return None
        if muted():
            if fresh:
                _usage_log("at or above the line but chime is muted: alarm kept for the first unmuted turn", vals)
            return None
        if os.path.exists(fired_r) and now - os.path.getmtime(fired_r) < USAGE_ALERT_EVERY:
            if fresh:
                _usage_log("at or above the line: alarm already played in the last %.0f min" % (USAGE_ALERT_EVERY / 60), vals)
            return None
        open(fired, "w").write(str(now))
        _usage_log("ALARM PLAYED", vals)
        return max(hits, key=lambda h: h[1])
    except Exception:
        return None

TICK_RX = re.compile(r"^\s*#(StandReady(?:Low|High)?|KeepWarm(?:High|Low)?|StayWarm(?:High|Low)?|Warm(?:High|Low)?|StandReadyMid|Ready(?:Low|High|Mid)?|StayReady(?:Low|High|Mid)?|KeepClaudeWarm|CompactionForm)\b")


def _rx(key, template):
    """A regex built from a config pattern (template has one %s for it), or None when the key is unset or not a regex."""
    try:
        pat = _C.get(key)
        return re.compile(template % pat) if isinstance(pat, str) and pat.strip() else None
    except Exception:
        return None


# a seat id in the text ("Sent by X", "[X]", "seat X"): only when the person's config names the shape of their seat ids
SEAT_RX = _rx("seat_id_regex", r"(?:Sent by |\[|seat )(%s)\b")
# a seat handing over a compaction prompt plays the compact sound only as its very last act
COMPACT_RX = re.compile(r"(?im)^\s*(?:[*_>`]+\s*)?type\s+/compact\b")
SOUND_LINE_RX = re.compile(r"^\s*Sound:\s*(?P<body>.+?)\s*(?:\u00b7|\s\.\s)\s*(?P<seat>[A-Za-z][A-Za-z0-9_-]{2,})\s*$")
OPENERS = (("major problem found", "major"),
           ("urgent and important", "uandi"),
           ("urgent + important", "uandi"),
           ("urgent decision needed", "urgent"),
           ("important decision needed", "important"),
           ("decision needed", "important"))
PS = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
APP_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"

def _rules():
    """The per-turn rules, plus the short RED ALERT paragraph; any error there leaves the rules as they were."""
    base = _rules_base()
    try:
        add = ra_paragraph()
    except Exception:
        add = ""
    return base + (" " + add if add else "")


def _rules_base():
    head, clock, tail, _muted, _grid = _rules_pieces()
    return head + clock + tail


# ---- v21: the per-turn rules once, then one short line (config "rules_text") ----------------------------------------
RULES_MODES = ("full_once", "full_always", "short_always")
RULES_SEEN_DIR = os.path.join(CHIME_HOME, "rules_seen")


def rules_mode():
    """full_once (the default: the whole block on a session's first prompt and on the first prompt after each compaction,
    one short line otherwise), full_always (the block on every prompt, as before v21) or short_always. Any other value
    is the default."""
    m = _C.get("rules_text")
    return m if m in RULES_MODES else "full_once"


def _hash(s):
    return hashlib.sha1((s or "").encode("utf-8")).hexdigest()[:16]


def _seen_path(sid):
    return os.path.join(RULES_SEEN_DIR, re.sub(r"[^A-Za-z0-9_.-]+", "-", str(sid))[:100] + ".json")


def _count_compactions(tp, count, offset):
    """(compactions, offset): the isCompactSummary records of the transcript (the generator's own count), found
    incrementally over complete lines past the stored offset. (None, None) when the transcript cannot be read."""
    try:
        if not tp or not os.path.isfile(tp):
            return None, None
        size = os.path.getsize(tp)
        if (not isinstance(offset, int) or isinstance(offset, bool) or offset < 0 or offset > size
                or not isinstance(count, int) or isinstance(count, bool)):
            count, offset = 0, 0                     # no usable record, or the file was rewritten: count from the start
        with open(tp, "rb") as fh:
            fh.seek(offset)
            chunk = fh.read()
        cut = chunk.rfind(b"\n")
        if cut < 0:
            return count, offset
        for line in chunk[:cut + 1].split(b"\n"):
            if b"isCompactSummary" in line:
                try:
                    if json.loads(line).get("isCompactSummary"):
                        count += 1
                except Exception:
                    pass
        return count, offset + cut + 1
    except Exception:
        return None, None


def _save_seen(path, state):
    """Write the per-session state; True when it is on disk. A replace that a sync client or a scanner holds up for a
    moment is tried again, then the file is written in place; only when both fail is it False (the caller then gives the
    full rules, so a session never goes without them)."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except Exception:
        return False
    tmp = path + ".%d.tmp" % os.getpid()
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh)
        for i in range(4):
            try:
                os.replace(tmp, path)
                return True
            except OSError:
                time.sleep(0.03)
    except Exception:
        pass
    try:
        if os.path.exists(tmp):
            os.remove(tmp)
    except Exception:
        pass
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(state, fh)
        return True
    except Exception:
        return False


def rules_for_prompt(data):
    """The text the prompt hook injects. full_always is today's: the whole block every time. full_once keeps a small
    state file per session in the chime home (rules_seen/<session id>.json): the whole block when there is none (a new
    session), when the transcript shows a compaction since the last print, or when the part that comes from config
    changed; otherwise the short line, plus the clock-out / mute / silenced notice or the RED ALERT paragraph only when
    it differs from what the session was last shown. Anything that goes wrong gives the whole block."""
    mode = rules_mode()
    if mode == "full_always":
        return _rules()
    try:
        head, clock, tail, is_muted, grid = _rules_pieces()
        try:
            ra = ra_paragraph()
        except Exception:
            ra = ""
        full = head + clock + tail + (" " + ra if ra else "")
        core = head + grid                                  # changes with config or the soundboard, never with the clock or a mute
        dyn = (clock + (tail if is_muted else "")).strip()  # clocked out or in, silenced sounds, muted
        short = itext("prompt_rules_short")
        if mode == "short_always":
            return short + (" " + dyn if dyn else "")
        sid = (data or {}).get("session_id") or ""
        if not sid:
            return full
        path = _seen_path(sid)
        st = _jload(path)
        st = st if isinstance(st, dict) else {}
        count, offset = _count_compactions((data or {}).get("transcript_path") or "", st.get("compactions"), st.get("offset"))
        new = {"core": _hash(core), "dyn": _hash(dyn), "dyn_on": bool(dyn), "ra": _hash(ra),
               "compactions": count, "offset": offset, "at": now_iso()}
        grown = (isinstance(count, int) and isinstance(st.get("compactions"), int) and count > st["compactions"])
        first = not st or st.get("core") != new["core"] or grown
        if not _save_seen(path, new):
            return full                                      # nothing remembered: never leave a session without the rules
        if first:
            return full
        parts = [short]
        if st.get("dyn") != new["dyn"]:
            if dyn:
                parts.append(dyn)
            elif st.get("dyn_on"):
                parts.append(itext("rules_status_clear"))
        if ra and st.get("ra") != new["ra"]:
            parts.append(ra)
        return " ".join(parts)
    except Exception:
        return _rules()


def _rules_pieces():
    """(head, clock, tail, muted, grid): the per-turn rules in the pieces that change at different speeds. head + clock +
    tail is exactly the text the hook has always injected (before the RED ALERT paragraph); tail is the muted notice while
    muted and the sound grid otherwise, and grid is the grid either way."""
    n = lambda k: SOUND_NAMES.get(k) or k
    head = itext("prompt_rules", (sys.executable, os.path.abspath(__file__)))
    pr = presence()
    clock = ""
    if pr.get("state") == "out":                 # the person clocked out on the soundboard
        clock = itext("clock_out", (pr.get("since") or "an unknown time", (" (" + pr["note"] + ")") if pr.get("note") else ""))
    elif pr.get("since"):
        try:
            back = time.time() - time.mktime(time.strptime(pr["since"][:16], "%Y-%m-%d %H:%M")) < 7200
        except Exception:
            back = False
        if back:
            clock = itext("clock_in", (pr["since"],))
    quiet = sorted((_jload(SILENCE_FILE).get("sounds") or {}).keys())
    if quiet:
        clock += itext("silenced", (", ".join(quiet),))
    grid = itext("grid", (n("urgent"), n("default"), n("boing"), n("important"), n("urgent"),
                          n("boing"), n("important"), n("tick"), n("tick_high"), n("tick_low"),
                          n("peer"), n("done"), n("ack"), n("urgent"), n("escalate"), IGNORE_AFTER,
                          n("abandon"), n("ignored"), n("questions"), int(questions_cooldown() // 60),
                          n("relay"), n("compact")))
    if muted():
        return head, clock, itext("muted", ("%s" % (itext("person_clocked_out") if clocked_out() else
                                                     "a Zoom meeting is open" if zoom_meeting() else MUTE_FILE + " exists"),)), True, grid
    return head, clock, grid, False, grid


def sound_name(key):
    if key in SOUND_NAMES:
        return SOUND_NAMES[key]
    base = os.path.splitext(os.path.basename(SOUNDS.get(key, "") or ""))[0]
    return base or key


def ps(script):
    try:
        subprocess.run([PS, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
                       timeout=20, capture_output=True, creationflags=0x08000000)   # CREATE_NO_WINDOW
    except Exception:
        pass


def q(s):
    return (s or "").replace("'", "''").replace("\r", " ").replace("\n", " ")[:200]


def toast(title, body):
    if _DEFER["on"]:
        _DEFER["items"].append((title, body))
        return
    silent = muted()
    if DRY:
        print("TOAST%s %s | %s" % (" (silent)" if silent else "", title, body))
        return
    ps("[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null;"
       "$t = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
       "$x = $t.GetElementsByTagName('text'); $x.Item(0).AppendChild($t.CreateTextNode('%s')) > $null; $x.Item(1).AppendChild($t.CreateTextNode('%s')) > $null;"
       "%s"
       "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('%s').Show([Windows.UI.Notifications.ToastNotification]::new($t))"
       % (q(title), q(body),
          "$a = $t.CreateElement('audio'); $a.SetAttribute('silent', 'true'); $t.DocumentElement.AppendChild($a) > $null;"
          if silent else "", APP_ID))


SPEAK = (_C.get("speak_names") or "attention").lower()
SPOKEN = _C.get("spoken_names") or {}
WORDS = dict(_C.get("words") or {})              # upper-case token -> the words to say ("" says nothing); the person's own
SUFFIX_RX = _rx("seat_suffix_regex", "%s")      # a suffix of the title that is not read aloud, e.g. a provider tag


def spoken(label):
    """The words for a session name: the seat's own choice in <chime home>/spoken/<title>.txt, then
    chime.json spoken_names, else the title read token by token."""
    try:
        own = os.path.join(CHIME_HOME, "spoken",
                           re.sub(r"[^A-Za-z0-9_.-]+", "-", label or "") + ".txt")
        if os.path.exists(own):
            w = open(own, encoding="utf-8").read().strip()[:80]
            if w:
                return w
    except Exception:
        pass
    if label in SPOKEN:
        return SPOKEN[label]
    out = []
    for tok in re.split(r"[\s_\-/.]+", SUFFIX_RX.sub("", label or "") if SUFFIX_RX else (label or "")):
        if not tok:
            continue
        w = WORDS.get(tok.upper())
        if w is not None:
            out.append(w)
        elif tok.isupper() and len(tok) <= 3:
            out.append(" ".join(tok))
        else:
            out.append(tok.lower() if tok.isupper() else tok)
    return " ".join(x for x in out if x)[:80]


VOICE_DIR = CHIME_HOME
VOICES_FILE = os.path.join(VOICE_DIR, "voices.json")
CLIP_DIR = os.path.join(VOICE_DIR, "clips")
VOICE_POOL = _C.get("voice_pool") or [
    "en-US-GuyNeural", "en-GB-RyanNeural", "en-US-AriaNeural", "en-AU-NatashaNeural",
    "en-GB-SoniaNeural", "en-US-JennyNeural", "en-IE-ConnorNeural", "en-CA-ClaraNeural",
    "en-US-ChristopherNeural", "en-IN-NeerjaNeural", "en-NZ-MitchellNeural", "en-ZA-LeahNeural",
    # more adult English voices that edge-tts lists, so that many seats can each have their own
    "en-AU-WilliamMultilingualNeural", "en-CA-LiamNeural", "en-GB-LibbyNeural", "en-GB-ThomasNeural", "en-IE-EmilyNeural",
    "en-IN-PrabhatNeural", "en-NZ-MollyNeural", "en-ZA-LukeNeural", "en-US-EricNeural", "en-US-MichelleNeural",
    "en-US-RogerNeural", "en-US-SteffanNeural", "en-US-AndrewNeural", "en-US-AvaNeural", "en-US-BrianNeural",
    "en-US-EmmaNeural", "en-SG-WayneNeural", "en-SG-LunaNeural", "en-PH-JamesNeural", "en-PH-RosaNeural",
    "en-KE-ChilembaNeural", "en-NG-AbeoNeural", "en-NG-EzinneNeural", "en-HK-SamNeural"]


def seat_voice(label):
    """The seat's own neural voice, picked at random the first time it speaks and never reassigned.
    <chime home>/voices.json maps tab title to voice; a new seat prefers a voice no other seat holds."""
    import random
    lock = VOICES_FILE + ".lock"
    os.makedirs(VOICE_DIR, exist_ok=True)
    fd = None
    for _ in range(40):                              # two hooks can assign at once; one writer at a time
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(lock) > 10:
                    os.remove(lock)                  # stale lock from a killed hook
            except OSError:
                pass
            time.sleep(0.05)
    try:
        try:
            held = json.load(open(VOICES_FILE, encoding="utf-8"))
        except Exception:
            held = {}
        if held.get(label):
            return held[label]
        free = [v for v in VOICE_POOL if v not in held.values()] or list(VOICE_POOL)
        held[label] = random.choice(free)
        tmp = VOICES_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(held, f, indent=1, sort_keys=True)
        os.replace(tmp, VOICES_FILE)
        return held[label]
    finally:
        if fd is not None:
            os.close(fd)
            try:
                os.remove(lock)
            except OSError:
                pass


def voice_clip(words, voice):
    """The cached mp3 of these words in this voice, rendered once with edge-tts (needs the internet only
    then). None when edge-tts is missing or the render fails, so the caller falls back to System.Speech."""
    # neural voices spell out capitals of 3+ letters (LAB -> L A B); keep caps only for 2-letter acronyms
    text = " ".join(w.capitalize() if w.isupper() and len(w) > 2 else w for w in words.split())
    path = os.path.join(CLIP_DIR, hashlib.sha1(("%s|%s" % (voice, text)).encode("utf-8")).hexdigest()[:16] + ".mp3")
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    try:
        import asyncio
        import edge_tts
        os.makedirs(CLIP_DIR, exist_ok=True)
        tmp = path + ".part"
        asyncio.run(asyncio.wait_for(edge_tts.Communicate(text, voice, rate="+10%").save(tmp), 12))
        if os.path.getsize(tmp) > 0:
            os.replace(tmp, path)
            return path
    except Exception:
        pass
    return None


def speak(label):
    """Say the session's name after the sounds. Silent when muted or off. In the seat's own neural voice, falling back
    to the built-in Windows voice."""
    if SPEAK == "off" or not label:
        return
    words = spoken(label)
    if not words:
        return
    if muted():
        if DRY:
            print("MUTED SAY %s" % words)
        return
    try:
        voice = seat_voice(label)
    except Exception:
        voice = ""
    vol = head_gain(label)
    if DRY:
        print("SAY %s (%s) vol %s%s" % (words, voice or "windows", vol, " head" if is_head(label) else ""))
        return
    clip = voice_clip(words, voice) if voice else None
    if clip:
        ps("Add-Type -AssemblyName PresentationCore; $p = New-Object System.Windows.Media.MediaPlayer; $p.Open([uri]'%s'); $p.Volume = %s; $p.Play();"
           "$i = 0; while (-not $p.NaturalDuration.HasTimeSpan -and $i -lt 30) { Start-Sleep -Milliseconds 100; $i++ };"
           "$s = 3; if ($p.NaturalDuration.HasTimeSpan) { $s = [Math]::Min(10, $p.NaturalDuration.TimeSpan.TotalSeconds + 0.3) }; Start-Sleep -Seconds $s; $p.Close()"
           % (q(clip), vol))
        return
    ps("Add-Type -AssemblyName System.Speech; $v = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
       "$v.Rate = 0; $v.Volume = 100; $v.Speak('%s'); $v.Dispose()" % q(words))


HEADS_FILE = os.path.join(CHIME_HOME, "heads.json")
NORMAL_VOLUME = 0.5                              # System.Windows.Media.MediaPlayer's own default
HEAD_GAIN = float(_C.get("head_gain") or 1.2)    # a parley head sounds this much louder
try:                                             # the person, 2026-11-24: "play the red alert at 150% of normal volume. Same rule for all sessions"
    RED_ALERT_GAIN = float(_C.get("red_alert_gain") or 1.5)
except Exception:
    RED_ALERT_GAIN = 1.5


def event_volume(key, vol):
    """The volume for one sound event: the red alert is RED_ALERT_GAIN times the seat's volume, never above 1.0."""
    return round(min(1.0, vol * RED_ALERT_GAIN), 3) if key == "red_alert" else vol
HEAD_FRESH_SECONDS = 24 * 3600
_SEAT = ""                                       # the seat this process is sounding for, set by main()


def is_head(label):
    """True while heads.json (written by the parley compile) holds the seat with reports > 0 and a
    "when" under 24 hours old."""
    try:
        import datetime
        e = _jload(HEADS_FILE).get(label or "") or {}
        if not isinstance(e, dict) or int(e.get("reports") or 0) <= 0:
            return False
        w = datetime.datetime.fromisoformat(str(e.get("when") or "").replace("Z", "+00:00"))
        if w.tzinfo is None:
            w = w.replace(tzinfo=datetime.timezone.utc)
        return 0 <= (datetime.datetime.now(datetime.timezone.utc) - w).total_seconds() < HEAD_FRESH_SECONDS
    except Exception:
        return False


def head_gain(label):
    """The MediaPlayer volume for this seat: 0.5 normally, 0.6 (20 percent louder, head_gain 1.2) while the seat is a
    parley head. Never above 1.0."""
    return round(min(1.0, NORMAL_VOLUME * HEAD_GAIN), 3) if is_head(label) else NORMAL_VOLUME


NEEDED = ("MAJOR PROBLEM FOUND", "URGENT", "Important", "BLOCKED", "Questions waiting", "Tick needs you", "Ignored",
          "Baton to relay", "Finished", "RED ALERT")


def ensure_generated(path):
    """A tone the skill generates ("gen:<style>") is made the first time it is needed, in the sounds folder of the chime
    home. Never in the skill folder, never a download. Silent on any error: the player then falls back."""
    try:
        name = os.path.basename(path or "")
        if (GEN_RX.match(name) and not os.path.isfile(path)
                and os.path.normcase(os.path.dirname(os.path.abspath(path))) == os.path.normcase(os.path.abspath(USER_SOUNDS))):
            os.makedirs(USER_SOUNDS, exist_ok=True)
            synth_wav(re.match(r"^gen-[a-z_]+-([a-z]+)\.wav$", name).group(1), path)
    except Exception:
        pass


def play(key):
    if muted():
        if DRY:
            print("MUTED %s (%s)" % (key, sound_name(key)))
        return
    if silenced(key):                            # silenced on the soundboard
        if DRY:
            print("SILENCED %s (%s)" % (key, sound_name(key)))
        return
    vol = event_volume(key, head_gain(_SEAT))
    if DRY:
        print("PLAY %s (%s) vol %s%s" % (key, sound_name(key), vol, " head" if is_head(_SEAT) else ""))
        return
    path = SOUNDS.get(key) or FALLBACK_WAV
    ensure_generated(path)
    if path.lower().endswith(".mp3") and os.path.exists(path):
        ps("Add-Type -AssemblyName PresentationCore; $p = New-Object System.Windows.Media.MediaPlayer; $p.Open([uri]'%s'); $p.Volume = %s; $p.Play();"
           "$i = 0; while (-not $p.NaturalDuration.HasTimeSpan -and $i -lt 30) { Start-Sleep -Milliseconds 100; $i++ };"
           "$s = 3; if ($p.NaturalDuration.HasTimeSpan) { $s = [Math]::Min(10, $p.NaturalDuration.TimeSpan.TotalSeconds + 0.3) }; Start-Sleep -Seconds $s; $p.Close()"
           % (q(path), vol))
        return
    try:
        import winsound
        target = path if (os.path.exists(path) and path.lower().endswith(".wav")) else FALLBACK_WAV
        if os.path.exists(target):
            winsound.PlaySound(target, winsound.SND_FILENAME)
        else:
            winsound.Beep(880, 600)
    except Exception:
        pass


def hold_job(seq, label, say, toasts):
    """Hand the rest of this turn's toasts, sounds and spoken name to a detached process that waits for the
    dictation to end, so the hook returns at once."""
    if DRY:
        print("HELD (dictation) %s%s" % (" ".join(seq), " + name" if say else ""))
        return
    try:
        job = json.dumps({"seq": list(seq), "label": label or "", "say": bool(say), "toasts": [list(x) for x in toasts]})
        subprocess.Popen([sys.executable, os.path.abspath(__file__), "held", job],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=0x00000008 | 0x00000200, close_fds=True)   # DETACHED_PROCESS | NEW_PROCESS_GROUP
    except Exception:
        pass


def held_lock():
    """One held turn plays at a time, so several sessions released together do not talk over each other.
    The lock is the open file; it is released when this process ends."""
    try:
        import msvcrt
        os.makedirs(os.path.dirname(HOLD_LOG), exist_ok=True)
        f = open(os.path.join(os.path.dirname(HOLD_LOG), "held.lock"), "a+")
        t0 = time.time()
        while time.time() - t0 < 120:
            try:
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                time.sleep(0.3)
        return f
    except Exception:
        return None


def hold_note(label, seconds, seq, say):
    try:
        os.makedirs(os.path.dirname(HOLD_LOG), exist_ok=True)
        with io.open(HOLD_LOG, "a", encoding="utf-8") as f:
            f.write("%s | held %.1f s | %s | %s%s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), seconds, label or "?",
                                                      " ".join(seq), " + name" if say else ""))
    except Exception:
        pass


def run_seq(seq, label="", say=False, toasts=(), held=False):
    """Show a turn's toasts, play its sounds, then say its name. In a hook (held False) a dictation in progress
    hands whatever is left to the detached held process. In that process (held True) each step waits for the
    dictation to end first."""
    seq, toasts = list(seq), list(toasts)
    if held:
        waited = hold_for_dictation()
        lock = held_lock()
        waited += hold_for_dictation()
        hold_note(label, waited, seq, say)
        for title, body in toasts:
            toast(title, body)
        for s in seq:
            hold_for_dictation()
            play(s)
        if say:
            hold_for_dictation()
            speak(label)
        del lock
        return
    active = HOLD and not muted()
    if active and (seq or say or toasts) and dictating():
        hold_job(seq, label, say, toasts)
        return
    for title, body in toasts:
        toast(title, body)
    for n, s in enumerate(seq):
        if active and dictating():
            hold_job(seq[n:], label, say, [])
            return
        play(s)
    if say:
        if active and dictating():
            hold_job([], label, True, [])
            return
        speak(label)


def last_assistant_text(transcript_path):
    try:
        with open(transcript_path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 400000))
            lines = f.read().decode("utf-8", errors="replace").splitlines()
    except Exception:
        return ""
    for line in reversed(lines):
        try:
            e = json.loads(line)
        except Exception:
            continue
        if e.get("type") != "assistant":
            continue
        parts = [c.get("text", "") for c in (e.get("message") or {}).get("content") or []
                 if isinstance(c, dict) and c.get("type") == "text"]
        if parts:
            return "\n".join(parts)
    return ""


def turn_origin(transcript_path):
    """Tick, peer or human: what started the turn, from the newest user entry that is not a tool result."""
    try:
        size = os.path.getsize(transcript_path)
    except Exception:
        return "human"
    n = 1 << 20
    while True:
        try:
            with open(transcript_path, "rb") as f:
                f.seek(max(0, size - n))
                lines = f.read().decode("utf-8", errors="replace").splitlines()
        except Exception:
            return "human"
        if size > n:
            lines = lines[1:]
        for line in reversed(lines):
            try:
                e = json.loads(line)
            except Exception:
                continue
            if e.get("type") != "user":
                continue
            c = (e.get("message") or {}).get("content")
            if isinstance(c, list) and any(isinstance(x, dict) and x.get("type") == "tool_result" for x in c):
                continue
            text = c if isinstance(c, str) else " ".join(
                x.get("text", "") for x in c or [] if isinstance(x, dict) and x.get("type") == "text")
            kind = ((e.get("origin") or {}).get("kind") or "")
            _m = TICK_RX.match(text or "")
            if _m:
                STATE["tick_loop"] = _m.group(1)
                return "tick"
            to = e.get("turnOrigin")                 # the transcript records who started the turn
            if to:
                return {"human": "human", "peer": "peer"}.get(to, "system")
            if kind == "peer" or (text or "").lstrip().startswith(PEER_PREFIXES):
                return "peer"
            if kind == "human":
                return "human"
            if e.get("isMeta"):
                continue
            return "human"
        if size <= n or n >= (1 << 24):
            return "human"
        n <<= 2


def first_line(text):
    for line in (text or "").splitlines():
        s = line.strip().lstrip("*_#>` ").strip()
        if s:
            return s.lower()
    return ""


def opener(text):
    fl = first_line(text)
    try:
        if RA_RX.match(first_line_raw(text)):                      # RED ALERT, on its own word boundary ("RED ALERTS" is not it)
            return "redalert"
    except Exception:
        pass
    for phrase, key in OPENERS:
        if fl.startswith(phrase):
            return key
    return None


def hands_compact_prompt(text):
    fl = first_line(text)
    return fl.startswith("compactionprep") or fl.startswith("smartcompact") or bool(COMPACT_RX.search(text or ""))


def sound_line_seat(text):
    for line in reversed((text or "").splitlines()):
        if line.strip():
            m = SOUND_LINE_RX.match(line)
            return m.group("seat") if m else ""
    return ""


FACT_RX = re.compile(rb'"type"\s*:\s*"(?:custom-title|ai-title)"|"turnOrigin"\s*:\s*"(?!human")|"promptSource"\s*:\s*"system"')


def prompt_key(text):
    return hashlib.sha1((text or "").strip()[:300].encode("utf-8", "replace")).hexdigest()[:12]


def transcript_facts(transcript_path):
    """From a session's transcript, its tab title (the newest custom-title, else ai-title) and the keys of every
    prompt that arrived scheduled or from the system rather than typed by the person (a cron prompt repeats verbatim, so its
    key is known from its second firing on). Cached per transcript by size: each call reads only the appended bytes."""
    facts = {"custom": "", "ai": "", "sys": []}
    if not transcript_path:
        return facts
    try:
        size = os.path.getsize(transcript_path)
        d = os.path.join(tempfile.gettempdir(), "chime")
        os.makedirs(d, exist_ok=True)
        cache = os.path.join(d, "facts_%s.json" % hashlib.sha1(transcript_path.lower().encode("utf-8")).hexdigest()[:10])
        c = {}
        try:
            c = json.load(open(cache, encoding="utf-8"))
        except Exception:
            pass
        start = c.get("size", 0) if 0 < c.get("size", 0) <= size else 0
        if start:
            facts = {"custom": c.get("custom", ""), "ai": c.get("ai", ""), "sys": c.get("sys", [])}
        if start != size:
            with open(transcript_path, "rb") as f:
                f.seek(start)
                data = f.read()
            last = -1
            for m in FACT_RX.finditer(data):
                a = data.rfind(b"\n", 0, m.start()) + 1
                if a == last:
                    continue
                last = a
                b = data.find(b"\n", m.end())
                try:
                    e = json.loads(data[a:b if b >= 0 else len(data)].decode("utf-8", "replace"))
                except Exception:
                    continue
                if e.get("type") == "custom-title" and e.get("customTitle"):
                    facts["custom"] = e["customTitle"]
                elif e.get("type") == "ai-title" and e.get("aiTitle"):
                    facts["ai"] = e["aiTitle"]
                elif e.get("type") == "user":
                    cc = (e.get("message") or {}).get("content")
                    text = cc if isinstance(cc, str) else " ".join(
                        x.get("text", "") for x in cc or [] if isinstance(x, dict) and x.get("type") == "text")
                    k = prompt_key(text)
                    if text.strip() and k not in facts["sys"]:
                        facts["sys"] = (facts["sys"] + [k])[-500:]
            with open(cache, "w", encoding="utf-8") as fh:
                json.dump(dict(facts, size=size), fh)
    except Exception:
        pass
    return facts


def tab_title(transcript_path):
    """The session's VS Code tab title, the newest custom-title (else ai-title) in its transcript."""
    f = transcript_facts(transcript_path)
    return f["custom"] or f["ai"]


def session_label(session_id, text, transcript_path=""):
    """The tab title the person sees; never the derived runtime name."""
    title = tab_title(transcript_path)
    if title:
        return title
    seat = sound_line_seat(text)
    if not seat:
        m = SEAT_RX.search(text or "") if SEAT_RX else None
        seat = m.group(1) if m else ""
    if seat:
        return seat
    if SESSIONS_GLOB:
        for f in glob.glob(SESSIONS_GLOB):
            try:
                d = json.load(open(f, encoding="utf-8"))
            except Exception:
                continue
            if d.get("sessionId") == session_id:
                if d.get("nameSource") == "user" and d.get("name"):
                    return d["name"]
                cwd = d.get("cwd") or ""
                if cwd:
                    return "a session in " + os.path.basename(cwd.rstrip("\\/"))
                break
    return "a session"


def already_played(session_id, mode, text):
    """True if this exact turn was already chimed in the last DEDUPE_SECONDS (two hook entries firing)."""
    try:
        d = os.path.join(tempfile.gettempdir(), "chime")
        os.makedirs(d, exist_ok=True)
        key = hashlib.sha1(("%s|%s|%s" % (session_id, mode, (text or "")[:4000])).encode("utf-8", "replace")).hexdigest()
        p = os.path.join(d, key)
        now = time.time()
        if os.path.exists(p) and now - os.path.getmtime(p) < DEDUPE_SECONDS:
            return True
        with open(p, "w") as fh:
            fh.write(str(now))
        for old in os.listdir(d):                   # keep the folder small
            op = os.path.join(d, old)
            if now - os.path.getmtime(op) > 3600:
                os.remove(op)
    except Exception:
        return False
    return False


def _gate_will_block(data):
    """An optional module the person names in config "stop_gate" (a python file with decide(data, config()) and config())
    may send a reply back once; this stop is then not the turn's end, so chime stays quiet and plays on the
    continuation's stop. Off unless named. Fails open (plays) on any error."""
    try:
        import importlib.util
        p = os.path.expanduser(_C.get("stop_gate") or "")
        if not p or not os.path.isfile(p):
            return False
        spec = importlib.util.spec_from_file_location("signature_gate", p)
        g = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(g)
        return g.decide(data, g.config())[0] == "block"
    except Exception:
        return False


# ---------------------------------------------------------------------------------------------------------------
# RED ALERT. A session that found a material risk or deficiency sounds red_alert, logs it in one central file and puts
# a card on its parley asking the person whether it merited the alert. The log is what the next session consults
# before it fires. Everything below is wrapped: an error skips the new behaviour, never the hook.
# ---------------------------------------------------------------------------------------------------------------
RA_RX = re.compile(r"^RED ALERT(?=$|[\s:\-\u2013\u2014.,;!*()\[\]])")   # the raw first line, CAPITALS only: a sentence that starts "Red alert is ..." is prose, not an alarm
RA_HOURS = 6                                     # the same issue does not sound again inside this window
RA_MARK_SECONDS = 15 * 60                        # a mid-turn fire silences that turn's first-line RED ALERT this long
RA_READ_BYTES = 400000                           # the hook and the read commands never read more of the log than this
RA_PARA_MAX = 1190                               # the whole paragraph of hook text stays under 1,200 characters
RA_STOP = frozenset(("the", "and", "for", "not", "are", "was", "has", "its", "out", "off", "per", "via", "with", "from"))


def ra_log_path():
    return os.path.join(CHIME_HOME, "red_alerts.jsonl")


def ra_seen_path():
    return os.path.join(CHIME_HOME, "redalert_seen.json")


def ra_txt(s, n):
    """One line of plain text, at most n characters."""
    return re.sub(r"[\x00-\x1f\x7f\s]+", " ", str(s or "")).strip()[:n]


def ra_slug(s):
    return re.sub(r"[^a-z0-9]+", "-", str(s or "").lower()).strip("-")[:48]


def ra_now():
    return datetime.datetime.now().astimezone()


def ra_parse(s):
    try:
        d = datetime.datetime.fromisoformat(str(s).strip().replace("Z", "+00:00"))
        return d if d.tzinfo else d.astimezone()
    except Exception:
        return None


def ra_ts(rec, field="when"):
    d = ra_parse(rec.get(field) or "")
    if d is None and field != "when":
        d = ra_parse(rec.get("when") or "")
    return d.timestamp() if d else 0.0


def ra_newest_first(rows):
    """Newest first by the time fired; lines fired in the same second keep the log's order, the later line first."""
    return [r for _, r in sorted(enumerate(rows), key=lambda p: (ra_ts(p[1]), p[0]), reverse=True)]


def ra_words(*texts):
    w = set()
    for t in texts:
        for x in re.split(r"[^a-z0-9]+", str(t or "").lower()):
            if len(x) >= 3 and x not in RA_STOP:
                w.add(x)
    return w


def ra_read():
    """The alerts in the log's last 400 KB, oldest first. A corrupt line, or a line that is not an object with an id,
    is skipped. [] on any error."""
    out = []
    try:
        with open(ra_log_path(), "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            start = max(0, size - RA_READ_BYTES)
            f.seek(start)
            raw = f.read(RA_READ_BYTES)
        lines = raw.decode("utf-8", errors="replace").splitlines()
        if start > 0:
            lines = lines[1:]                    # the first line of a cut read is partial
        for ln in lines:
            ln = ln.strip()
            if not ln:
                continue
            try:
                d = json.loads(ln)
            except Exception:
                continue
            if isinstance(d, dict) and isinstance(d.get("id"), str) and d["id"]:
                out.append(d)
    except Exception:
        return []
    return out


def ra_lock(timeout=5.0, stale=15.0):
    """Take the log's lock: an exclusive-create file (works on Windows; no fcntl). A lock older than `stale` seconds
    belongs to a killed process and is removed. Returns the lock path, or None when it could not be taken in
    `timeout` seconds (the caller then goes on without it rather than hang)."""
    lock = ra_log_path() + ".lock"
    try:
        os.makedirs(CHIME_HOME, exist_ok=True)
    except Exception:
        return None
    t0 = time.time()
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return lock
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(lock) > stale:
                    os.remove(lock)
                    continue
            except OSError:
                pass
        except PermissionError:                  # Windows: the lock is being deleted by its holder
            pass
        except OSError:
            return None
        if time.time() - t0 > timeout:
            return None
        time.sleep(0.03)


def ra_unlock(lock):
    if lock:
        try:
            os.remove(lock)
        except OSError:
            pass


def ra_append(rec):
    """Append one record as one line, after making sure the file ends in a newline (a cut line must not swallow it)."""
    os.makedirs(CHIME_HOME, exist_ok=True)
    p = ra_log_path()
    lead = b""
    try:
        if os.path.getsize(p) > 0:
            with open(p, "rb") as f:
                f.seek(-1, 2)
                if f.read(1) != b"\n":
                    lead = b"\n"
    except OSError:
        pass
    with open(p, "ab") as f:
        f.write(lead + (json.dumps(rec, ensure_ascii=False) + "\n").encode("utf-8"))


def ra_new_id():
    return "RA-%s-%s" % (time.strftime("%Y%m%d-%H%M%S"), os.urandom(2).hex())


def ra_date(rec, field="when"):
    d = ra_parse(rec.get(field) or "") or ra_parse(rec.get("when") or "")
    return d.strftime("%Y-%m-%d") if d else "?"


def ra_line(a):
    v = str(a.get("verdict") or "pending")
    return "%s | %s | %s | %s%s | %s" % (a.get("id"), ra_date(a), ra_txt(a.get("kind"), 48) or "?",
                                          v, itext("ra_example_tag") if a.get("source") == "example" else "",
                                          ra_txt(a.get("title"), 120))


def ra_silent_reason(session=""):
    """None when a red alert would sound now, else the plain reason it will not (this is what the log's played holds)."""
    try:
        if session and brakes_on(session):
            return "brakes on"
        if os.path.exists(MUTE_FILE):
            return "muted (mute file)"
        if clocked_out():
            return "muted (%s)" % itext("person_clocked_out")
        if zoom_meeting():
            return "muted (Zoom meeting)"
        if silenced("red_alert"):
            return "silenced on the soundboard"
    except Exception:
        pass
    return None


# ---- the marker files that keep one firing to one sound -------------------------------------------------------

def ra_mark_path(kind, key):
    d = os.path.join(tempfile.gettempdir(), "chime")
    return os.path.join(d, "ra_fired_" + hashlib.sha1(("%s:%s" % (kind, (key or "").lower())).encode("utf-8")).hexdigest()[:16])


def ra_mark(alert_id, session, seat):
    """A fire (or a mid-turn play) that sounded: leave a marker for the session and for the seat, so the Stop hook of
    this turn does not sound the first-line RED ALERT a second time. Life: 15 minutes."""
    try:
        os.makedirs(os.path.join(tempfile.gettempdir(), "chime"), exist_ok=True)
        body = json.dumps({"id": alert_id, "ts": time.time()})
        for kind, key in (("sid", session), ("seat", seat)):
            if key:
                with open(ra_mark_path(kind, key), "w", encoding="utf-8") as fh:
                    fh.write(body)
    except Exception:
        pass


def ra_take_mark(pairs):
    """The alert id of a live marker for any of these (kind, key) pairs, else None. Every marker found is removed,
    so one fire silences one turn."""
    found = None
    for kind, key in pairs:
        if not key:
            continue
        p = ra_mark_path(kind, key)
        try:
            if not os.path.exists(p):
                continue
            try:
                with open(p, encoding="utf-8") as fh:
                    d = json.load(fh)
            except Exception:
                d = {}
            os.remove(p)
            if time.time() - float(d.get("ts") or 0) < RA_MARK_SECONDS and found is None:
                found = str(d.get("id") or "a mid-turn alert")
        except Exception:
            continue
    return found


def ra_seen_load():
    d = _jload(ra_seen_path())
    now = time.time()
    return {k: v for k, v in d.items() if isinstance(v, (int, float)) and 0 <= now - v < RA_HOURS * 3600}


def ra_seen_stamp(*seats):
    """The seat has sounded a red alert now; a first-line RED ALERT from it inside 6 hours is an ordinary turn."""
    try:
        d = ra_seen_load()
        for s in seats:
            if s:
                d[s.lower()] = time.time()
        os.makedirs(CHIME_HOME, exist_ok=True)
        tmp = ra_seen_path() + ".%d.tmp" % os.getpid()
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(d, fh)
        os.replace(tmp, ra_seen_path())
    except Exception:
        pass


def ra_gate(sid, label, text):
    """Stop hook: a first-line RED ALERT sounds unless this turn already sounded one mid-turn, or this seat sounded
    one in the last 6 hours (nothing is replayed). Returns "redalert" or None (an ordinary turn). Any error: sound."""
    try:
        seat = sound_line_seat(text)
        done = ra_take_mark([("sid", sid), ("seat", label), ("seat", seat)])
        if done is not None:
            if DRY:
                print("RED ALERT already sounded this turn (%s): nothing more" % done)
            return None
        seen = ra_seen_load()
        if any((s or "").lower() in seen for s in (label, seat)):
            if DRY:
                print("RED ALERT repeat inside %d hours: ordinary turn" % RA_HOURS)
            return None
        if not muted():                          # a muted turn does not use the seat's one sound up
            ra_seen_stamp(label, seat)
    except Exception:
        pass
    return "redalert"


def first_line_raw(text):
    for line in (text or "").splitlines():
        s = line.strip().lstrip("*_#>` ").strip()
        if s:
            return s
    return ""


def ra_toast_body(text):
    """The first line's words after RED ALERT, at most 140 characters."""
    try:
        fl = first_line_raw(text)
        rest = re.sub(r"^red alert[\s:\-\u2013\u2014.,;!*_]*", "", fl, flags=re.I).strip().rstrip("*_ ")
        return ra_txt(rest, 140) or "A session raised a red alert: a material risk or deficiency."
    except Exception:
        return "A session raised a red alert."


# ---- the prompt hook's paragraph ------------------------------------------------------------------------------

def ra_item(a):
    """Kind (title, date) cut at 70 characters."""
    kind, date = ra_slug(a.get("kind")) or "?", ra_date(a, "verdict_at")
    title = ra_txt(a.get("title"), 200)
    whole = "%s (%s, %s)" % (kind, title, date)
    if len(whole) <= 70:
        return whole
    room = 70 - len("%s (" % kind) - len(", %s)" % date) - 3
    return ("%s (%s..., %s)" % (kind, title[:max(room, 0)].rstrip(), date))[:70]


def ra_learned(alerts):
    """([merited items], [not merited items]): the person's newest ruling per kind, newest first, at most 6 each."""
    latest = {}
    for a in alerts:
        v = a.get("verdict")
        if v not in ("merited", "not_merited"):
            continue
        k, ts = ra_slug(a.get("kind")) or "?", ra_ts(a, "verdict_at")
        if k not in latest or ts >= latest[k][0]:
            latest[k] = (ts, a)
    rows = sorted(latest.values(), key=lambda r: r[0], reverse=True)
    return ([ra_item(a) for _, a in rows if a["verdict"] == "merited"][:6],
            [ra_item(a) for _, a in rows if a["verdict"] == "not_merited"][:6])


def ra_paragraph():
    """The RED ALERT paragraph for the prompt hook: what it is, how to fire, and what the person has ruled. Under 1,200
    characters; the oldest rulings are dropped first when the lists would not fit. With an empty log the two list
    sentences are left out and the rest stays."""
    alerts = ra_read()
    m, n = ra_learned(alerts)

    def build():
        out = itext("ra_base")
        if m:
            out += itext("ra_merited") + "; ".join(m) + "."
        if n:
            out += itext("ra_not_merited") + "; ".join(n) + "."
        return out

    while len(build()) > RA_PARA_MAX and (m or n):
        (m if len(m) >= len(n) else n).pop()
    return build()


# ---- the commands: chime.py redalert check|fire|verdict|list|example -----------------------------------------

def ra_args(argv, valued, flags=()):
    o, i = {}, 0
    while i < len(argv):
        a = argv[i]
        if a in flags:
            o[a] = True
            i += 1
        elif a in valued:
            if i + 1 >= len(argv):
                raise ValueError("%s needs a value" % a)
            o[a] = argv[i + 1]
            i += 2
        else:
            raise ValueError("unknown argument %s" % a)
    return o


RA_USAGE = ("usage: chime.py redalert check --kind <slug> [--words \"..\"] | fire --seat <SEAT> --kind <slug> --title \"..\" "
            "--why \"..\" [--evidence \"..\"] [--card <id>] [--parley <url>] [--session <uuid>] [--worse \"..\"] "
            "[--fragment <path>] [--codename \"..\"] | card --id <id> --card <card id> [--parley <url>] [--fragment <path>] "
            "[--where \"..\"] | card --id <id> --write [--card <card id>] [--fragment <path>] [--codename \"..\"] | uncarded "
            "[--seat <SEAT>] [--crew <S1,S2>] [--min-age <minutes>] [--updated \"SEAT=ISO;..\"] | verdict "
            "--id <id> --merited|--not-merited [--by \"..\"] [--note \"..\"] | list [--pending] [--seat <SEAT>] | example "
            "--kind <slug> --title \"..\" --why \"..\" --verdict merited|not_merited [--seat <SEAT>] [--evidence \"..\"] "
            "[--by \"..\"] [--when <ISO>]")


def ra_main(argv):
    """Exit code: 0 done, 1 not found or busy, 2 bad arguments, 3 fire refused (same issue under 6 hours old)."""
    try:
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
        sub = (argv[0] if argv else "").lower()
        rest = argv[1:]
        if sub == "check":
            return ra_cmd_check(ra_args(rest, ("--kind", "--words")))
        if sub == "fire":
            return ra_cmd_fire(ra_args(rest, ("--seat", "--kind", "--title", "--why", "--evidence", "--card", "--parley",
                                              "--session", "--worse", "--fragment", "--codename")))
        if sub == "card":
            return ra_cmd_card(ra_args(rest, ("--id", "--card", "--parley", "--fragment", "--where", "--codename"), ("--write",)))
        if sub == "uncarded":
            return ra_cmd_uncarded(ra_args(rest, ("--seat", "--crew", "--min-age", "--updated")))
        if sub == "verdict":
            return ra_cmd_verdict(ra_args(rest, ("--id", "--by", "--note"), ("--merited", "--not-merited")))
        if sub == "list":
            return ra_cmd_list(ra_args(rest, ("--seat",), ("--pending",)))
        if sub == "example":
            return ra_cmd_example(ra_args(rest, ("--kind", "--title", "--why", "--verdict", "--seat", "--evidence", "--by",
                                                 "--when")))
        print("ERROR: " + RA_USAGE)
        return 2
    except ValueError as e:
        print("ERROR: %s" % e)
        return 2
    except Exception as e:
        print("ERROR: red alert command failed (%s)" % e.__class__.__name__)
        return 1


def ra_cmd_check(o):
    slug = ra_slug(o.get("--kind"))
    if not slug:
        print("ERROR: --kind <slug> is required")
        return 2
    query = ra_words(slug, o.get("--words"))
    hit = [a for a in ra_read() if ra_slug(a.get("kind")) == slug or (ra_words(a.get("kind")) & query)]
    hit = ra_newest_first(hit)
    for a in hit[:8]:
        print(ra_line(a))
    yes = [a for a in hit if a.get("verdict") == "merited"]
    no = [a for a in hit if a.get("verdict") == "not_merited"]
    if yes and no:
        print("ADVICE mixed: read the lines above")
    elif yes:
        print("ADVICE fire")
    elif no:
        newest = max(no, key=lambda a: ra_ts(a, "verdict_at"))
        print(itext("ra_advice_not_merited", (ra_date(newest, "verdict_at"),)))
    else:
        print("ADVICE no precedent")
    return 0


def ra_cmd_fire(o):
    global _SEAT
    seat, kind = ra_txt(o.get("--seat"), 80), ra_slug(o.get("--kind"))
    title, why = ra_txt(o.get("--title"), 200), ra_txt(o.get("--why"), 1500)
    missing = [n for n, v in (("--seat", seat), ("--kind", kind), ("--title", title), ("--why", why)) if not v]
    if missing:
        print("ERROR: missing " + ", ".join(missing))
        return 2
    worse, session = ra_txt(o.get("--worse"), 300), ra_txt(o.get("--session"), 80)
    lock = ra_lock()
    try:
        now = ra_now()
        prior = None
        for a in ra_newest_first(ra_read()):
            if a.get("source") == "example" or str(a.get("seat") or "").lower() != seat.lower() \
                    or ra_slug(a.get("kind")) != kind or a.get("verdict") not in ("pending", "merited"):
                continue
            age = now.timestamp() - ra_ts(a)
            if ra_ts(a) and age < RA_HOURS * 3600:
                prior = (a, age)
                break
        if prior and not worse:
            print("REFUSED: %s fired %s for this seat and kind %d min ago (verdict %s); it does not sound again inside %d "
                  "hours unless it got materially worse: add --worse \"<what got worse>\""
                  % (prior[0]["id"], ra_txt(prior[0].get("when"), 25), int(prior[1] // 60), prior[0].get("verdict"), RA_HOURS))
            if prior[0].get("verdict") == "pending" and not (prior[0].get("card") or prior[0].get("parley")) and prior[1] >= RA_CARD_MIN * 60:
                print("ALERT CARD MISSING %s %s %.1f" % (prior[0]["id"], seat, prior[1] / 3600.0))
            return 3
        reason = ra_silent_reason(session)
        rec = {"id": ra_new_id(), "when": now.isoformat(timespec="seconds"), "seat": seat, "session": session,
               "home": account_name() or "", "kind": kind, "title": title, "why": why,
               "evidence": ra_txt(o.get("--evidence"), 500), "card": ra_txt(o.get("--card"), 80),
               "parley": ra_txt(o.get("--parley"), 300), "played": True if reason is None else reason,
               "verdict": "pending", "verdict_at": "", "verdict_by": "", "verdict_note": "", "source": "fired"}
        if worse:
            rec["worse"] = worse
            rec["worse_than"] = prior[0]["id"] if prior else ""
        ra_append(rec)
    finally:
        ra_unlock(lock)
    _SEAT = seat
    if reason != "brakes on":                    # a braked session shows and says nothing
        run_seq(["red_alert"], seat, True, [("RED ALERT: " + seat, title[:140])])
    if reason is None:
        ra_mark(rec["id"], session, seat)
        ra_seen_stamp(seat)
    print("FIRED %s" % rec["id"])
    print("SOUND %s" % ("played" if reason is None else "not played: " + reason))
    try:                                         # v22: the card is part of the firing
        ra_apply_card(rec, o)
    except Exception as e:
        print("CARD NOT WRITTEN: the card step failed (%s); write the card yourself, then run: chime.py redalert card --id %s "
              "--card <card id>" % (e.__class__.__name__, rec["id"]))
    return 0


def ra_cmd_verdict(o):
    rid = ra_txt(o.get("--id"), 80)
    if not rid or ("--merited" in o) == ("--not-merited" in o):
        print("ERROR: --id <id> and exactly one of --merited or --not-merited are required")
        return 2
    verdict = "merited" if "--merited" in o else "not_merited"
    lock = ra_lock()
    if lock is None:
        print("BUSY: the red alert log is locked by another process; run it again")
        return 1
    try:
        p = ra_log_path()
        if not os.path.exists(p):
            print("NOT FOUND %s" % rid)
            return 1
        stamp = ra_now().isoformat(timespec="seconds")
        found, replaced = False, ""
        tmp = p + ".%d.tmp" % os.getpid()
        with open(p, "rb") as src, open(tmp, "wb") as dst:
            for raw in src:                      # the whole file, line by line: nothing is lost, corrupt lines stay
                out = raw
                if not found and rid.encode("utf-8") in raw:
                    try:
                        d = json.loads(raw.decode("utf-8", errors="replace"))
                    except Exception:
                        d = None
                    if isinstance(d, dict) and d.get("id") == rid:
                        found = True
                        old = d.get("verdict")
                        if old in ("merited", "not_merited"):
                            d.setdefault("verdict_history", []).append(
                                {k: d.get(k, "") for k in ("verdict", "verdict_at", "verdict_by", "verdict_note")})
                            replaced = " (replaces %s of %s)" % (old, ra_date(d, "verdict_at"))
                        d.update(verdict=verdict, verdict_at=stamp, verdict_by=ra_txt(o.get("--by"), 80),
                                 verdict_note=ra_txt(o.get("--note"), 500))
                        out = (json.dumps(d, ensure_ascii=False) + "\n").encode("utf-8")
                if not out.endswith(b"\n"):
                    out += b"\n"
                dst.write(out)
        if not found:
            os.remove(tmp)
            print("NOT FOUND %s" % rid)
            return 1
        for attempt in range(40):                # Windows refuses to replace a file another process has open
            try:
                os.replace(tmp, p)
                break
            except PermissionError:
                if attempt == 39:
                    os.remove(tmp)
                    print("BUSY: the red alert log could not be replaced; run it again")
                    return 1
                time.sleep(0.05)
        print("VERDICT %s %s%s" % (rid, verdict, replaced))
        return 0
    finally:
        ra_unlock(lock)


def ra_cmd_list(o):
    rows = ra_read()
    if o.get("--pending"):
        rows = [a for a in rows if (a.get("verdict") or "pending") == "pending"]
    if o.get("--seat"):
        rows = [a for a in rows if str(a.get("seat") or "").lower() == o["--seat"].lower()]
    rows = ra_newest_first(rows)
    if not rows:
        print("NO ALERTS")
    for a in rows:
        print("%s | %s | %s | %s" % (ra_line(a), ra_txt(a.get("seat"), 60) or "-", ra_txt(a.get("verdict_by"), 40) or "-",
                                     "played" if a.get("played") is True else ra_txt(a.get("played"), 60)))
    return 0


def ra_cmd_example(o):
    kind, title, why = ra_slug(o.get("--kind")), ra_txt(o.get("--title"), 200), ra_txt(o.get("--why"), 1500)
    verdict = (o.get("--verdict") or "").replace("-", "_")
    if not (kind and title and why) or verdict not in ("merited", "not_merited"):
        print("ERROR: --kind, --title, --why and --verdict merited|not_merited are required")
        return 2
    now = ra_now()
    when = ra_parse(o["--when"]) if o.get("--when") else now
    if when is None:
        print("ERROR: --when is not an ISO date")
        return 2
    rec = {"id": ra_new_id(), "when": when.isoformat(timespec="seconds"), "seat": ra_txt(o.get("--seat"), 80),
           "session": "", "home": "", "kind": kind, "title": title, "why": why, "evidence": ra_txt(o.get("--evidence"), 500),
           "card": "", "parley": "", "played": "example: no sound", "verdict": verdict,
           "verdict_at": now.isoformat(timespec="seconds"), "verdict_by": ra_txt(o.get("--by"), 80) or itext("ra_default_by"),
           "verdict_note": itext("ra_example_note"), "source": "example"}
    lock = ra_lock()
    try:
        ra_append(rec)
    finally:
        ra_unlock(lock)
    print("EXAMPLE %s %s" % (rec["id"], verdict))
    return 0


# ---- v22: the card is part of the firing (the person's standard of 2026-11-18) -------------------------------------
# `fire` prints the card block and, when it can find the seat's page source, writes it there. `card` records a card on
# the alert's log line (card, parley, card_where, card_at). `uncarded` is the detector: a pending alert with no card.
# Everything here is wrapped like the rest of the red alert commands: an error prints a line, it never reaches a hook.
PARLEY_DIR = os.path.join(os.path.expanduser("~"), ".threadops", "parley")
FRAGMENTS_FILE = os.path.join(PARLEY_DIR, "fragments.json")   # written by the parley compile: seat -> {path, head, own, when}
RA_CARD_MIN = 30                                               # minutes a pending alert may have no card before it is reported


def ra_zone(d):
    """EST or EDT for the two Eastern offsets, else the numeric offset (+HH:MM). No time zone database is needed."""
    off = d.utcoffset()
    if off is None:
        return ""
    m = int(off.total_seconds() // 60)
    if m in (-300, -240):
        return "EST" if m == -300 else "EDT"
    z = d.strftime("%z")
    return (z[:3] + ":" + z[3:]) if len(z) == 5 else "Z"


def ra_stamp(d):
    d = d.astimezone()
    return (d.strftime("%Y-%m-%d %H:%M") + " " + ra_zone(d)).strip()


def ra_fragment_for(seat, given):
    """(path, how): how is "given" or "recorded" when there is a path, else the plain reason there is none."""
    if given:
        return os.path.abspath(os.path.expanduser(given)), "given"
    try:
        with io.open(FRAGMENTS_FILE, encoding="utf-8") as fh:
            reg = json.load(fh)
        for k, v in reg.items():
            if str(k).lower() == str(seat).lower() and isinstance(v, dict) and v.get("path"):
                p = str(v["path"])
                if os.path.isfile(p):
                    return p, "recorded"
                return None, "the recorded page source is gone (%s); pass --fragment PATH" % p
    except Exception:
        pass
    return None, "no page source is recorded for this seat (a compile of its page, or of its head's page, records it); pass --fragment PATH"


def ra_alert_block(rec):
    d = {"id": rec["id"], "kind": rec.get("kind") or "", "fired": ra_stamp(ra_parse(rec.get("when")) or ra_now()),
         "why": rec.get("why") or ""}
    if rec.get("evidence"):
        d["evidence"] = rec["evidence"]
    return d


def ra_card(rec, card_id, seat, codename):
    """The card for one alert, in the shape parley 2.20 compiles without a warning."""
    now = ra_stamp(ra_now())
    c = {"id": card_id}
    if codename:
        c["codename"] = codename
    c.update({"title": "RED ALERT: " + (rec.get("title") or rec.get("kind") or rec["id"]), "from": seat, "opened": now,
              "important": True, "urgent": False, "mrp": itext("ra_default_by"), "alert": ra_alert_block(rec),
              "ask": "Did this merit a red alert? Rule Merited or Not merited on this card.",
              "steps": [["1", "Rule Merited or Not merited on this card"]],
              "checked": "%s: written when the alert fired; the seat adds what it checked in the system of record" % now,
              "origin": {"project": seat, "thread": "red alert " + rec["id"]}})
    return c


def ra_rewrite(rid, mut):
    """Change the one log line whose id is rid with mut(dict). Every other line stays byte for byte.
    Returns "ok", "notfound" or "busy"."""
    lock = ra_lock()
    if lock is None:
        return "busy"
    tmp = ra_log_path() + ".%d.tmp" % os.getpid()
    try:
        p = ra_log_path()
        if not os.path.exists(p):
            return "notfound"
        found = False
        with open(p, "rb") as src, open(tmp, "wb") as dst:
            for raw in src:
                out = raw
                if not found and rid.encode("utf-8") in raw:
                    try:
                        d = json.loads(raw.decode("utf-8", errors="replace"))
                    except Exception:
                        d = None
                    if isinstance(d, dict) and d.get("id") == rid:
                        found = True
                        mut(d)
                        out = (json.dumps(d, ensure_ascii=False) + "\n").encode("utf-8")
                if not out.endswith(b"\n"):
                    out += b"\n"
                dst.write(out)
        if not found:
            return "notfound"
        for attempt in range(40):                # Windows refuses to replace a file another process has open
            try:
                os.replace(tmp, p)
                return "ok"
            except PermissionError:
                if attempt == 39:
                    return "busy"
                time.sleep(0.05)
        return "busy"
    finally:
        ra_unlock(lock)
        try:
            os.remove(tmp)
        except OSError:
            pass


def ra_set_card(rid, card, parley, where):
    """Record the card on the alert's log line. A card the line already names and this one replaces goes to card_history."""
    stamp = ra_now().isoformat(timespec="seconds")

    def mut(d):
        old = {k: d.get(k, "") for k in ("card", "parley", "card_where", "card_at")}
        if old["card"] and old["card"] != card:
            d.setdefault("card_history", []).append(old)
        d["card"] = card
        if parley:
            d["parley"] = ra_txt(parley, 300)
        d["card_where"] = ra_txt(where, 300)
        d["card_at"] = stamp
    return ra_rewrite(rid, mut)


def ra_write_card(path, rec, card_id, explicit, seat, codename):
    """Put the alert's card into the page source at path (valid JSON in, valid JSON out, a backup beside it, never a
    second card for the same alert id). Returns (state, text, card id). state: "added", "attached" (the block went on a
    card the seat named with --card), "exists" (the alert is already on a card there; nothing written) or "no"."""
    import copy
    import shutil
    try:
        st0 = os.stat(path)
        with open(path, "rb") as f:
            raw = f.read()
        bom = raw.startswith(b"\xef\xbb\xbf")
        text = raw.decode("utf-8-sig")
        orig = json.loads(text)
    except Exception as e:
        return "no", "the page source could not be read as JSON (%s)" % e.__class__.__name__, card_id
    if not isinstance(orig, dict):
        return "no", "the page source is not a JSON object", card_id
    qs = orig.get("questions", [])
    if not isinstance(qs, list):
        return "no", "the questions in the page source are not a list", card_id
    for q in qs:
        al = q.get("alert") if isinstance(q, dict) else None
        if isinstance(al, dict) and al.get("id") == rec["id"]:
            return "exists", "", str(q.get("id") or card_id)
    d = copy.deepcopy(orig)
    dq = d.setdefault("questions", [])
    target = next((q for q in dq if isinstance(q, dict) and str(q.get("id")) == card_id), None)
    if target is not None:
        if not explicit:
            return "no", "a card with the id %s is already there; pass --card <another id>" % card_id, card_id
        if target.get("alert") is not None:
            return "no", "card %s already carries another alert; pass --card <another id>" % card_id, card_id
        target["alert"] = ra_alert_block(rec)
        mode = "attached"
    else:
        dq.append(ra_card(rec, card_id, seat, codename or (d.get("codename") if isinstance(d.get("codename"), str) else "")))
        mode = "added"
    d["updated"] = ra_stamp(ra_now())
    m = re.search(r"\n([ \t]+)\S", text)
    indent = (m.group(1) if "\t" in m.group(1) else len(m.group(1))) if m else 2
    crlf = "\r\n" in text
    out = json.dumps(d, indent=indent, ensure_ascii=bool(re.search(r"\\u[0-9a-fA-F]{4}", text)))
    if crlf:
        out = out.replace("\n", "\r\n")
    if text.endswith("\n"):
        out += "\r\n" if crlf else "\n"
    back = json.loads(out)                       # what was written must read back as the original plus the card
    if mode == "added":
        back["questions"].pop()
        if "questions" not in orig:
            back.pop("questions", None)
    else:
        for q in back["questions"]:
            if isinstance(q, dict) and str(q.get("id")) == card_id:
                q.pop("alert", None)
    if "updated" in orig:
        back["updated"] = orig["updated"]
    else:
        back.pop("updated", None)
    if back != orig:
        return "no", "the rewritten file would differ from the original beyond the card; nothing written", card_id
    st1 = os.stat(path)
    if (st1.st_mtime_ns, st1.st_size) != (st0.st_mtime_ns, st0.st_size):
        return "no", "the page source changed while it was being read; nothing written", card_id
    bak = "%s.pre-redalert-%s.bak" % (path, rec["id"])
    shutil.copy2(path, bak)
    tmp = "%s.%d.tmp" % (path, os.getpid())
    try:
        with open(tmp, "wb") as f:
            f.write((b"\xef\xbb\xbf" if bom else b"") + out.encode("utf-8"))
        for attempt in range(40):
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                if attempt == 39:
                    return "no", "the page source could not be replaced (busy); nothing written", card_id
                time.sleep(0.05)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    return mode, bak, card_id


def ra_apply_card(rec, o):
    """Everything after the log line exists: find the page source, write or print the card, record it on the log line, say
    what is next. Prints; the caller wraps it."""
    seat = rec.get("seat") or ""
    named = ra_txt(o.get("--card"), 80)
    card_id, codename = named or rec["id"], ra_txt(o.get("--codename"), 60)
    path, how = ra_fragment_for(seat, o.get("--fragment"))
    head = delegated_to(seat)
    if head and str(head).startswith("("):
        head = None
    state, info, cid = "no", how, card_id
    if path:
        state, info, cid = ra_write_card(path, rec, card_id, bool(named), seat, codename)
    if state in ("added", "attached", "exists"):
        if state == "exists":
            print("CARD EXISTS %s in %s: this alert is already on it, nothing was written" % (cid, path))
        else:
            print("CARD %s %s in %s (backup %s)" % ("ADDED" if state == "added" else "ATTACHED to existing card", cid, path, info))
        res = ra_set_card(rec["id"], cid, o.get("--parley"), "fragment " + path)
        print("LOG LINE %s" % ("updated: card " + cid if res == "ok" else "not updated (%s): run chime.py redalert card --id %s --card %s" % (res, rec["id"], cid)))
    else:
        print("CARD NOT WRITTEN: %s" % info)
        if named:
            print('ALERT BLOCK (add it as the "alert" field of your card %s):' % card_id)
            print(json.dumps(ra_alert_block(rec), indent=2, ensure_ascii=False))
        else:
            print('CARD BLOCK (add it to the "questions" list of %s):' % (path or "your page source, <SEAT>_PARLEY.json"))
            print(json.dumps(ra_card(rec, card_id, seat, codename), indent=2, ensure_ascii=False))
        print("THEN run: chime.py redalert card --id %s --card %s" % (rec["id"], card_id))
    if head:
        print("NEXT: tell %s in this turn that the card is in your page source, so it compiles and publishes it. A failed send "
              "does not end that duty: until the log line shows a card, ALERT CARD MISSING prints on your ticks and on its compile. "
              "Open the reply with RED ALERT only if it has not sounded yet" % head)
    else:
        print("NEXT: compile and publish your page in this turn. Open the reply with RED ALERT only if it has not sounded yet")


def ra_cmd_card(o):
    rid = ra_txt(o.get("--id"), 80)
    if not rid or not (o.get("--card") or o.get("--write")):
        print("ERROR: --id <id> and --card <card id> (record a card you added) or --write (write it into the page source) are required")
        return 2
    rec = next((a for a in ra_read() if a.get("id") == rid), None)
    if rec is None:
        print("NOT FOUND %s" % rid)
        return 1
    if o.get("--write"):
        ra_apply_card(rec, o)
        return 0
    where = ra_txt(o.get("--where"), 300) or ("fragment " + os.path.abspath(os.path.expanduser(o["--fragment"])) if o.get("--fragment") else "stated by the seat")
    res = ra_set_card(rid, ra_txt(o.get("--card"), 80), o.get("--parley"), where)
    if res != "ok":
        print("BUSY: the red alert log is locked by another process; run it again" if res == "busy" else "NOT FOUND %s" % rid)
        return 1
    print("CARD RECORDED %s on %s" % (ra_txt(o.get("--card"), 80), rid))
    return 0


def ra_cmd_uncarded(o):
    """One line per pending alert with no card: ALERT CARD MISSING <alert id> <seat> <hours>. With --updated
    "SEAT=ISO;SEAT=ISO" (the parley compile passes its fragments' updated stamps) also FRAGMENT STALE lines. Nothing
    is printed when there is nothing to say, and nothing when the log is absent."""
    try:
        minage = float(o["--min-age"]) if o.get("--min-age") not in (None, "") else float(RA_CARD_MIN)
        if minage < 0:
            raise ValueError
    except ValueError:
        print("ERROR: --min-age is a number of minutes, 0 or more")
        return 2
    want = set()
    if o.get("--seat"):
        want.add(o["--seat"].strip().lower())
    for s in (o.get("--crew") or "").split(","):
        if s.strip():
            want.add(s.strip().lower())
    now = ra_now().timestamp()
    rows = [a for a in ra_read() if a.get("source") != "example" and (a.get("verdict") or "pending") == "pending"
            and (not want or str(a.get("seat") or "").lower() in want)]
    for a in sorted(rows, key=ra_ts):
        t = ra_ts(a)
        if not t or a.get("card") or a.get("parley") or (now - t) / 60.0 < minage:
            continue
        print("ALERT CARD MISSING %s %s %.1f" % (a["id"], ra_txt(a.get("seat"), 80) or "-", (now - t) / 3600.0))
    for part in (o.get("--updated") or "").split(";"):
        seat, _, iso = part.partition("=")
        seat, when = seat.strip(), ra_parse(iso)
        if not seat or when is None:
            continue
        mine = [a for a in rows if str(a.get("seat") or "").lower() == seat.lower() and ra_ts(a)]
        if mine:
            newest = max(mine, key=ra_ts)
            if ra_ts(newest) - when.timestamp() >= 60:      # a stamp is to the minute: a card written in the same minute is not older
                print("FRAGMENT STALE %s updated %s, older than alert %s fired %s" % (
                    seat, ra_stamp(when), newest["id"], ra_stamp(ra_parse(newest.get("when")))))
    return 0


# ---- the commands "chime.py usage status|mute|unmute" and "chime.py sounds list|set|generate|reset|styles" -----
# Every command prints one line of plain text, or one JSON object with --json. Exit 0 done, 2 bad input, 1 failed to write.
# Nothing here writes inside the skill folder: only <chime home> (config.json, sounds/, usage_mute.json, config_log.txt).

MAX_SOUND_BYTES = 5 * 1024 * 1024
SOUND_EXTS = (".mp3", ".wav")      # what the player plays: .mp3 through the Windows media player, .wav through winsound
SAMPLE_RATE = 44100
MAX_GEN_MS = 1500


def _seg(kind, f0, f1, ms, gain, attack, release, gap=0):
    return {"type": kind, "freq": [f0, f1], "ms": ms, "gain": gain, "attack_ms": attack, "release_ms": release,
            "gap_ms": gap}


# One table, two readers: the generator below synthesises from it, and "sounds styles --json" prints it so the
# Soundboard can play the same thing in the browser. A segment starts when the one before it ends plus that one's
# gap_ms; a NEGATIVE gap_ms starts the next segment early, so the chord's three notes sound together.
STYLES = {
    "beep": [_seg("sine", 880, 880, 320, 0.40, 8, 80)],
    "double": [_seg("sine", 1046, 1046, 150, 0.40, 5, 40, 70), _seg("sine", 1046, 1046, 150, 0.40, 5, 40)],
    "rise": [_seg("sine", 400, 1200, 520, 0.40, 10, 120)],
    "fall": [_seg("sine", 1100, 250, 520, 0.40, 10, 120)],
    "chord": [_seg("sine", 523.25, 523.25, 700, 0.20, 15, 300, -700), _seg("sine", 659.25, 659.25, 700, 0.20, 15, 300, -700),
              _seg("sine", 783.99, 783.99, 700, 0.20, 15, 300)],
    "alarm": [_seg("square", f, f, 140, 0.22, 3, 10) for f in (880, 660, 880, 660, 880, 660)],
    "tick": [_seg("sine", 1800, 1200, 45, 0.45, 1, 30)],
    "soft": [_seg("sine", 523.25, 523.25, 450, 0.18, 90, 250)],
}
STYLE_ABOUT = {"beep": "one steady beep", "double": "two short high beeps", "rise": "a pitch that climbs",
               "fall": "a pitch that drops", "chord": "three notes together, a major chord", "alarm": "six square-wave"
               " alternations, harsh and urgent", "tick": "one very short click", "soft": "a quiet, slow-fading note"}
# the style "sounds generate" picks for an event when none is named
EVENT_STYLE = {"urgent": "double", "important": "chord", "boing": "rise", "default": "soft", "tick": "tick",
               "tick_ready": "tick", "tick_high": "tick", "tick_low": "tick", "tick_compaction": "tick", "peer": "beep",
               "compact": "fall", "relay": "double", "ack": "beep", "done": "rise", "questions": "double",
               "low_health": "alarm", "brakes": "fall", "red_alert": "alarm", "escalate": "rise", "abandon": "fall",
               "ignored": "soft"}
GEN_RX = re.compile(r"^gen-[a-z_]+-(?:%s)\.wav$" % "|".join(STYLES))


def style_ms(style):
    t, end = 0.0, 0.0
    for sg in STYLES[style]:
        end = max(end, t + sg["ms"])
        t += sg["ms"] + sg["gap_ms"]
    return int(round(end))


def synth_wav(style, path):
    """Write the style as a 16-bit mono WAV (standard library only). Returns its length in milliseconds."""
    import math
    import struct
    import wave
    segs = STYLES[style]
    ms = style_ms(style)
    if ms > MAX_GEN_MS:
        raise ValueError("style %s is %d ms, over the %d ms limit" % (style, ms, MAX_GEN_MS))
    total = int(round(SAMPLE_RATE * ms / 1000.0))
    buf = [0.0] * (total + 1)
    cursor = 0.0
    two_pi = 2 * math.pi
    for sg in segs:
        start = int(round(cursor * SAMPLE_RATE / 1000.0))
        cnt = int(round(sg["ms"] * SAMPLE_RATE / 1000.0))
        f0, f1 = sg["freq"]
        att = sg["attack_ms"] * SAMPLE_RATE / 1000.0
        rel = sg["release_ms"] * SAMPLE_RATE / 1000.0
        phase = 0.0
        for i in range(cnt):
            f = f0 + (f1 - f0) * (i / float(cnt))
            phase += two_pi * f / SAMPLE_RATE
            if sg["type"] == "square":
                x = 1.0 if math.sin(phase) >= 0 else -1.0
            elif sg["type"] == "triangle":
                x = (2.0 / math.pi) * math.asin(math.sin(phase))
            else:
                x = math.sin(phase)
            env = 1.0
            if att > 0 and i < att:
                env = i / att
            if rel > 0 and cnt - i < rel:
                env = min(env, (cnt - i) / rel)
            if start + i < len(buf):
                buf[start + i] += x * sg["gain"] * env
        cursor += sg["ms"] + sg["gap_ms"]
    tmp = "%s.%d.tmp" % (path, os.getpid())
    try:
        with wave.open(tmp, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            w.writeframes(b"".join(struct.pack("<h", int(max(-1.0, min(1.0, v)) * 32767)) for v in buf[:total]))
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    return ms


def jwrite(path, obj):
    """Write JSON through a temp file and a rename, so a reader never sees half a file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.%d.tmp" % (path, os.getpid())
    try:
        with io.open(tmp, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def config_note(by, text):
    """One line per change to the person's files, so a stray sound or mute can be traced."""
    try:
        p = os.path.join(CHIME_HOME, "config_log.txt")
        os.makedirs(CHIME_HOME, exist_ok=True)
        with io.open(p, "a", encoding="utf-8") as fh:
            fh.write("%s | %s | %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), by or "?", text))
        if os.path.getsize(p) > 60000:
            with io.open(p, encoding="utf-8", errors="replace") as fh:
                keep = fh.readlines()[-300:]
            with io.open(p, "w", encoding="utf-8") as fh:
                fh.writelines(keep)
    except Exception:
        pass


class CmdError(Exception):
    pass


def cmd_args(argv, valued, flags=()):
    """(positionals, options). Raises CmdError on an unknown option or a missing value."""
    pos, o, i = [], {}, 0
    while i < len(argv):
        a = argv[i]
        if a in flags:
            o[a] = True
            i += 1
        elif a in valued:
            if i + 1 >= len(argv):
                raise CmdError("%s needs a value" % a)
            o[a] = argv[i + 1]
            i += 2
        elif a.startswith("--"):
            raise CmdError("unknown option %s" % a)
        else:
            pos.append(a)
            i += 1
    return pos, o


def say(o, obj, text):
    print(json.dumps(obj, ensure_ascii=False) if o.get("--json") else text)


def pretty(iso):
    return str(iso or "").replace("T", " ")[:16]


def num(p):
    p = round(float(p), 1)
    return int(p) if p == int(p) else p


# ---- usage: status, mute, unmute -------------------------------------------------------------------------------

def resolve_account(token):
    """(folder, colour) from a colour in account_names, a home folder name (either case) or "this"."""
    names = _C.get("account_names") or ({account_folder(): account_folder()} if account_folder() else {})
    t = (token or "").strip()
    if not t:
        raise CmdError("an account is required: one of %s or this" % ", ".join(sorted(set(names.values()))) )
    if t.lower() == "this":
        f = account_folder()
        return f, color_of(f)
    for folder, color in names.items():
        if t.lower() in (str(color).lower(), str(folder).lower()):
            return folder, color
    raise CmdError("unknown account %s (known: %s, or this)" % (t, ", ".join(sorted(set(names.values())))))


def account_homes(folder):
    """The config home paths an account folder can have: this process's, and the one sessions_glob implies."""
    homes = []
    if folder.lower() == account_folder().lower():
        homes.append(account_home())
    g = _C.get("sessions_glob") or ""
    segs = re.split(r"[\\/]", g)
    for idx, sg in enumerate(segs):
        if "*" in sg:
            sep = "\\" if "\\" in g else "/"
            homes.append(sep.join(segs[:idx] + [folder] + segs[idx + 1:idx + 2]))
            break
    return homes


def find_cache(folder):
    """(data, mtime) of the newest usage cache this account has, or (None, None). Found by the tag of either spelling of
    its home path, and by the account folder the cache records."""
    d = os.path.join(tempfile.gettempdir(), "chime")
    tags = []
    for h in account_homes(folder):
        for t in cache_tags(h):
            if t not in tags:
                tags.append(t)
    paths = [os.path.join(d, "usage_%s.json" % t) for t in tags]
    try:
        for f in os.listdir(d):
            if f.startswith("usage_") and f.endswith(".json") and not f.startswith(("usage_fired_", "usage_failed_")):
                p = os.path.join(d, f)
                if p not in paths and str(_jload(p).get("folder") or "").lower() == folder.lower():
                    paths.append(p)
    except OSError:
        pass
    best, bt = None, None
    for p in paths:
        try:
            m = os.path.getmtime(p)
        except OSError:
            continue
        if bt is None or m > bt:
            best, bt = p, m
    if not best:
        return None, None
    d2 = _jload(best)
    return (d2, bt) if d2 else (None, None)


def log_reading(folder):
    """The last usage_log.txt line for this account that carries values, as a last_reading (no resets_at), or None."""
    try:
        color = color_of(folder).lower()
        with io.open(USAGE_LOG, encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()[-400:]
        for ln in reversed(lines):
            parts = [x.strip() for x in ln.rstrip("\n").split(" | ", 3)]
            if len(parts) < 4 or parts[1].lower() != color or parts[3] == "no values":
                continue
            vals = []
            for item in parts[3].split(", "):
                m = re.match(r"^(.*) (\d+(?:\.\d+)?)%$", item.strip())
                if m:
                    vals.append({"limit": m.group(1), "pct": num(m.group(2))})
            if vals:
                return {"at": parts[0].replace(" ", "T"), "values": vals}
    except Exception:
        pass
    return None


def last_reading(folder):
    data, mt = find_cache(folder)
    if data and isinstance(data.get("vals"), list) and data["vals"]:
        resets = data.get("resets") if isinstance(data.get("resets"), dict) else {}
        vals = []
        for v in data["vals"]:
            try:
                row = {"limit": v[0], "pct": num(v[1])}
            except Exception:
                continue
            if resets.get(v[0]):
                row["resets_at"] = resets[v[0]]
            vals.append(row)
        if vals:
            return {"at": data.get("at") or now_iso(mt), "values": vals}
    return log_reading(folder)


def cycle_until(reading, now):
    """The reset of the cycle that is over the alert line: the latest known reset among the limits at or above the line
    (a reset already past is ignored). With nothing over the line, the latest known reset of any limit. None when no
    usable reset time is known."""
    vals = (reading or {}).get("values") or []
    over = [v for v in vals if float(v.get("pct") or 0) >= USAGE_ALERT_PCT]
    pool = over or vals
    cands = []
    for v in pool:
        t = parse_local(v.get("resets_at"))
        if t and t > now:
            cands.append(t)
    return max(cands) if cands else None


def stopgap_until(folder):
    """A usage_fired marker dated in the future (a stopgap mute made by hand): when it ends, else None. Read only."""
    d = os.path.join(tempfile.gettempdir(), "chime")
    best = None
    for h in account_homes(folder):
        p = _newest(d, "usage_fired_", cache_tags(h))
        if p:
            m = os.path.getmtime(p) + USAGE_ALERT_EVERY          # the alarm stays quiet until its marker is 30 min old
            if m > time.time() and (best is None or m > best):
                best = m
    return now_iso(best) if best else None


def usage_status_obj():
    now = datetime.datetime.now()
    ents = mute_entries()
    names = _C.get("account_names") or ({account_folder(): account_folder()} if account_folder() else {})
    rows, seen = [], set()
    for folder in list(names) + [k for k in ents if k not in [str(n).lower() for n in names]]:
        key = folder.lower()
        if key in seen:
            continue
        seen.add(key)
        e = ents.get(key) if entry_live(ents.get(key), now) else None
        e = e or {}
        row = {"account": color_of(folder), "home": folder, "muted": bool(e), "until": e.get("until"),
               "until_source": e.get("until_source"), "by": e.get("by"), "why": e.get("why"), "set_at": e.get("set_at"),
               "last_reading": last_reading(folder)}
        sg = stopgap_until(folder)
        if sg:
            row["marker_quiet_until"] = sg
        rows.append(row)
    return {"alert_pct": num(USAGE_ALERT_PCT), "accounts": rows}


def cmd_usage_status(o):
    obj = usage_status_obj()
    bits = []
    for a in obj["accounts"]:
        if a["muted"]:
            bits.append("%s muted until %s (%s%s)" % (a["account"], pretty(a["until"]), a["until_source"],
                                                       ", by %s" % a["by"] if a["by"] else ""))
        else:
            lr = a["last_reading"]
            top = max(lr["values"], key=lambda v: v["pct"]) if lr and lr["values"] else None
            bits.append("%s not muted, %s" % (a["account"], "%s %s%% at %s" % (top["limit"], top["pct"], pretty(lr["at"])[11:])
                                              if top else "no reading"))
            if a.get("marker_quiet_until"):
                bits[-1] += ", quiet until %s by an old marker file" % pretty(a["marker_quiet_until"])
    say(o, obj, "USAGE alert line %s%%. %s." % (obj["alert_pct"], ". ".join(bits) or "no accounts"))
    return 0


def prune_mutes(ents, now):
    return {k: v for k, v in ents.items() if entry_live(v, now)}


def cmd_usage_mute(pos, o):
    if len(pos) != 1:
        raise CmdError("usage: usage mute <ACCOUNT> [--cycle | --until \"YYYY-MM-DD HH:MM\"] [--by SEAT] [--why \"text\"]")
    if o.get("--cycle") and o.get("--until"):
        raise CmdError("give --cycle or --until, not both")
    folder, color = resolve_account(pos[0])
    now = datetime.datetime.now().replace(microsecond=0)
    if o.get("--until"):
        until = parse_local(o["--until"])
        if not until:
            raise CmdError("--until wants \"YYYY-MM-DD HH:MM\" (local time), got %r" % o["--until"])
        if until <= now:
            raise CmdError("--until %s is not in the future" % o["--until"])
        source = "given"
    else:
        until = cycle_until(last_reading(folder), now)
        source = "cycle"
        if not until:
            until, source = now + datetime.timedelta(hours=24), "fallback_24h"
    ents = prune_mutes(mute_entries(), now)
    entry = {"account": color, "home": folder, "until": until.strftime("%Y-%m-%dT%H:%M:%S"), "until_source": source,
             "by": o.get("--by") or None, "why": o.get("--why") or None, "set_at": now_iso()}
    ents[folder.lower()] = entry
    jwrite(USAGE_MUTE_FILE, {"version": 1, "accounts": ents})
    config_note(o.get("--by"), "usage mute %s until %s (%s)" % (color, entry["until"], source))
    how = {"cycle": "the reset of the cycle over the line", "given": "the time given",
           "fallback_24h": "24 hours, because no reset time is known"}[source]
    obj = dict(entry, ok=True, muted=True)
    say(o, obj, "MUTED %s low-usage alarm until %s (%s; until_source %s%s)"
        % (color, pretty(entry["until"]), how, source, ", by %s" % entry["by"] if entry["by"] else ""))
    return 0


def cmd_usage_unmute(pos, o):
    if len(pos) != 1:
        raise CmdError("usage: usage unmute <ACCOUNT> [--by SEAT]")
    folder, color = resolve_account(pos[0])
    now = datetime.datetime.now()
    ents = mute_entries()
    was = entry_live(ents.get(folder.lower()), now)
    ents = prune_mutes(ents, now)
    ents.pop(folder.lower(), None)
    jwrite(USAGE_MUTE_FILE, {"version": 1, "accounts": ents})
    config_note(o.get("--by"), "usage unmute %s (was %s)" % (color, "muted" if was else "not muted"))
    say(o, {"ok": True, "account": color, "home": folder, "muted": False, "was_muted": was},
        "UNMUTED %s low-usage alarm" % color if was else "%s low-usage alarm was not muted" % color)
    return 0


def usage_main(argv):
    sub = (argv[0] if argv else "").lower()
    if sub == "status":
        pos, o = cmd_args(argv[1:], (), ("--json",))
        if pos:
            raise CmdError("usage status takes no account")
        return cmd_usage_status(o)
    if sub == "mute":
        pos, o = cmd_args(argv[1:], ("--until", "--by", "--why"), ("--cycle", "--json"))
        return cmd_usage_mute(pos, o)
    if sub == "unmute":
        pos, o = cmd_args(argv[1:], ("--by",), ("--json",))
        return cmd_usage_unmute(pos, o)
    raise CmdError("usage: chime.py usage status [--json] | mute <ACCOUNT> [--cycle | --until \"YYYY-MM-DD HH:MM\"] "
                   "[--by SEAT] [--why \"text\"] | unmute <ACCOUNT> [--by SEAT]")


# ---- sounds: list, set, generate, reset, styles ------------------------------------------------------------------

def ref_path(ev, raw):
    """The file a config value names: a gen: tone's file, a skill-relative path made absolute, or ''."""
    if not raw:
        return ""
    if raw.startswith("gen:"):
        return gen_sound_path(ev, raw) or ""
    return raw if os.path.isabs(raw) else os.path.normpath(os.path.join(_ROOT, raw))


def sound_rows():
    user, _err = load_user_config()
    eff = merge_config(_DEFAULTS, user)
    names = eff.get("names") if isinstance(eff.get("names"), dict) else {}
    labels = eff.get("labels") if isinstance(eff.get("labels"), dict) else {}
    rows = []
    for ev in EVENTS:
        raw = eff.get(ev) if isinstance(eff.get(ev), str) else ""
        dflt = _DEFAULTS.get(ev) if isinstance(_DEFAULTS.get(ev), str) else ""
        missing_ref = None
        if raw.startswith("user:"):
            p = user_sound_path(raw)
            if p and os.path.isfile(p):
                source = "generated" if GEN_RX.match(os.path.basename(p)) else "user"
                path = p
            else:                                   # the person's file is gone: what plays is the skill default
                missing_ref, raw, source = raw, dflt, "default"
                path = ref_path(ev, raw)
        else:
            source = "default" if raw == dflt else ("generated" if raw.startswith("gen:") else "user")
            path = ref_path(ev, raw)
        name = names.get(ev) or (os.path.splitext(os.path.basename(path))[0] if path else "") or ev
        made_on_use = raw.startswith("gen:")        # a tone the skill makes the first time it is needed: always available
        row = {"event": ev, "label": labels.get(ev) or ev.replace("_", " "), "file": raw, "source": source,
               "exists": bool(path and (made_on_use or os.path.isfile(path))), "name": name}
        style = (raw[4:] if made_on_use else (re.match(r"^gen-[a-z_]+-([a-z]+)\.wav$", os.path.basename(path)) or [None, None])[1])
        if style:
            row["style"] = style
        if missing_ref:
            row["mapped_missing"] = missing_ref
        rows.append(row)
    return rows


def need_event(ev):
    if ev not in EVENTS:
        raise CmdError("unknown event %s (events: %s)" % (ev, ", ".join(EVENTS)))
    return ev


def editable_config():
    user, err = load_user_config()
    if err:                                         # never overwrite a file the person may be mid-edit on
        raise CmdError("%s: fix or remove %s first" % (err, USER_CONFIG))
    return user


def cmd_sounds_list(o):
    rows = sound_rows()
    obj = {"events": rows, "user_dir": USER_SOUNDS, "accepts": list(SOUND_EXTS)}
    cnt = {s: sum(1 for r in rows if r["source"] == s) for s in ("default", "user", "generated")}
    miss = [r["event"] for r in rows if not r["exists"]]
    say(o, obj, "SOUNDS %d events: %d default, %d user, %d generated; %s; folder %s"
        % (len(rows), cnt["default"], cnt["user"], cnt["generated"],
           ("no file for %d (%s%s)" % (len(miss), ", ".join(miss[:5]), ", ..." if len(miss) > 5 else "")) if miss
           else "every file exists", USER_SOUNDS))
    return 0


def clean_name(stem):
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-._") or "sound"
    return s[:60]


def sniff_audio(path, ext):
    with open(path, "rb") as fh:
        head = fh.read(131072)
    if ext == ".wav":
        return head[:4] == b"RIFF" and head[8:12] == b"WAVE"
    return head[:3] == b"ID3" or re.search(rb"\xff[\xe0-\xff]", head) is not None


def cmd_sounds_set(pos, o):
    if len(pos) != 2:
        raise CmdError("usage: sounds set <event> <path to an audio file> [--by SEAT]")
    ev = need_event(pos[0])
    src = os.path.abspath(os.path.expanduser(pos[1]))
    if not os.path.isfile(src):
        raise CmdError("file not found: %s" % src)
    ext = os.path.splitext(src)[1].lower()
    if ext not in SOUND_EXTS:
        raise CmdError("unsupported file type %s: the player plays %s (ogg, m4a and flac are not routed to a decoder)"
                       % (ext or "(none)", " and ".join(SOUND_EXTS)))
    size = os.path.getsize(src)
    if size > MAX_SOUND_BYTES:
        raise CmdError("file is %.1f MB, over the 5 MB limit" % (size / 1048576.0))
    if size == 0 or not sniff_audio(src, ext):
        raise CmdError("%s does not look like a %s file" % (os.path.basename(src), ext[1:]))
    cfg = editable_config()
    import shutil
    base = clean_name(os.path.splitext(os.path.basename(src))[0])
    if base.lower().startswith("gen-"):             # gen-* is the generator's namespace
        base = "user-" + base
    os.makedirs(USER_SOUNDS, exist_ok=True)

    def digest(p):
        h = hashlib.sha256()
        with open(p, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    want, n, name = digest(src), 1, base + ext
    while os.path.exists(os.path.join(USER_SOUNDS, name)):
        if digest(os.path.join(USER_SOUNDS, name)) == want:     # the same file again: reuse it
            break
        n += 1
        name = "%s-%d%s" % (base, n, ext)
    dest = os.path.join(USER_SOUNDS, name)
    if not os.path.exists(dest):
        tmp = "%s.%d.tmp" % (dest, os.getpid())
        try:
            shutil.copyfile(src, tmp)
            os.replace(tmp, dest)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
    cfg[ev] = "user:" + name
    jwrite(USER_CONFIG, cfg)
    config_note(o.get("--by"), "sounds set %s -> user:%s" % (ev, name))
    say(o, {"ok": True, "event": ev, "file": "user:" + name, "path": dest, "bytes": size},
        "SET %s -> user:%s (%.0f KB %s)" % (ev, name, max(1, size / 1024.0), ext[1:]))
    return 0


def generate_one(ev, style, cfg):
    os.makedirs(USER_SOUNDS, exist_ok=True)
    name = "gen-%s-%s.wav" % (ev, style)
    ms = synth_wav(style, os.path.join(USER_SOUNDS, name))
    cfg[ev] = "user:" + name
    return {"event": ev, "style": style, "file": "user:" + name, "ms": ms}


def cmd_sounds_generate(pos, o):
    allm = bool(o.get("--all-missing"))
    if allm and pos:
        raise CmdError("give an event or --all-missing, not both")
    if not allm and len(pos) != 1:
        raise CmdError("usage: sounds generate <event> [--style STYLE] [--by SEAT] | sounds generate --all-missing")
    style = (o.get("--style") or "").lower()
    if style and style not in STYLES:
        raise CmdError("unknown style %s (styles: %s)" % (style, ", ".join(STYLES)))
    cfg = editable_config()
    made = []
    if allm:
        for r in sound_rows():
            if not r["exists"]:
                made.append(generate_one(r["event"], style or EVENT_STYLE.get(r["event"], "beep"), cfg))
    else:
        ev = need_event(pos[0])
        made.append(generate_one(ev, style or EVENT_STYLE.get(ev, "beep"), cfg))
    if made:
        jwrite(USER_CONFIG, cfg)
        config_note(o.get("--by"), "sounds generate %s" % ", ".join("%s:%s" % (m["event"], m["style"]) for m in made))
    if allm:
        txt = ("GENERATED %d events: %s" % (len(made), ", ".join("%s (%s)" % (m["event"], m["style"]) for m in made))
               if made else "GENERATED none: every event already has a file")
    else:
        m = made[0]
        txt = "GENERATED %s -> %s (style %s, %d ms)" % (m["event"], m["file"], m["style"], m["ms"])
    say(o, {"ok": True, "generated": made}, txt)
    return 0


def cmd_sounds_reset(pos, o):
    if len(pos) != 1:
        raise CmdError("usage: sounds reset <event> [--by SEAT]")
    ev = need_event(pos[0])
    cfg = editable_config()
    had = ev in cfg
    if had:
        cfg.pop(ev, None)
        jwrite(USER_CONFIG, cfg)
        config_note(o.get("--by"), "sounds reset %s" % ev)
    say(o, {"ok": True, "event": ev, "reset": had},
        "RESET %s: back to the skill default (your file stays in %s)" % (ev, USER_SOUNDS) if had
        else "RESET %s: nothing to reset, it already uses the skill default" % ev)
    return 0


def styles_obj():
    return {"sample_rate": SAMPLE_RATE, "max_ms": MAX_GEN_MS,
            "recipe": "Segments play in order; each starts when the one before it ends plus that one's gap_ms (a negative "
                      "gap_ms starts the next one early, which is how the chord sounds together). Frequency moves "
                      "linearly from freq[0] to freq[1] in Hz over ms. Gain ramps linearly from 0 over attack_ms, holds, "
                      "and ramps linearly to 0 over the last release_ms. Types: sine, square, triangle.",
            "default_style": dict(EVENT_STYLE),
            "styles": {k: {"about": STYLE_ABOUT[k], "ms": style_ms(k), "segments": v} for k, v in STYLES.items()}}


def cmd_sounds_styles(o):
    say(o, styles_obj(), "STYLES %s" % ", ".join("%s (%d ms)" % (k, style_ms(k)) for k in STYLES))
    return 0


def sounds_main(argv):
    sub = (argv[0] if argv else "").lower()
    if sub == "list":
        pos, o = cmd_args(argv[1:], (), ("--json",))
        return cmd_sounds_list(o)
    if sub == "set":
        pos, o = cmd_args(argv[1:], ("--by",), ("--json",))
        return cmd_sounds_set(pos, o)
    if sub == "generate":
        pos, o = cmd_args(argv[1:], ("--style", "--by"), ("--all-missing", "--json"))
        return cmd_sounds_generate(pos, o)
    if sub == "reset":
        pos, o = cmd_args(argv[1:], ("--by",), ("--json",))
        return cmd_sounds_reset(pos, o)
    if sub == "styles":
        pos, o = cmd_args(argv[1:], (), ("--json",))
        return cmd_sounds_styles(o)
    raise CmdError("usage: chime.py sounds list [--json] | set <event> <file> [--by SEAT] | generate <event> [--style STYLE] "
                   "[--by SEAT] | generate --all-missing | reset <event> [--by SEAT] | styles [--json]")


def cli_main(mode, argv):
    """Exit code: 0 done, 2 bad input (the message starts ERROR), 1 the command could not write its files."""
    as_json = "--json" in argv
    try:
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
        return usage_main(argv) if mode == "usage" else sounds_main(argv)
    except (CmdError, ValueError) as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False) if as_json else "ERROR: %s" % e)
        return 2
    except Exception as e:
        msg = "%s command failed (%s)" % (mode, e.__class__.__name__)
        print(json.dumps({"ok": False, "error": msg}) if as_json else "ERROR: %s" % msg)
        return 1


def main():
    global _SEAT
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "prompt":
        try:
            data = json.loads(sys.stdin.read() or "{}")
        except Exception:
            data = {}
        try:
            prompt = data.get("prompt") or ""
            if ACK and direct_request(prompt) and not system_prompt(data) and not brakes_on(data.get("session_id", "")) \
                    and not already_played(data.get("session_id", ""), mode, prompt):
                ack_log(data, prompt)
                play_detached("ack", tab_title(data.get("transcript_path") or "") or "")
        except Exception:
            pass
        ctx = itext("brakes_rules") if brakes_on(data.get("session_id", "")) else rules_for_prompt(data)
        sys.stdout.write(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                                            "additionalContext": ctx}}))
        return 0
    if mode == "sound":
        key = sys.argv[2] if len(sys.argv) > 2 else ""
        _SEAT = sys.argv[3] if len(sys.argv) > 3 else ""
        if key in SOUNDS:
            hold_for_dictation()                     # already detached, so it may simply wait
            play(key)
        return 0
    if mode == "held":                               # a turn's sounds, held until the dictation ends
        try:
            job = json.loads(sys.argv[2])
        except Exception:
            return 0
        _SEAT = job.get("label") or ""
        run_seq(job.get("seq") or [], _SEAT, bool(job.get("say")),
                [tuple(x) for x in (job.get("toasts") or []) if len(x) == 2], held=True)
        return 0
    if mode == "redalert":                           # the log commands; the only mode whose exit code is not 0
        return ra_main(sys.argv[2:])
    if mode in ("usage", "sounds"):                  # the mute and sound commands; exit 0, 1 or 2 like redalert
        return cli_main(mode, sys.argv[2:])
    if mode == "play":
        kind = sys.argv[2].lower() if len(sys.argv) > 2 else "urgent"
        label = sys.argv[3] if len(sys.argv) > 3 else "a session"
        what = sys.argv[4] if len(sys.argv) > 4 else "Look at this session now."
        _SEAT = label
        if kind in ("major", "blocked"):
            toast("MAJOR PROBLEM FOUND: " + label, what)
            seq = ["urgent", "boing", "important"]
        elif kind == "important":
            toast("Important: " + label, what)
            seq = ["boing", "important"]
        elif kind == "compact":
            toast("Compaction prompt ready: " + label, what)
            seq = ["compact"]
        elif kind in ("redalert", "red_alert", "red-alert"):     # sounds now, and the Stop hook adds nothing
            toast("RED ALERT: " + label, ra_txt(what, 140))
            seq = ["red_alert"]
            try:
                if not (muted() or silenced("red_alert")):
                    ra_mark("", "", label)
                    ra_seen_stamp(label)
            except Exception:
                pass
        else:
            toast("URGENT: " + label, what)
            seq = ["urgent"]
        run_seq(seq, label, True)                    # mid-turn alerts always need the person; after a dictation
        return 0
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except Exception:
        data = {}
    sid = data.get("session_id", "")
    tp = data.get("transcript_path", "")
    if mode == "autocompact":
        text = last_assistant_text(tp)
        if already_played(sid, mode, text):
            return 0
        _SEAT = session_label(sid, text, tp)
        toast("Auto-compacting: " + _SEAT, "This session filled its context and is compacting now.")
        if not brakes_on(sid):                       # a braked session stays silent
            run_seq(["compact"], _SEAT)
    elif mode == "decision":
        text = data.get("last_assistant_message") or last_assistant_text(tp)
        if _gate_will_block(data):
            return 0
        if already_played(sid, mode, text):
            if DRY:
                print("SKIPPED duplicate")
            return 0
        _DEFER["on"] = True
        label = session_label(sid, text, tp)
        _SEAT = label
        key = opener(text)
        if key == "redalert":                        # not a repeat, and not already sounded mid-turn
            key = ra_gate(sid, label, text)
        mgr = delegated_to(sound_line_seat(text))
        if mgr and key == "redalert":                # the one attention sound a delegated seat keeps
            if DRY:
                print("DELEGATED to %s: RED ALERT still sounds" % mgr)
        elif mgr:                                    # a delegated seat's manager routes and sounds its questions
            if DRY:
                print("DELEGATED to %s: attention sounds suppressed" % mgr)
            key = None
        ra = key == "redalert"
        u, i = FLAGS.get(key, (False, False))
        relay = bool(RELAY_RX.search(text or ""))
        origin = turn_origin(tp)
        seq = []
        if origin == "tick":
            kc = kw()
            st, skey = {}, None
            if kc and tp:
                skey = kc.session_key(tp)
                st = kc.load_state(skey) or {}
            lk = loop_kind(st.get("loop") or STATE.get("tick_loop"))
            armed = loop_kind(st.get("armed_loop") or st.get("loop") or STATE.get("tick_loop"))
            blocked = key == "major"
            prev = st.get("blocked_ticks") or 0
            prev = prev if isinstance(prev, int) else 0
            count = prev + 1 if blocked else 0
            # keepwarm_tick.py upgrades a Low/Ready chain to High after more than 2 blocked ticks
            escalate = blocked and armed in ("low", "ready") and count == 3 and "escalate" in SOUNDS
            asks = bool(ASKS_RX.search(text or "")) and not mgr   # only a parley head surfacing reports' questions
            qcount = (st.get("question_ticks") or 0) + 1 if asks else 0
            # a seat whose #StandReadyHigh ticks keep needing the person with no prompt from them is ignored
            needy = bool(blocked or u or i or ra or relay or asks or (QFM_RX.search(text or "") and not mgr))
            was_ab = bool(st.get("abandoned"))
            ig = st.get("ignored_ticks") or 0
            ig = ig if isinstance(ig, int) else 0
            ig = (ig + 1 if lk == "high" else ig) if needy else 0
            abandon = needy and not was_ab and lk == "high" and ig >= IGNORE_AFTER
            ab = needy and (was_ab or abandon)
            if clocked_out():                        # the person is out, so nothing escalates and no counter moves
                escalate = abandon = False
                skey = None
                if DRY:
                    print("CLOCKED OUT: tick counters frozen")
            if kc and skey:
                kc.save_state(skey, {"blocked_ticks": count, "question_ticks": qcount, "ignored_ticks": ig,
                                     "abandoned": ab})
            if DRY:
                print("TICK loop=%s blocked_ticks=%d question_ticks=%d ignored_ticks=%d abandoned=%s"
                      % (lk, count, qcount, ig, ab))
            if ra:                                   # a red alert is a new finding: red_alert alone, even if ignored
                toast("RED ALERT: " + label, ra_toast_body(text))
                seq = ["red_alert"]
            elif was_ab and needy and "ignored" in SOUNDS:   # still ignored: one sound, so the person can find it
                toast("Ignored (%d ticks): %s" % (max(ig, IGNORE_AFTER), label),
                      "This seat has needed you for a while and is waiting on #StandReadyLow.")
                seq, relay = ["ignored"], False
            elif blocked and lk != "keepwarm":
                toast("BLOCKED (%d ticks): %s" % (count, label), "This seat is blocked on you." +
                      (" Its loop now runs as #StandReadyHigh." if escalate else ""))
                seq = ["urgent", "urgent", "urgent"] + (["escalate"] if escalate else [])
            elif asks and qcount >= QUESTIONS_AFTER and "questions" in SOUNDS and questions_due():
                toast("Questions waiting (%d ticks): %s" % (qcount, label), "This seat has questions for you.")
                seq = ["questions"]
                if not muted():
                    questions_played()
            elif u or i:
                toast("Tick needs you: " + label, "A tick report opened with a decision phrase.")
                seq = flag_seq(u, i)
            elif relay:
                toast("Baton to relay: " + label, "This tick carries a baton for you to paste.")
                seq, relay = ["relay"], False
            else:                                    # a quiet tick plays its sound and shows no toast
                seq = [TICK_SOUND[lk]]
            if abandon:                                  # ignored, so the chain drops to #StandReadyLow
                toast("Ignored: " + label, "No answer for %d #StandReadyHigh ticks; it drops to #StandReadyLow until "
                      "you prompt it." % ig)
                if "abandon" in SOUNDS:
                    seq.append("abandon")
                if DRY:
                    print("ABANDONED after %d ignored #StandReadyHigh ticks" % ig)
        else:
            if origin == "human":                    # the person answered, so the question count restarts
                try:
                    kc = kw()
                    if kc and tp:
                        kc.save_state(kc.session_key(tp), {"question_ticks": 0, "ignored_ticks": 0, "abandoned": False})
                except Exception:
                    pass
            # a turn the person started opens with done unless it is blocked (MAJOR PROBLEM FOUND)
            seq = ["done"] if origin == "human" and key not in ("major", "redalert") else []   # the person's own turns only
            if ra:                                   # red_alert alone (relay may follow); not done, peer or default
                toast("RED ALERT: " + label, ra_toast_body(text))
                seq += ["red_alert"]
            elif u or i:
                toast(("URGENT" if u else "Important") + (" + important" if (u and i) else "") + ": " + label,
                      "Open this session: it is waiting on you.")
                seq += flag_seq(u, i)
            elif relay:
                toast("Baton to relay: " + label, "This reply carries a baton for you to paste.")
                seq, relay = seq + ["relay"], False
            elif origin == "peer":
                toast("Session message handled: " + label, "Another session's message started this turn.")
                seq = ["peer"]
            elif origin == "human":                  # a system turn finishing is not news
                toast("Finished: " + label, "This session finished your prompt.")
        if relay:
            seq.append("relay")
        if hands_compact_prompt(text):               # always the very last sound of the turn
            toast("Compaction prompt ready: " + label, "This session wrote its compaction prompt; nothing else is left to do.")
            seq.append("compact")
        if brakes_on(sid):                           # brakes on, so only the brakes sound (and low usage)
            _DEFER["items"] = [("Brakes on: " + label, "Parked on #KeepWarm until /brakes off.")]
            seq = ["brakes"] if "brakes" in SOUNDS else []
            if DRY:
                print("BRAKES ON")
        _DEFER["on"] = False
        low = usage_alert() if "low_health" in SOUNDS else None
        if low:                                      # shown and heard first, on any kind of turn
            acct = account_name()
            toast("%s%s limit at %.0f%%" % (acct + " " if acct else "", low[0], low[1]),
                  "Claude usage on %s is within %.0f%% of this limit." % (acct or "this account", 100 - USAGE_ALERT_PCT))
            run_seq(["low_health"], label)
        say = any(t.startswith(NEEDED) for t, _ in _DEFER["items"]) and not brakes_on(sid)
        if SPEAK == "all" and _DEFER["items"] and not brakes_on(sid):
            say = True
        # this turn's own toast just before its sounds, then the session's name on a turn that needs the person;
        # all three wait together while the person dictates
        run_seq(seq, label, say, _DEFER["items"])
    return 0


if __name__ == "__main__":
    rc = 0
    try:
        rc = main()
    except Exception:
        rc = 0
    # every hook mode exits 0; only the "redalert" and "usage" / "sounds" commands report their code to the seat
    sys.exit(rc if (sys.argv[1:2] in (["redalert"], ["usage"], ["sounds"]) and isinstance(rc, int)) else 0)
