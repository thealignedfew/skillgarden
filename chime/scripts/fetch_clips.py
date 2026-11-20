#!/usr/bin/env python3
"""Optional: fetch third-party sound clips for chime, for your own local use.

chime works without any of this: every event already has a tone the skill generates itself. This script exists for
people who would rather hear recognisable sound effects. It ships no audio. Nothing runs it automatically: it runs only
when you run it, and it only downloads files, it never runs anything it downloads.

The clips are third-party sounds. They are owned by others. You download them for your own local use and you are
responsible for that download. Nothing here grants a licence.

Usage:
  fetch_clips.py             download the clips that are missing, into <chime home>/sounds
  fetch_clips.py --list      print the manifest as a table
  fetch_clips.py --check     report which clips are present or missing (no download)
  fetch_clips.py --only NAME [NAME ...]   fetch just these
  fetch_clips.py --chime-home DIR         use another chime home (default: CHIME_HOME, else ~/.threadops/chime)

The manifest is clips.json beside the skill: a list of {"name", "file", "source_url"}. A person's own list goes in
<chime home>/clips.json in the same shape; an entry there with the same name replaces the skill's entry. An entry with no
source_url cannot be fetched and is reported as such. A source_url is an https address of an mp3 file, or of a page that
links one at /media/sounds/<file>.mp3 (the page is read as text only). The file must start like an mp3 and be at most
5 MB, or it is refused and nothing is written.

After fetching, give a clip to an event with: chime.py sounds set <event> <chime home>/sounds/<file>
"""
import argparse
import io
import json
import os
import re
import sys
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "clips.json")
MAX_BYTES = 5 * 1024 * 1024
NOTE = ("These clips are owned by others. You download them for your own local use "
        "and you are responsible for that download. Nothing here grants a licence.")


def chime_home(override=None):
    if override:
        return os.path.abspath(os.path.expanduser(override))
    if os.environ.get("CHIME_HOME"):
        return os.path.normpath(os.environ["CHIME_HOME"])
    return os.path.join(os.path.expanduser("~"), ".threadops", "chime")


def read_list(path):
    try:
        with io.open(path, encoding="utf-8-sig") as fh:
            d = json.load(fh)
        return [e for e in d if isinstance(e, dict) and e.get("name")] if isinstance(d, list) else []
    except Exception:
        return []


def load(home):
    """The skill's manifest, with the person's own <chime home>/clips.json laid over it by name."""
    by = {}
    order = []
    for e in read_list(MANIFEST) + read_list(os.path.join(home, "clips.json")):
        if e["name"] not in by:
            order.append(e["name"])
        by[e["name"]] = e
    return [by[n] for n in order]


def file_of(e):
    name = os.path.basename(str(e.get("file") or e["name"] + ".mp3").replace("\\", "/"))
    return name if os.path.splitext(name)[1].lower() in (".mp3", ".wav") else name + ".mp3"


def dest_of(home, e):
    return os.path.join(home, "sounds", file_of(e))


def looks_like_mp3(data):
    return data[:3] == b"ID3" or (len(data) > 1 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0)


def fetch(url):
    """(bytes, content type) of one https address. The only network call in this script; tests replace it."""
    req = urllib.request.Request(url, headers={"User-Agent": "chime-fetch-clips"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read(MAX_BYTES + 1), r.headers.get("Content-Type", "")


def get_audio(url):
    """The audio bytes for a source address: the file itself, or the mp3 a page links. Raises ValueError when refused."""
    if not url.lower().startswith("https://"):
        raise ValueError("only https addresses are fetched")
    data, ctype = fetch(url)
    if data[:1] == b"<" or "html" in (ctype or "").lower():
        m = re.search(r"""["'(](/media/sounds/[^"')\s<>]+?\.mp3)""", data.decode("utf-8", "replace"))
        if not m:
            raise ValueError("the page links no /media/sounds/<file>.mp3")
        link = urllib.parse.urljoin(url, m.group(1))
        if urllib.parse.urlparse(link).netloc != urllib.parse.urlparse(url).netloc:
            raise ValueError("the page's mp3 is on another host")
        data, ctype = fetch(link)
    if len(data) > MAX_BYTES:
        raise ValueError("larger than 5 MB")
    if not data or not looks_like_mp3(data):
        raise ValueError("does not look like an mp3 file")
    return data


def cmd_list(entries):
    rows = [("name", "file", "source_url")]
    for e in entries:
        rows.append((e["name"], file_of(e), e.get("source_url") or "(none)"))
    w = [max(len(r[i]) for r in rows) for i in range(3)]
    for i, r in enumerate(rows):
        print("  ".join(c.ljust(w[j]) for j, c in enumerate(r)).rstrip())
        if i == 0:
            print("  ".join("-" * x for x in w))
    print("%d entries, %d with a source_url" % (len(entries), sum(1 for e in entries if e.get("source_url"))))


def cmd_check(entries, home):
    missing = 0
    for e in entries:
        ok = os.path.isfile(dest_of(home, e))
        missing += 0 if ok else 1
        print("%-8s %s" % ("present" if ok else "missing", e["name"]))
    print("%d present, %d missing (folder %s)" % (len(entries) - missing, missing, os.path.join(home, "sounds")))


def cmd_fetch(entries, home):
    print(NOTE)
    got = skipped = failed = nosrc = 0
    for e in entries:
        dest = dest_of(home, e)
        if os.path.isfile(dest):
            skipped += 1
            continue
        url = e.get("source_url")
        if not url:
            print("%s: no source recorded" % e["name"])
            nosrc += 1
            continue
        try:
            data = get_audio(url)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            tmp = "%s.%d.tmp" % (dest, os.getpid())
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, dest)
            print("%s: downloaded (%d bytes) to %s" % (e["name"], len(data), dest))
            got += 1
        except Exception as ex:
            print("%s: FAILED (%s)" % (e["name"], ex))
            failed += 1
    print("summary: %d downloaded, %d already present, %d no source recorded, %d failed"
          % (got, skipped, nosrc, failed))
    return 1 if failed else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--list", action="store_true", help="print the manifest as a table")
    g.add_argument("--check", action="store_true", help="report present or missing, no download")
    ap.add_argument("--only", nargs="+", metavar="NAME", help="only these clips")
    ap.add_argument("--chime-home", help="the chime home (default CHIME_HOME, else ~/.threadops/chime)")
    a = ap.parse_args(argv)
    home = chime_home(a.chime_home)
    entries = load(home)
    if a.only:
        want = set(a.only)
        unknown = want - set(e["name"] for e in entries)
        if unknown:
            print("not in the manifest: " + ", ".join(sorted(unknown)))
            return 2
        entries = [e for e in entries if e["name"] in want]
    if a.list:
        cmd_list(entries)
    elif a.check:
        cmd_check(entries, home)
    else:
        return cmd_fetch(entries, home)
    return 0


if __name__ == "__main__":
    sys.exit(main())
