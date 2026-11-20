#!/usr/bin/env python3
"""migrate_config: move a person's own choices out of an OLD skill folder's chime.json and into their chime home.

Older versions of chime kept the person's sound choices, account names and paths in chime.json inside the skill folder,
which an update replaces. This script reads that OLD chime.json and the new generic chime.json, keeps only what differs
(plus anything named with --extra), and writes it as <chime home>/config.json. The skill's own sound files named by the
old file are copied to <chime home>/sounds, and their paths are rewritten to "user:<file>".

  python migrate_config.py OLD_CHIME_JSON --chime-home DIR [--generic PATH] [--extra FILE ...] [--old-sounds DIR]
                           [--apply] [--force]

  OLD_CHIME_JSON   the old file, for example <old skill folder>/chime.json
  --chime-home     the person's chime home (the folder CHIME_HOME names, normally ~/.threadops/chime)
  --generic        the new generic chime.json (default: the one beside this script's folder)
  --extra FILE     a JSON file of further person settings to merge on top (a private skill ships one); repeatable
  --old-sounds     where the old skill's sound files are (default: a "sounds" folder beside the old chime.json)
  --apply          really write. WITHOUT it nothing is written: a dry run prints what would happen.
  --force          allow overwriting an existing config.json (after a backup, config.json.bak-<time>) or a different
                   sound file of the same name (after a backup of that file). Without it, either is refused.

Exit 0 when done (or the dry run is clean), 2 when something is refused or wrong. The old files are never changed.
The script reads local files only: no network, no credentials, no settings of any program.
"""
import argparse
import hashlib
import io
import json
import os
import shutil
import sys
import time

EVENTS = ("urgent", "important", "boing", "default", "tick", "tick_ready", "tick_high", "tick_low", "peer", "compact",
          "relay", "tick_compaction", "ack", "done", "questions", "low_health", "brakes", "red_alert", "escalate",
          "abandon", "ignored")
DEEP = ("names", "labels", "account_names", "words", "spoken_names", "texts")
AUDIO = (".mp3", ".wav")


class Refused(Exception):
    pass


def load(path, what):
    try:
        with io.open(path, encoding="utf-8-sig") as fh:
            d = json.load(fh)
    except Exception as e:
        raise Refused("cannot read %s %s (%s)" % (what, path, e.__class__.__name__))
    if not isinstance(d, dict):
        raise Refused("%s %s is not a JSON object" % (what, path))
    return d


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def difference(old, generic):
    """The keys of old that differ from generic (deep keys entry by entry), in old's order."""
    out = {}
    for k, v in old.items():
        g = generic.get(k)
        if k in DEEP and isinstance(v, dict):
            d = {a: b for a, b in v.items() if not (isinstance(g, dict) and a in g and g[a] == b)}
            if d:
                out[k] = d
        elif k not in generic or g != v:
            out[k] = v
    return out


def merge_over(base, extra):
    out = dict(base)
    for k, v in extra.items():
        if k in DEEP and isinstance(v, dict) and isinstance(out.get(k), dict):
            m = dict(out[k])
            m.update(v)
            out[k] = m
        else:
            out[k] = v
    return out


def plan(old_path, generic_path, extras, old_sounds):
    """(config dict, [(source file, destination name)], notes). Raises Refused on a missing sound file."""
    old, generic = load(old_path, "old chime.json"), load(generic_path, "generic chime.json")
    cfg = difference(old, generic)
    for e in extras:
        cfg = merge_over(cfg, load(e, "extra file"))
    copies, notes, missing = [], [], []
    for ev in EVENTS:
        v = cfg.get(ev)
        if not isinstance(v, str) or not v or v.startswith(("user:", "gen:")) or os.path.isabs(v):
            continue
        rel = v.replace("\\", "/")
        name = os.path.basename(rel)
        if os.path.splitext(name)[1].lower() not in AUDIO:
            notes.append("%s: %s is not an mp3 or wav file; left as written" % (ev, v))
            continue
        src = os.path.join(old_sounds, name)
        if not os.path.isfile(src):
            missing.append("%s: %s" % (ev, src))
            continue
        cfg[ev] = "user:" + name
        if (src, name) not in copies:
            copies.append((src, name))
    if missing:
        raise Refused("sound files named by the old chime.json are missing, nothing to do until they are found "
                      "(or point --old-sounds at them):\n  " + "\n  ".join(missing))
    return cfg, copies, notes


def stamp():
    return time.strftime("%Y%m%d-%H%M%S")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("old")
    ap.add_argument("--chime-home", required=True)
    ap.add_argument("--generic", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "chime.json"))
    ap.add_argument("--extra", action="append", default=[])
    ap.add_argument("--old-sounds")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    home = os.path.abspath(os.path.expanduser(a.chime_home))
    old_sounds = a.old_sounds or os.path.join(os.path.dirname(os.path.abspath(a.old)), "sounds")
    try:
        cfg, copies, notes = plan(a.old, a.generic, a.extra, old_sounds)
        target = os.path.join(home, "config.json")
        sdir = os.path.join(home, "sounds")
        problems = []
        if os.path.exists(target) and not a.force:
            problems.append("%s already exists: nothing is overwritten without --force (it would be backed up first)" % target)
        clash = []
        for src, name in copies:
            dest = os.path.join(sdir, name)
            if os.path.exists(dest) and sha(dest) != sha(src):
                clash.append(dest)
        if clash and not a.force:
            problems.append("a different file of the same name already exists (use --force to replace it after a backup): "
                            + ", ".join(clash))
        print("%s: %d keys in config.json, %d sound files to copy" % ("APPLY" if a.apply else "DRY RUN", len(cfg), len(copies)))
        for k, v in cfg.items():
            shown = json.dumps(v, ensure_ascii=False)
            print("  %s = %s" % (k, shown if len(shown) < 110 else shown[:107] + "..."))
        for src, name in copies:
            print("  copy %s -> %s" % (src, os.path.join(sdir, name)))
        for n in notes:
            print("  note: " + n)
        if problems:
            raise Refused("\n".join(problems))
        if not a.apply:
            print("nothing was written. Run again with --apply to write.")
            return 0
        os.makedirs(sdir, exist_ok=True)
        if os.path.exists(target):
            bak = "%s.bak-%s" % (target, stamp())
            shutil.copyfile(target, bak)
            print("backup %s" % bak)
        for src, name in copies:
            dest = os.path.join(sdir, name)
            if os.path.exists(dest):
                if sha(dest) == sha(src):
                    continue
                bak = "%s.bak-%s" % (dest, stamp())
                shutil.copyfile(dest, bak)
                print("backup %s" % bak)
            tmp = "%s.%d.tmp" % (dest, os.getpid())
            shutil.copyfile(src, tmp)
            os.replace(tmp, dest)
        tmp = "%s.%d.tmp" % (target, os.getpid())
        with io.open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(cfg, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, target)
        try:
            with io.open(os.path.join(home, "config_log.txt"), "a", encoding="utf-8") as fh:
                fh.write("%s | migrate_config | wrote config.json (%d keys), copied %d sound files\n"
                         % (time.strftime("%Y-%m-%d %H:%M:%S"), len(cfg), len(copies)))
        except OSError:
            pass
        print("wrote %s and %d sound files in %s" % (target, len(copies), sdir))
        return 0
    except Refused as e:
        print("REFUSED: %s" % e)
        return 2


if __name__ == "__main__":
    sys.exit(main())
