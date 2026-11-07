#!/usr/bin/env python
# govern_posttick.py  ramgovern, the post-tick trim: an optional Claude Code Stop hook.
#
# For sessions that run unattended on a timer (a scheduler re-prompts them every N minutes), the best moment to page a session
# out is right after its own scheduled turn ends: it will sit idle until the next one. The scheduled task alone catches it
# only on its own cadence; this hook catches it at once.
#
# Contract with your scheduler: after each scheduled turn starts, it writes
#     <posttick_state_dir>/<session_id>.json   containing   {"last_tick": "<local ISO time>", "stopped": false}
# (session_id is the Claude Code session id the Stop hook receives). Without such files the hook does nothing.
#
# On every Stop event the hook reads the hook's stdin JSON (session_id, transcript_path) and, only when that session's
# last_tick is within posttick_window_seconds (govern.json, default 120), spawns the engine DETACHED:
#     govern.ps1 -Mode self -TargetPid <this hook's own claude.exe ancestor> -Apply
# and exits. It never trims inline and never prints anything (a Stop hook's output can reach the model).
#
# Guarantees:
#   1  returns within 200 ms on every path; a trim spawns detached and the hook exits; stdout and stderr stay empty.
#   2  exit 0 and do nothing when: the state file is absent or unreadable, last_tick is null or older than the window,
#      "stopped" is true, govern.json is unreadable or has enabled false, or govern.stop exists. Python -I, stdlib only.
#   3  one trim per tick: posttick.state.json remembers the last_tick value it already trimmed for, so a human turn inside the
#      window after a tick cannot trim a second time.
#
# Test flags (never used by the registered hook):
#   --dry              decide, log what it WOULD do, spawn nothing
#   --log-all          write one govern.log line for every outcome, not only for a spawn
#   --state-dir DIR    tick state directory (default: posttick_state_dir in govern.json, else a 'ticks' folder beside it)
#   --govern-dir DIR   directory holding govern.json, govern.stop, posttick.state.json (default: this script's folder)
#   --spawn-probe FILE spawn a harmless PowerShell that writes FILE, with the SAME creation flags as the real trim, to
#                      prove the child outlives the hook (used instead of trimming a session during the test)
import sys
import os
import json
import time
import datetime
import subprocess

T0 = time.perf_counter()
GOV_DEFAULT = os.path.dirname(os.path.abspath(__file__))
POWERSHELL = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0",
                          "powershell.exe")


def arg(name, default=None):
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


DRY = "--dry" in sys.argv
LOG_ALL = "--log-all" in sys.argv
GOV = arg("--govern-dir", GOV_DEFAULT)
PROBE = arg("--spawn-probe")


def stamp():
    # local time with the UTC offset, the same shape as the engine's lines: 2026-01-15 09:30:00 +01:00
    now = datetime.datetime.now().astimezone()
    off = now.strftime("%z")
    return now.strftime("%Y-%m-%d %H:%M:%S") + " " + off[:3] + ":" + off[3:]


def read_json(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return None


def log(line):
    try:
        cfg = read_json(os.path.join(GOV, "govern.json")) or {}
        path = cfg.get("log_path") or os.path.join(GOV, "govern.log")
        ms = (time.perf_counter() - T0) * 1000.0
        with open(path, "a", encoding="ascii", errors="replace") as f:
            f.write("%s stage1 posttick %s; %d ms\n" % (stamp(), line, round(ms)))
    except Exception:
        pass


def claude_ancestor():
    # walk up from this process to the first claude.exe (the session this hook belongs to); stdlib ctypes only
    import ctypes
    from ctypes import wintypes

    class PE(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_void_p), ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", ctypes.c_wchar * 260)]

    k32 = ctypes.windll.kernel32
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    k32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PE)]
    k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PE)]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    snap = k32.CreateToolhelp32Snapshot(2, 0)
    if snap in (None, -1, 0xFFFFFFFF, ctypes.c_void_p(-1).value):
        return 0
    table = {}
    try:
        pe = PE()
        pe.dwSize = ctypes.sizeof(PE)
        ok = k32.Process32FirstW(snap, ctypes.byref(pe))
        while ok:
            table[pe.th32ProcessID] = (pe.th32ParentProcessID, pe.szExeFile.lower())
            ok = k32.Process32NextW(snap, ctypes.byref(pe))
    finally:
        k32.CloseHandle(snap)
    pid = os.getpid()
    for _ in range(10):
        ent = table.get(pid)
        if not ent:
            return 0
        if ent[1] == "claude.exe":
            return pid
        pid = ent[0]
    return 0


def spawn(cmd):
    # detached: the hook exits at once and the child carries on; no window, own process group
    flags = 0x08000000 | 0x00000200   # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(cmd, creationflags=flags, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, close_fds=True)


def main():
    raw = ""
    try:
        raw = sys.stdin.read()
    except Exception:
        pass
    ev = {}
    try:
        ev = json.loads(raw) if raw.strip() else {}
    except Exception:
        ev = {}
    sid = ev.get("session_id") or ""
    if not sid and ev.get("transcript_path"):
        sid = os.path.splitext(os.path.basename(str(ev["transcript_path"])))[0]
    short = sid[:24] if sid else "none"

    def done(outcome, detail=""):
        if LOG_ALL or outcome.startswith("WOULD") or outcome == "SPAWNED":
            log("%s session %s: %s%s" % ("DRY" if DRY else "RUN", short, outcome, (" (" + detail + ")") if detail else ""))
        return 0

    # settings first (cheapest), then the stop flag, then the session state
    cfg = read_json(os.path.join(GOV, "govern.json"))
    if not isinstance(cfg, dict) or cfg.get("enabled") is not True:
        return done("NOOP govern.json unreadable or enabled not true")
    if os.path.exists(os.path.join(GOV, "govern.stop")):
        return done("NOOP govern.stop present (storm halt)")
    if not sid:
        return done("NOOP no session_id in the hook input")
    state_dir = arg("--state-dir") or cfg.get("posttick_state_dir") or os.path.join(GOV, "ticks")
    st = read_json(os.path.join(state_dir, sid + ".json"))
    if st is None:
        return done("NOOP tick state absent or unreadable")
    if not isinstance(st, dict):
        return done("NOOP tick state not an object")
    if st.get("stopped") is True:
        return done("NOOP stopped is true")
    lt = st.get("last_tick")
    if not lt:
        return done("NOOP last_tick null")
    try:
        window = float(cfg.get("posttick_window_seconds", 120))
        age = (datetime.datetime.now() - datetime.datetime.fromisoformat(str(lt))).total_seconds()
    except Exception:
        return done("NOOP last_tick unparseable")
    if age < -5 or age > window:
        return done("NOOP last_tick %.0f s old, outside the %.0f s window" % (age, window))
    # one trim per tick
    pt_path = os.path.join(GOV, "posttick.state.json")
    pt = read_json(pt_path)
    if not isinstance(pt, dict):
        pt = {}
    if pt.get(sid) == lt:
        return done("NOOP already trimmed for this tick")
    pid = claude_ancestor()
    if not pid and not PROBE:
        return done("NOOP no claude.exe ancestor found")

    engine = os.path.join(GOV, "govern.ps1")
    if PROBE:
        cmd = [POWERSHELL, "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command",
               "Start-Sleep -Milliseconds 800; Set-Content -Path '%s' -Value 'child outlived the hook'" % PROBE]
    else:
        cmd = [POWERSHELL, "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", engine,
               "-Mode", "self", "-TargetPid", str(pid), "-Apply"]
    if DRY:
        return done("WOULD TRIM claude pid %s" % pid, "last_tick %.0f s old, window %.0f s" % (age, window))
    try:
        spawn(cmd)
        pt[sid] = lt
        if len(pt) > 60:
            for k in list(pt)[:-60]:
                pt.pop(k, None)
        try:
            with open(pt_path, "w", encoding="ascii") as f:
                json.dump(pt, f)
        except Exception:
            pass
    except Exception as e:
        return done("NOOP spawn failed %s" % type(e).__name__)
    return done("SPAWNED", "pid %s, last_tick %.0f s old" % (pid, age))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
