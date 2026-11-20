#!/usr/bin/env python3
r"""soundboard_sync: the bridge between the Soundboard page and this machine's chime.

The page is a published artifact and cannot touch the PC. A person presses a button there, the page writes a request
row to its database, and the session that owns the page (at its next check, or at once when the person pushes with a
comment) reads the rows, runs this script, and writes the results and a fresh roster back.

  python soundboard_sync.py roster --out roster.json [--clips DIR]
      Sounds (key, name, file, silenced, and a label where the config has one), sessions (tab title, account name, last
      active, voice, spoken words), Windows virtual desktops (number and name), the person's clock and the questions
      cooldown, as one JSON object. --clips copies each voiced seat's spoken-name clip into DIR (rendering any missing
      one with edge-tts) and names it in the row's "clip", so the page can play the current voice; publish DIR as voices/.
      Account names come from the config key account_names; the transcripts that give each session's tab title come from
      the config key transcripts_glob (default ~/.claude/projects/*/*.jsonl).
  python soundboard_sync.py apply requests.json --out results.json [--dry-run]
      requests.json is a list of {"id", "kind", "target", "note"}; results.json is a list of
      {"id", "status": "done"|"manual"|"failed", "result"}. Kinds:
        silence / unsilence     target = a sound name or event
        clock                   target = "out" | "in", note = optional reason
        voice_new               target = a tab title: a new random voice, preferring one no other seat holds
        name_reset              target = a tab title: drop its spoken-name override, so the title is read fresh
        name_set                target = a tab title, note = the words to say
        questions_cooldown      target = minutes between questions-sound plays
        desktop_rename          target = desktop number, note = new name: recorded as a manual step (Task View)
        roster                  nothing to apply; the roster is rebuilt after every apply anyway
State lives in <chime home>/silence.json and ~/.threadops/presence.json, one per machine, read by every account's chime.py.

The page's four newer request kinds carry "type", not "kind", and they are not applied by `apply`. This script cannot
read or write the page database; the owner session does that with its tools. The script plans:

  python soundboard_sync.py state --out-dir DIR [--chime PATH]
      Writes DIR/usage.json and DIR/sounds.json from `chime.py usage status --json`, `sounds list --json` and
      `sounds styles --json` (usage.json plus synced_at; sounds.json plus styles and synced_at; `accepts` is part of
      what `sounds list --json` prints). The session writes them to the page's state/usage and state/sounds documents
      after the check, after it has run the commands below, so the page shows the result. A command that failed leaves
      its file unwritten.
  python soundboard_sync.py requests requests.json [--assets-dir DIR] [--out plan.json] [--seat SEAT] [--chime PATH]
      requests.json is the list of pending request documents (each with its "id"). Only the types usage_mute,
      sound_replace, sound_generate and sound_reset are looked at; the rest are left to `apply`. The plan is a list of
        {"id", "type", "status": "ready", "command": [argv], "command_line": "..."}   run the command, then mark the request
            done with the command's one line as "result" (or failed with its message when it exits non-zero)
        {"id", "type", "status": "failed", "result": "why"}   not run: unknown account, unknown event or style, a bad
            file name or type; mark the request failed with that result
        {"id", "type", "status": "blocked", "result": "why", "save_asset": {...}}   not run yet: the uploaded file is not
            in --assets-dir. Save the asset there (Artifact read with the asset id as path and out_dir DIR), then run this
            again. The page uploads audio wrapped in a small JSON envelope (the platform has no audio type): the script
            unwraps it into DIR/<asset id>-<file name> and hands that local path to `sounds set`.
      Nothing is run by this script; the session runs each "command_line" itself.
"""
import glob
import importlib.util
import io
import json
import os
import random
import re
import sys
import time

import base64
import datetime
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
CHIME_PATH = os.environ.get("SOUNDBOARD_CHIME") or os.path.join(HERE, "chime.py")


class _Lazy(object):
    """chime.py is loaded the first time roster or apply needs it, so `state` and `requests` (which only run chime.py
    as a command) work with nothing but the file."""
    _mod = None

    def _load(self):
        if _Lazy._mod is None:
            spec = importlib.util.spec_from_file_location("chime", CHIME_PATH)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _Lazy._mod = mod
        return _Lazy._mod

    def __getattr__(self, name):
        return getattr(self._load(), name)


chime = _Lazy()
NEW_TYPES = ("usage_mute", "sound_replace", "sound_generate", "sound_reset")



def homes():
    """Account folder name -> the name shown for it, from the config key account_names."""
    try:
        h = chime._C.get("account_names")
        return dict(h) if isinstance(h, dict) else {}
    except Exception:
        return {}


def transcripts_glob():
    """Where session transcripts live: the config key transcripts_glob, else Claude Code's own default."""
    try:
        g = chime._C.get("transcripts_glob")
    except Exception:
        g = None
    return g if isinstance(g, str) and g.strip() else os.path.join(os.path.expanduser("~"), ".claude", "projects", "*", "*.jsonl")


def account_of(path, pattern, names):
    """The account name for a transcript path: the path segment where the pattern's first wildcard sits, when the
    segment after it is a literal "home" (one folder per account); otherwise no account is known and this is ''."""
    try:
        pat = re.split(r"[\\/]+", pattern)
        got = re.split(r"[\\/]+", path)
        for i, seg in enumerate(pat):
            if "*" in seg:
                if i + 1 < len(pat) and pat[i + 1].lower() == "home" and i < len(got):
                    return names.get(got[i], got[i])
                return ""
    except Exception:
        pass
    return ""


ACTIVE_DAYS = 7
NOW = lambda: time.strftime("%Y-%m-%d %H:%M")


def jload(path, default):
    try:
        with io.open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def jsave(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=1, sort_keys=True, ensure_ascii=False)
    os.replace(tmp, path)


def desktops():
    try:
        import uuid
        import winreg
        base = r"Software\Microsoft\Windows\CurrentVersion\Explorer\VirtualDesktops"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, base) as k:
            ids = winreg.QueryValueEx(k, "VirtualDesktopIDs")[0]
        out = []
        for i in range(len(ids) // 16):
            g = "{%s}" % uuid.UUID(bytes_le=bytes(ids[i * 16:i * 16 + 16]))
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, base + "\\Desktops\\" + g.upper()) as d:
                    name = winreg.QueryValueEx(d, "Name")[0]
            except OSError:
                name = ""
            out.append({"n": i + 1, "name": name or "Desktop %d" % (i + 1)})
        return out
    except Exception as e:
        return [{"n": 0, "name": "unavailable: %s" % e.__class__.__name__}]


def sessions():
    voices = jload(chime.VOICES_FILE, {})
    seen = {}
    cutoff = time.time() - ACTIVE_DAYS * 86400
    pattern, names = transcripts_glob(), homes()
    for tp in glob.glob(pattern):
        try:
            mt = os.path.getmtime(tp)
        except OSError:
            continue
        if mt < cutoff:
            continue
        title = chime.tab_title(tp)
        if not title:
            continue
        home = account_of(tp, pattern, names)
        row = seen.get(title)
        if row and row["_mt"] >= mt:
            continue
        seen[title] = {"_mt": mt, "title": title, "home": home, "session": os.path.basename(tp)[:8],
                       "last": time.strftime("%Y-%m-%d %H:%M", time.localtime(mt))}
    for title in voices:
        seen.setdefault(title, {"_mt": 0, "title": title, "home": "", "session": "", "last": ""})
    rows = []
    for title, r in seen.items():
        r.pop("_mt", None)
        r["voice"] = voices.get(title, "")
        r["words"] = chime.spoken(title)
        own = os.path.join(chime.VOICE_DIR, "spoken", re.sub(r"[^A-Za-z0-9_.-]+", "-", title) + ".txt")
        r["own_words"] = os.path.exists(own)
        rows.append(r)
    rows.sort(key=lambda r: r["last"], reverse=True)
    return rows


def clips(rows, clip_dir):
    """Each voiced seat's real clip (its voice saying its spoken words), rendered by chime if missing and copied to
    clip_dir for the page to play."""
    import shutil
    os.makedirs(clip_dir, exist_ok=True)
    for r in rows:
        if not r.get("voice") or not r.get("words"):
            continue
        try:
            c = chime.voice_clip(r["words"], r["voice"])
        except Exception:
            c = None
        if c and os.path.exists(c):
            dst = os.path.join(clip_dir, os.path.basename(c))
            if not os.path.exists(dst):
                shutil.copyfile(c, dst)
            r["clip"] = os.path.basename(c)


def roster(clip_dir=None):
    sil = jload(chime.SILENCE_FILE, {})
    names = chime.SOUND_NAMES
    sounds = []
    labels = chime._C.get("labels") or {}           # an optional plain-words label per sound key (config "labels")
    for key in sorted(set(list(chime.SOUNDS) + list(names))):
        name = names.get(key) or key
        f = chime.SOUNDS.get(key, "")
        row = {"key": key, "name": name, "file": os.path.basename(f) if f else "",
               "silenced": name in (sil.get("sounds") or {})}
        if labels.get(key):
            row["label"] = labels[key]
        sounds.append(row)
    rows = sessions()
    if clip_dir:
        clips(rows, clip_dir)
    return {"updated": NOW(), "sounds": sounds, "silenced": sil.get("sounds") or {},
            "questions_cooldown_min": int(chime.questions_cooldown() // 60),
            "presence": chime.presence(), "desktops": desktops(), "sessions": rows,
            "voice_pool": len(chime.VOICE_POOL)}


def apply(reqs, dry):
    sil = jload(chime.SILENCE_FILE, {})
    sil.setdefault("sounds", {})
    names = set(v for v in chime.SOUND_NAMES.values()) | set(chime.SOUNDS)
    voices = jload(chime.VOICES_FILE, {})
    out, sil_changed, voice_changed, pres = [], False, False, None
    for r in reqs:
        if r.get("type") in NEW_TYPES and not r.get("kind"):
            continue                                  # the newer kinds are planned by `requests`, not applied here
        kind, target, note = r.get("kind"), (r.get("target") or "").strip(), (r.get("note") or "").strip()
        res = {"id": r.get("id"), "status": "done", "result": ""}
        if kind in ("silence", "unsilence"):
            if target not in names:
                res.update(status="failed", result="no sound named %s" % target)
            elif kind == "silence":
                sil["sounds"][target] = {"since": NOW(), "note": note}
                sil_changed = True
                res["result"] = "%s silenced" % target
            else:
                sil["sounds"].pop(target, None)
                sil_changed = True
                res["result"] = "%s plays again" % target
        elif kind == "clock":
            if target not in ("out", "in"):
                res.update(status="failed", result="clock target must be out or in")
            else:
                pres = {"state": target, "since": NOW(), "note": note}
                res["result"] = "clocked %s at %s" % (target, pres["since"])
        elif kind == "voice_new":
            if not target:
                res.update(status="failed", result="no session named")
            else:
                old = voices.get(target, "")
                free = [v for v in chime.VOICE_POOL if v not in voices.values() and v != old] or \
                       [v for v in chime.VOICE_POOL if v != old]
                voices[target] = random.choice(free)
                voice_changed = True
                res["result"] = "%s: %s -> %s" % (target, old or "none", voices[target])
        elif kind in ("name_reset", "name_set"):
            own = os.path.join(chime.VOICE_DIR, "spoken", re.sub(r"[^A-Za-z0-9_.-]+", "-", target) + ".txt")
            if not target:
                res.update(status="failed", result="no session named")
            elif kind == "name_reset":
                if os.path.exists(own) and not dry:
                    os.remove(own)
                res["result"] = "%s is read as: %s" % (target, chime.spoken(target) if not dry else "(dry run)")
            elif not note:
                res.update(status="failed", result="name_set needs the words in the note")
            else:
                if not dry:
                    os.makedirs(os.path.dirname(own), exist_ok=True)
                    with io.open(own, "w", encoding="utf-8") as fh:
                        fh.write(note[:80])
                res["result"] = "%s is read as: %s" % (target, note[:80])
        elif kind == "questions_cooldown":
            try:
                m = max(0, min(24 * 60, int(float(target))))
                sil["questions_cooldown_min"] = m
                sil_changed = True
                res["result"] = "i-have-several-questions at most once every %d minutes" % m
            except ValueError:
                res.update(status="failed", result="cooldown must be a number of minutes")
        elif kind == "desktop_rename":
            res.update(status="manual", result="Rename desktop %s to %s in Task View (Win+Tab, click its name); "
                       "the next roster reads it back." % (target, note or "?"))
        elif kind == "roster":
            res["result"] = "roster rebuilt"
        else:
            res.update(status="failed", result="unknown request kind %s" % kind)
        out.append(res)
    if not dry:
        if sil_changed:
            jsave(chime.SILENCE_FILE, sil)
        if voice_changed:
            jsave(chime.VOICES_FILE, voices)
        if pres:
            jsave(chime.PRESENCE_FILE, pres)
    return out



# ---- state documents and the plan for the page's newer requests ----------------------------------------------------

DEFAULT_ACCEPTS = (".mp3", ".wav")                 # used only when chime.py does not say (`sounds list` prints accepts)
MAX_SOUND_BYTES = 5 * 1024 * 1024
ASSET_RX = re.compile(r"^[0-9a-f]{32}$")
SEAT_RX = re.compile(r"^[A-Za-z0-9_.-]{1,60}$")
QUIET = re.compile(r"^[A-Za-z0-9_./:\\-]+$")


class ChimeError(Exception):
    pass


def now_iso():
    return datetime.datetime.now().astimezone().replace(microsecond=0).isoformat()


def chime_cmd(chime_path, args):
    return [sys.executable, "-X", "utf8", chime_path] + list(args)


def run_json(chime_path, args):
    """Run one chime.py command that prints a JSON object and return it. Raises ChimeError with the command's own words."""
    cmd = chime_cmd(chime_path, list(args) + ["--json"])
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=90)
    except Exception as e:
        raise ChimeError("%s could not be run: %s" % (" ".join(args), e.__class__.__name__))
    out = r.stdout.decode("utf-8", "replace").strip()
    if r.returncode != 0:
        raise ChimeError("chime.py %s exited %d: %s" % (" ".join(args), r.returncode, (out or r.stderr.decode("utf-8", "replace")).strip()[:300]))
    try:
        obj = json.loads(out)
    except ValueError:
        raise ChimeError("chime.py %s did not print JSON: %s" % (" ".join(args), out[:200]))
    if not isinstance(obj, dict):
        raise ChimeError("chime.py %s printed JSON that is not an object" % " ".join(args))
    return obj


def state_docs(chime_path, out_dir):
    """Write usage.json and sounds.json. Returns (written files, problems)."""
    done, problems = [], []
    os.makedirs(out_dir, exist_ok=True)
    stamp = now_iso()
    try:
        u = run_json(chime_path, ["usage", "status"])
        u["synced_at"] = stamp
        jwrite_plain(os.path.join(out_dir, "usage.json"), u)
        done.append("usage.json")
    except ChimeError as e:
        problems.append("usage.json not written: %s" % e)
    try:
        s = run_json(chime_path, ["sounds", "list"])
        styles = run_json(chime_path, ["sounds", "styles"])
        s["styles"] = styles
        s["synced_at"] = stamp
        jwrite_plain(os.path.join(out_dir, "sounds.json"), s)
        done.append("sounds.json")
    except ChimeError as e:
        problems.append("sounds.json not written: %s" % e)
    return done, problems


def jwrite_plain(path, data):
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def quote(a):
    return a if QUIET.match(a) else '"%s"' % a.replace('"', '\\"')


def safe_name(name):
    base = re.split(r"[\\/]", str(name or ""))[-1]
    return re.sub(r"[^A-Za-z0-9._-]+", "-", base).strip("-.")[:80]


def style_ids(styles_obj):
    raw = styles_obj
    if isinstance(raw, dict) and isinstance(raw.get("styles"), (dict, list)):
        raw = raw["styles"]
    if isinstance(raw, dict):
        return list(raw)
    if isinstance(raw, list):
        return [x.get("style") or x.get("name") or x.get("id") for x in raw if isinstance(x, dict)]
    return []


def sniff_ok(head):
    return (head[:3] == b"ID3" or (len(head) > 1 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0)
            or (head[:4] == b"RIFF" and head[8:12] == b"WAVE") or head[:4] == b"OggS" or head[4:8] == b"ftyp")


def find_asset(assets_dir, asset_id):
    if not assets_dir or not os.path.isdir(assets_dir):
        return None
    hits = sorted(p for p in glob.glob(os.path.join(glob.escape(assets_dir), asset_id + "*")) if os.path.isfile(p))
    return hits[0] if hits else None


def asset_to_audio(src, asset_id, filename, assets_dir, accepts, dry):
    """(local audio path, None) or (None, why). Unwraps the page's JSON envelope; checks size, name, type and header."""
    want = safe_name(filename)
    ext = os.path.splitext(want)[1].lower()
    if ext not in accepts:
        return None, "file name %s is not one of %s" % (filename, ", ".join(accepts))
    with open(src, "rb") as fh:
        data = fh.read(MAX_SOUND_BYTES * 2 + 4096)
    if data[:1] in (b"{", b"\xef"):
        try:
            env = json.loads(data.decode("utf-8-sig"))
            raw = base64.b64decode(env["data_base64"], validate=True)
        except Exception:
            return None, "asset %s is not a Soundboard audio envelope or an audio file" % asset_id
        if env.get("format") != "soundboard-audio-1":
            return None, "asset %s has an unknown envelope format" % asset_id
    else:
        raw = data
    if not raw:
        return None, "asset %s is empty" % asset_id
    if len(raw) > MAX_SOUND_BYTES:
        return None, "asset %s is %.1f MB; the limit is 5 MB" % (asset_id, len(raw) / 1048576.0)
    if not sniff_ok(raw[:16]):
        return None, "asset %s does not look like an audio file" % asset_id
    dst = os.path.join(assets_dir, "%s-%s" % (asset_id, want))
    if not dry and not (os.path.isfile(dst) and os.path.getsize(dst) == len(raw)):
        with open(dst, "wb") as fh:
            fh.write(raw)
    return dst, None


def plan_requests(reqs, chime_path, assets_dir, seat, dry=False):
    usage = run_json(chime_path, ["usage", "status"])
    sounds = run_json(chime_path, ["sounds", "list"])
    styles = style_ids(run_json(chime_path, ["sounds", "styles"]))
    accounts = {}
    for a in usage.get("accounts") or []:
        for key in (a.get("account"), a.get("home")):
            if key:
                accounts[str(key).lower()] = a.get("account")
    events = [e.get("event") for e in sounds.get("events") or []]
    accepts = [x.lower() for x in (sounds.get("accepts") or DEFAULT_ACCEPTS)]
    out = []
    for r in reqs:
        t = r.get("type")
        if t not in NEW_TYPES or r.get("kind"):
            continue
        item = {"id": r.get("id"), "type": t, "status": "ready"}

        def fail(why):
            item.update(status="failed", result=why)
            return item

        if t == "usage_mute":
            acct = str(r.get("account") or "").strip()
            canon = "this" if acct.lower() == "this" else accounts.get(acct.lower())
            if not canon:
                out.append(fail("unknown account %r (accounts: %s)" % (acct, ", ".join(sorted(set(accounts.values()))) or "none")))
                continue
            if not isinstance(r.get("on"), bool):
                out.append(fail("usage_mute needs on: true or false"))
                continue
            args = (["usage", "mute", canon, "--cycle", "--by", seat, "--why", "from the Soundboard"] if r["on"]
                    else ["usage", "unmute", canon, "--by", seat])
        else:
            ev = str(r.get("event") or "").strip()
            if ev not in events:
                out.append(fail("unknown event %r (events: %s)" % (ev, ", ".join(events) or "none")))
                continue
            if t == "sound_reset":
                args = ["sounds", "reset", ev, "--by", seat]
            elif t == "sound_generate":
                st = str(r.get("style") or "").strip().lower()
                if st and st not in styles:
                    out.append(fail("unknown style %r (styles: %s)" % (st, ", ".join(styles) or "none")))
                    continue
                args = ["sounds", "generate", ev] + (["--style", st] if st else []) + ["--by", seat]
            else:
                aid = str(r.get("asset_id") or "")
                fn = str(r.get("filename") or "")
                if not ASSET_RX.match(aid):
                    out.append(fail("asset_id %r is not a 32-character id" % aid[:40]))
                    continue
                if not safe_name(fn) or os.path.splitext(safe_name(fn))[1].lower() not in accepts:
                    out.append(fail("file name %r is not one of %s" % (fn[:60], ", ".join(accepts))))
                    continue
                item["save_asset"] = {"asset_id": aid, "dir": assets_dir, "how": "Artifact read with path=%s and out_dir=<dir>; the saved file starts with the asset id" % aid}
                src = find_asset(assets_dir, aid)
                if not src:
                    item.update(status="blocked", result="asset %s is not in %s yet: save it there, then run requests again" % (aid, assets_dir or "(no --assets-dir given)"))
                    out.append(item)
                    continue
                local, why = asset_to_audio(src, aid, fn, assets_dir, accepts, dry)
                if why:
                    out.append(fail(why))
                    continue
                item["local_path"] = local
                args = ["sounds", "set", ev, local, "--by", seat]
        cmd = chime_cmd(chime_path, args)
        item["command"] = cmd
        item["command_line"] = " ".join(quote(a) for a in cmd)
        out.append(item)
    return out


def opt(args, name, default=None):
    return args[args.index(name) + 1] if name in args and args.index(name) + 1 < len(args) else default


def main():
    args = sys.argv[1:]
    outp = args[args.index("--out") + 1] if "--out" in args else None
    chime_path = opt(args, "--chime", CHIME_PATH)
    if args[:1] == ["roster"]:
        data = roster(args[args.index("--clips") + 1] if "--clips" in args else None)
    elif args[:1] == ["apply"] and len(args) > 1:
        data = apply(jload(args[1], []), "--dry-run" in args)
    elif args[:1] == ["state"] and opt(args, "--out-dir"):
        done, problems = state_docs(chime_path, opt(args, "--out-dir"))
        print("wrote %s" % ", ".join(os.path.join(opt(args, "--out-dir"), d) for d in done) if done else "wrote nothing")
        for pr in problems:
            print("PROBLEM " + pr)
        return 1 if problems else 0
    elif args[:1] == ["requests"] and len(args) > 1:
        seat = opt(args, "--seat", os.environ.get("SOUNDBOARD_SEAT") or "Soundboard")
        if not SEAT_RX.match(seat):
            print("--seat must be letters, digits, _ . - only")
            return 2
        try:
            data = plan_requests(jload(args[1], []), chime_path, opt(args, "--assets-dir"), seat, "--dry-run" in args)
        except ChimeError as e:
            print("PROBLEM %s" % e)
            return 1
    else:
        print(__doc__)
        return 2
    text = json.dumps(data, indent=1, ensure_ascii=False)
    if outp:
        with io.open(outp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        print("wrote %s" % outp)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
