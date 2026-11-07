#!/usr/bin/env python3
r"""parley_compile.py: build a parley page from its owner's fragment and, for a manager session, its
direct reports' fragments.

Every session keeps its parley data on disk as <SEAT>_PARLEY.json (the page's DATA object as JSON). A
manager session (one that answers for others) compiles its page from its own fragment plus each
report's fragment, so the crew's questions land on one page.

  python parley_compile.py --own <MANAGER>_PARLEY.json --out <MANAGER>_PARLEY.html \
      [--report <SEAT>_PARLEY.json ...] [--template <path>] [--refresh] [--warn-links-elsewhere]

--out is created from the template (assets/parley-template.html beside this script) if it does not
exist, otherwise only its DATA object is replaced, so a page's own experiments survive. A lock file
(<out>.lock) stops two sessions compiling the same page at once; a lock older than 10 minutes is stale.
Prints what it compiled, including any card ID that appears in more than one fragment, so a shared
ask can be asked once. Then publish --out with the Artifact tool as usual.

--refresh rebuilds --out from the template even when it exists (keeping only the DATA), which is how a
page picks up a new template version. Without it a page keeps its own markup.

Environment: PARLEY_DELEGATED_FILE turns on the optional delegation registry and names the JSON file it is written
to (for example ~/.parley/delegated.json). Unset, no registry is written and the compile says nothing about it.
Nothing reads the file unless you wire up a companion that does.

Checks printed on every compile:
  UNCHECKED  a card with no "checked" note. Before a card surfaces, look in the system of record and the
             other sessions' records for whether it is already done, then say what you looked at in "checked".
  LIST MISSING  a card that asks about many items but carries no "items" table.
  CARD ID  an id with spaces, commas or brackets; the page saves its status under the cleaned id it prints. Put an
           "also" list in the title, not the id.
  QUESTION LATE  an ask that runs past two sentences with no "context"; lead with the question, move the rest to "context".
  STEPS MISSING  an open card with no "steps" and no numbered steps in its ask; say what the reviewer should do, one step per line.
  ORIGIN MISSING  an open card with no "origin"; name the project or lane, the thread or finding, and an https link if there is one.
  ASK EQUALS TITLE  a card whose question is its title word for word; the page shows it once, so make the title a short name.
  ITEMS      an "items" table whose rows are not lists, or whose row ids repeat.
  CONTEXT LONG  an open card whose context runs past 600 characters; keep the current state in three sentences.
  HISTORY ON CARD  an open card whose context reads like a progress log (done, in progress, pending, PROGRESS);
             history goes to the activity log.
  PASTE STALE  a paste box on a card opened more than a day ago; remove it once it has been pasted or its task is done.
  UPDATES MISSING / UPDATES ORDER / UPDATE UNDATED / UPDATE EMPTY  the "updates" list is absent on a long card, not newest
             first, missing its stamp, or empty.
  CODENAME MISSING  an open card with no codename and an id that is not of the form PROJECT_Topic.
  PASTE SHARED  one paste on two cards.

Checks that refuse (nothing is written):
  OPENED MISSING  a card, open or closed, with no parsable "opened" (YYYY-MM-DD HH:MM, the time the author session added
             the card, never its latest edit). A card with "when" but no "opened" takes "when"; a placeholder minute (09:4x)
             reads as 09:40. Exit code 3.
  LINK       a file path (drive letter or UNC) or a word ending in .md, .doc, .docx, .xls, .xlsx, .pdf or .txt anywhere on
             the page: open cards, closed cards, activity, work, decisions and changes. Put the content on the card as
             "explain" blocks instead. Exit code 4. --warn-links-elsewhere downgrades the closed-card, activity, work,
             decisions and changes hits to one warning.
"""
import argparse
import io
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "..", "assets", "parley-template.html")
START, END_TAG = "const DATA = ", "</script>"


DELEGATED_FILE = os.path.expanduser(os.environ.get("PARLEY_DELEGATED_FILE") or "")   # opt-in: unset means no registry


def register_delegations(frags):
    """Record which sessions' parleys are delegated to a manager, so an optional companion (an alerting tool, say) can keep
    a delegated session quiet. A fragment with delegated.to is listed; one without it is removed. Opt-in: does nothing
    unless PARLEY_DELEGATED_FILE is set."""
    if not DELEGATED_FILE:
        return
    try:
        try:
            with io.open(DELEGATED_FILE, encoding="utf-8") as fh:
                reg = json.load(fh)
        except Exception:
            reg = {}
        before = json.dumps(reg, sort_keys=True)
        for f in frags:
            seat, dl = f.get("seat"), f.get("delegated") or {}
            if not seat:
                continue
            mb = f.get("mothball") or {}
            if dl.get("to"):
                reg[seat] = {"to": dl.get("to"), "at": dl.get("at"), "url": dl.get("url")}
                if mb.get("relaunch"):
                    reg[seat]["mothballed"] = mb.get("at") or True
            elif mb.get("relaunch"):                 # sleeping with no manager: still listed
                reg[seat] = {"to": "(mothballed)", "at": mb.get("at"), "mothballed": mb.get("at") or True}
            else:
                reg.pop(seat, None)
        if json.dumps(reg, sort_keys=True) != before:
            os.makedirs(os.path.dirname(DELEGATED_FILE) or ".", exist_ok=True)
            tmp = DELEGATED_FILE + ".tmp"
            with io.open(tmp, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(reg, fh, indent=1, sort_keys=True)
            os.replace(tmp, DELEGATED_FILE)
            print("DELEGATIONS %s" % (", ".join("%s -> %s" % (k, v.get("to")) for k, v in sorted(reg.items())) or "none"))
    except Exception as e:
        print("DELEGATIONS not recorded: %r" % (e,))


def load(p):
    with io.open(p, encoding="utf-8") as fh:
        return json.load(fh)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--own", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--report", action="append", default=[])
    ap.add_argument("--template", default=TEMPLATE)
    ap.add_argument("--refresh", action="store_true", help="rebuild --out from the template, keeping only DATA")
    ap.add_argument("--warn-links-elsewhere", action="store_true", help="only warn (do not refuse) on paths or document names outside open cards")
    a = ap.parse_args()
    lock = a.out + ".lock"
    if os.path.exists(lock) and time.time() - os.path.getmtime(lock) < 600:
        print("LOCKED: %s is held (another session is compiling); try again shortly" % lock)
        return 2
    io.open(lock, "w").write(str(os.getpid()))
    try:
        data = load(a.own)
        reports = []
        frags = [data]
        for rp in a.report:
            r = load(rp)
            frags.append(r)
            reports.append({k: r.get(k) for k in ("seat", "version", "phase", "updated", "loop", "capacity", "remote_control", "account",
                                                   "questions", "activity", "work", "mothball")})
        data["reports"] = reports
        register_delegations(frags)
        # Every card shows when the author session added it. Refuse, do not warn.
        stamp = re.compile(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}")
        # A placeholder minute ("09:4x") reads as its ten (09:40).
        tens = re.compile(r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d)[xX]")
        missing = []
        for f in [data] + reports:
            for q in f.get("questions") or []:
                for k in ("opened", "when"):
                    if isinstance(q.get(k), str):
                        q[k] = tens.sub(r"\g<1>0", q[k], count=1)
                if not stamp.match(str(q.get("opened") or "")) and stamp.match(str(q.get("when") or "")):
                    q["opened"] = q["when"]
                if not stamp.match(str(q.get("opened") or "")):
                    missing.append("%s:%s" % (f.get("seat"), q.get("id")))
        if missing:
            for tag in missing:
                print("OPENED MISSING %s: set 'opened' to the YYYY-MM-DD HH:MM the author session added the card (never its latest edit)" % tag)
            print("NOT COMPILED: %d card(s) without an opened time; nothing was written" % len(missing))
            return 3
        # work.columns must be strings, and a paste belongs to one card.
        for f in [data] + reports:
            w = f.get("work") or {}
            if any(not isinstance(c, str) for c in w.get("columns") or []):
                w["columns"] = [c if isinstance(c, str) else str(c.get("name") or c.get("label") or c) if isinstance(c, dict) else str(c)
                                for c in w["columns"]]
                print("WORK COLUMNS of %s coerced to strings" % f.get("seat"))
        pastes = {}
        for f in [data] + reports:
            for q in f.get("questions") or []:
                if q.get("paste"):
                    pastes.setdefault(q["paste"].strip(), []).append("%s:%s" % (f.get("seat"), q.get("id")))
        for ids in pastes.values():
            if len(ids) > 1:
                print("PASTE SHARED by %s: a paste belongs to one card; fix the fragments" % ", ".join(ids))
        # Check before surfacing; a ruling on many items puts the list on the card.
        many = re.compile(r"\b\d{2,}\s+(?:\w+\s+){0,2}(?:merges?|items?|rows?|records?|bills?|vendors?|contacts?|journals?|entries|lines?|invoices?|accounts?|files?|names?)\b", re.I)
        for f in [data] + reports:
            for q in f.get("questions") or []:
                tag = "%s:%s" % (f.get("seat"), q.get("id"))
                if str(q.get("status") or q.get("stage") or "open").lower() in ("done", "completed", "superseded", "deferred"):
                    continue
                # Ids that break the status control, and questions buried in context.
                qid = str(q.get("id") or "")
                key = re.sub(r"^-+|-+$", "", re.sub(r"[^A-Za-z0-9_.-]+", "-", qid)) or "card"
                if key != qid:
                    print("CARD ID %s: not a clean document id; its status is saved as status/%s. Put an 'also' list in the title" % (tag, key))
                ask = str(q.get("question") or q.get("ask") or "")
                if not q.get("question") and not q.get("context") and not re.match(r"\s*QUESTION FOR YOU:", ask, re.I) and (
                        len(re.findall(r"[.?!](?:\s|$)", ask)) > 2 or len(ask) > 280):
                    print("QUESTION LATE %s: lead with the one-sentence question in 'ask'; move the rest to 'context'" % tag)
                # A card names the actions to take and where it comes from.
                if not q.get("steps") and not re.search(r"(?:^|\s)1[.)]\s.*(?:^|\s)2[.)]\s", str(q.get("ask") or ""), re.S):
                    print("STEPS MISSING %s: give the actions the reviewer should take as 'steps', one per line" % tag)
                norm = lambda x: re.sub(r"[^a-z0-9]+", "", str(x or "").lower())
                if q.get("title") and norm(q.get("title")) == norm(ask):
                    print("ASK EQUALS TITLE %s: the page shows it once, as the question; make the title a short name for the card" % tag)
                if not q.get("origin"):
                    print("ORIGIN MISSING %s: add 'origin' {project, thread, link (https only)} so the reviewer can rebuild the context" % tag)
                # A card carries the open ask and the current state only.
                ctx = str(q.get("context") or "")
                # Long cards become timestamped updates, newest first, as lists; a card is named by a thread codename, not a serial.
                ups = q.get("updates")
                if isinstance(ups, list) and ups:
                    stamps = [str(u.get("when") or "") for u in ups if isinstance(u, dict)]
                    if any(not re.match(r"\d{4}-\d{2}-\d{2}", w) for w in stamps):
                        print("UPDATE UNDATED %s: every entry in 'updates' starts with its YYYY-MM-DD HH:MM stamp in 'when'" % tag)
                    if stamps != sorted(stamps, reverse=True):
                        print("UPDATES ORDER %s: 'updates' must run newest first" % tag)
                    if any(isinstance(u, dict) and not u.get("points") and not u.get("text") for u in ups):
                        print("UPDATE EMPTY %s: each update carries 'points' (a list) or 'text'" % tag)
                elif len(ctx) > 600:
                    print("UPDATES MISSING %s: %d characters of context and no 'updates'; split it into timestamped blocks, newest first, with lists" % (tag, len(ctx)))
                if not q.get("codename") and not re.match(r"^[A-Za-z]+_[A-Za-z0-9]+$", qid):
                    print("CODENAME MISSING %s: name the card by its thread codename ('codename': '#PROJECT_TopicCamelCase'); a bare serial like Y56 means nothing to the reader" % tag)
                if len(ctx) > 600 and not (isinstance(ups, list) and ups):
                    print("CONTEXT LONG %s: %d characters; keep the current state in three sentences, history goes to the activity log" % (tag, len(ctx)))
                if re.search(r"\bPROGRESS\b", ctx) or len(re.findall(r"\b(?:done|in progress|pending|completed)\b", ctx, re.I)) >= 3:
                    print("HISTORY ON CARD %s: the context reads like a progress log; keep the current state, move the history to the activity log" % tag)
                opened = re.match(r"(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})", str(q.get("opened") or ""))
                if q.get("paste") and opened and time.time() - time.mktime(time.strptime(" ".join(opened.groups()), "%Y-%m-%d %H:%M")) > 86400:
                    print("PASTE STALE %s: the paste box is over a day old; remove it once it has been pasted or its task is done" % tag)
                if not q.get("checked"):
                    print("UNCHECKED %s: confirm in the system of record and the other seats' records that it is not already done; say what you checked in 'checked'" % tag)
                it = q.get("items")
                if it:
                    rows = it.get("rows") or []
                    if any(not isinstance(r, list) for r in rows):
                        print("ITEMS %s: every row must be a list of cells" % tag)
                    else:
                        k = int(it.get("key") or 0)
                        keys = [str(r[k]) if len(r) > k else "" for r in rows]
                        dup = sorted(set(x for x in keys if keys.count(x) > 1))
                        if dup:
                            print("ITEMS %s: row ids repeat (%s); give each row a unique id in column %d" % (tag, ", ".join(dup[:5]), k))
                    if any(not isinstance(c, str) for c in it.get("columns") or []):
                        it["columns"] = [str(c) for c in it["columns"]]
                elif many.search("%s %s" % (q.get("ask") or "", q.get("title") or "")):
                    print("LIST MISSING %s: it asks about many items; put them on the card as 'items' (columns, rows), approve or strike per row" % tag)
        # No file path or document name anywhere on a page: the card carries what the reader needs, in 'explain' blocks.
        path_rx = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]|\\\\[A-Za-z0-9_.$-]+\\|(?<![\w/])[\w.-]+\.(?:md|docx?|xlsx?|pdf|txt)\b", re.I)

        def walk(x, where):
            if isinstance(x, dict):
                for k, v in x.items():
                    if k == "paste":                              # a command or baton to paste is not a document link
                        continue
                    yield from walk(v, where + "." + str(k))
            elif isinstance(x, list):
                for i, v in enumerate(x):
                    yield from walk(v, where + "[%d]" % i)
            elif isinstance(x, str):
                m = path_rx.search(x)
                if m:
                    yield where, x[max(0, m.start() - 20):m.end() + 30].replace("\n", " ")
        hard, soft = [], []
        for f in [data] + reports:
            seat = f.get("seat")
            for q in f.get("questions") or []:
                closed = str(q.get("status") or q.get("stage") or "open").lower() in ("done", "completed", "superseded", "deferred")
                for where, snip in walk(q, "%s:%s" % (seat, q.get("id"))):
                    (soft if closed else hard).append((where, snip))
            for sec in ("activity", "work", "decisions", "changes"):
                for where, snip in walk(f.get(sec), "%s:%s" % (seat, sec)):
                    soft.append((where, snip))
        for where, snip in hard:
            print("LINK %s: %s" % (where, snip))
        if soft:
            print("LINKS ELSEWHERE %d: paths or document names in closed cards, activity, work, decisions or changes; reword them%s"
                  % (len(soft), "" if not a.warn_links_elsewhere else " (warning only: --warn-links-elsewhere)"))
            if not a.warn_links_elsewhere:
                for where, snip in soft[:20]:
                    print("LINK %s: %s" % (where, snip))
                hard = hard or soft
        if hard:
            print("LINKS %d: no document links or file paths on a parley; put the content on the card as 'explain' blocks" % len(hard))
            raise SystemExit(4)
        seen = {}
        for owner, qs in [(data.get("seat"), data.get("questions"))] + [(r["seat"], r["questions"]) for r in reports]:
            for q in qs or []:
                seen.setdefault(q.get("id"), []).append(owner)
        src = a.out if os.path.exists(a.out) and not a.refresh else a.template
        page = io.open(src, encoding="utf-8").read()
        i = page.index(START)
        j = page.index(END_TAG, i)       # the DATA script holds nothing else, so replace up to its close
        out = page[:i] + START + json.dumps(data, indent=2, ensure_ascii=False) + ";\n" + page[j:]
        if src == a.template:
            out = out.replace("<title>Parley: SEAT-ID</title>", "<title>Parley: %s</title>" % data.get("seat", "SEAT-ID"), 1)
        tmp = a.out + ".tmp"
        io.open(tmp, "w", encoding="utf-8", newline="\n").write(out)
        os.replace(tmp, a.out)
        print("COMPILED %s: own %d cards, %d report tab(s): %s" % (
            a.out, len(data.get("questions") or []), len(reports),
            ", ".join("%s (%d cards)" % (r["seat"], len(r["questions"] or [])) for r in reports) or "none"))
        for qid, owners in seen.items():
            if len(owners) > 1:
                print("SHARED card id %s appears in %s: ask it once on the manager's Parley tab" % (qid, ", ".join(owners)))
        return 0
    finally:
        try:
            os.remove(lock)
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
