#!/usr/bin/env python
# govern_posttick_test.py  hand-fed stdin test of govern_posttick.py.
# Feeds the hook a Stop-event JSON for a fake session and checks, per case: exit 0, empty stdout and stderr, wall time under
# 200 ms (the whole process, Python start included), and the one log line the hook writes in --dry --log-all mode.
# Cases: tick just written, human turn (old tick), absent state file, stopped, last_tick null, govern.json enabled false,
# govern.stop present, already trimmed for this tick, and one real detached spawn of a harmless probe command to prove the
# child outlives the hook. Nothing is trimmed, and everything (settings, log, state) lives in a temp folder.
import sys
import os
import json
import time
import tempfile
import subprocess
import datetime
import shutil

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "govern_posttick.py")
PY = sys.executable
fails = 0
tmp = tempfile.mkdtemp(prefix="posttick_test_")
kw = os.path.join(tmp, "ticks")
os.makedirs(kw)
log_path = os.path.join(tmp, "govern.log")
base_cfg = {"enabled": True, "posttick_window_seconds": 120, "log_path": log_path}


def gov_dir(name, enabled=True, stop=False, trimmed=None):
    d = os.path.join(tmp, "gov_" + name)
    os.makedirs(d, exist_ok=True)
    cfg = dict(base_cfg)
    cfg["enabled"] = enabled
    json.dump(cfg, open(os.path.join(d, "govern.json"), "w"))
    if stop:
        open(os.path.join(d, "govern.stop"), "w").write("{}")
    if trimmed:
        json.dump(trimmed, open(os.path.join(d, "posttick.state.json"), "w"))
    return d


DEFAULT_GOV = gov_dir("default")


def now_iso(offset_s=0):
    return (datetime.datetime.now() + datetime.timedelta(seconds=offset_s)).isoformat(timespec="seconds")


def run(case, state, expect, gov=None, extra=None, wait_file=None):
    global fails
    sid = "testcase-" + case
    if state is not None:
        json.dump(state, open(os.path.join(kw, sid + ".json"), "w"))
    args = [PY, "-I", HOOK, "--state-dir", kw, "--log-all", "--govern-dir", gov or DEFAULT_GOV]
    args += extra if extra is not None else ["--dry"]
    ev = json.dumps({"session_id": sid, "transcript_path": "C:\\x\\" + sid + ".jsonl", "hook_event_name": "Stop"})
    t0 = time.perf_counter()
    r = subprocess.run(args, input=ev, capture_output=True, text=True)
    ms = (time.perf_counter() - t0) * 1000
    lines = open(log_path, encoding="ascii", errors="replace").read().splitlines() if os.path.exists(log_path) else []
    last = [ln for ln in lines if "session " + sid[:24] in ln][-1:] or [""]
    expects = expect if isinstance(expect, tuple) else (expect,)
    ok = (r.returncode == 0 and r.stdout == "" and r.stderr == "" and ms < 200 and any(e in last[0] for e in expects))
    note = ""
    if wait_file:
        time.sleep(2.0)
        present = os.path.exists(wait_file)
        ok = ok and present
        note = " child-wrote-file=%s" % present
    if not ok:
        fails += 1
    print("%s  %-22s exit=%d out=%d err=%d %.0f ms%s | %s" % ("PASS" if ok else "FAIL", case, r.returncode, len(r.stdout),
                                                            len(r.stderr), ms, note, last[0][:150]))


good = {"stopped": False, "last_tick": now_iso(-3)}
# under a Claude Code session the hook finds its claude.exe and would trim it; from a plain terminal it finds none
run("tick-just-written", good, ("WOULD TRIM claude pid", "no claude.exe ancestor found"))
run("human-turn-old-tick", {"stopped": False, "last_tick": now_iso(-2400)}, "outside the 120 s window")
run("absent-state-file", None, "state absent or unreadable")
run("stopped", {"stopped": True, "last_tick": now_iso(-3)}, "stopped is true")
run("last-tick-null", {"stopped": False, "last_tick": None}, "last_tick null")
run("govern-disabled", good, "enabled not true", gov=gov_dir("disabled", enabled=False))
run("govern-stop-present", good, "govern.stop present", gov=gov_dir("stop", stop=True))
run("already-trimmed", good, "already trimmed for this tick",
    gov=gov_dir("trimmed", trimmed={"testcase-already-trimmed": good["last_tick"]}))
probe = os.path.join(tmp, "probe.txt")
run("real-detached-spawn", dict(good, last_tick=now_iso(-2)), "SPAWNED", gov=gov_dir("spawn"),
    extra=["--spawn-probe", probe], wait_file=probe)

shutil.rmtree(tmp, ignore_errors=True)
print("govern_posttick_test: " + ("ALL PASSED" if fails == 0 else "%d FAILED" % fails))
sys.exit(0 if fails == 0 else 1)
