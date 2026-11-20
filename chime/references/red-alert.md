# RED ALERT

## What a red alert is

A session fires a red alert when it has itself found a material risk or deficiency: something that will cost money, data, access or working time if nobody acts soon, or a control or a piece of equipment that is not doing what it is there to do. It is about the finding. It is not about the session being stuck (that is MAJOR PROBLEM FOUND) and not about a decision waiting (the DECISION phrases).

## When it sounds

- A reply whose first non-empty line opens `RED ALERT` plays `red_alert` at the end of the turn. Leading markdown is ignored; `RED ALERT:` and `RED ALERT -` count; `RED ALERTS` as a plain heading does not, and neither does a mention on a later line. The phrase must be in capitals: a sentence starting "Red alert is being built" is prose.
- It plays alone and first: no `done`, no tick or peer sound. A baton to relay still adds `relay` after it. The toast reads "RED ALERT: <seat>" plus the first line's words after the phrase (140 characters at most), and the seat's name is spoken.
- Mid-turn, so the person hears it at once: `chime.py redalert fire ...` sounds it and logs it, or `chime.py play redalert "<SEAT>" "<what>"` sounds it without a log line. After either, the same turn's Stop hook plays nothing more for the phrase (a marker, 15 minutes).
- Nothing is replayed. One firing per issue: the same seat and kind does not sound again within 6 hours unless it got materially worse (`--worse`). A first-line `RED ALERT` from a seat that sounded one in the last 6 hours is treated as an ordinary turn.
- A muted moment plays nothing, but the firing is still logged and the toast still shows. A muted turn does not use the seat's one sound up. A sound the person silenced (by the name or `red_alert`) does not play. While the person dictates, the sound waits like every other sound.
- Any seat may fire, including one whose parley is delegated to a manager.

## The commands

Each prints one line per fact and exits 0, except `fire` (3 when it refuses), 2 for a bad argument, 1 for a missing id or a busy log. None of them can fail a hook.

```
chime.py redalert check --kind usage-limit-burn --words "weekly usage near the line"
chime.py redalert fire --seat <SEAT> --kind <slug> --title "..." --why "..." --evidence "..." [--card <id>] [--parley <url>] [--session <uuid>] [--worse "..."]
chime.py redalert verdict --id RA-20260101-120000-abcd --merited|--not-merited --by "<name>" --note "<their words>"
chime.py redalert list [--pending] [--seat <SEAT>]
chime.py redalert example --kind <slug> --title "..." --why "..." --verdict merited|not_merited [--by "<name>"] [--when <ISO>]
```

- `check` prints the past alerts whose kind equals the slug or shares a word with it or with `--words` (newest first, at most 8, each with its verdict and title), then one line: `ADVICE fire`, `ADVICE do not fire: ...`, `ADVICE mixed: read the lines above` or `ADVICE no precedent`. A pending alert is listed but is no precedent. Run it before every fire.
- `fire` appends one line to the log, sounds `red_alert` unless muted (then the log's `played` holds the reason), shows the toast, and prints `FIRED <id>` and a `SOUND` line. It refuses (exit 3), naming the earlier id, while the same seat and kind has a pending or merited alert under 6 hours old, unless `--worse` is given.
- `verdict` sets the verdict; a second verdict on the same id replaces the first and keeps the old one in `verdict_history`. It is the only command that rewrites the log (atomically, under a lock).
- `example` adds a precedent with `source: example` and no sound: a case the person gave as an example, not an alert that fired.

## The log, and how it learns

`<chime home>/red_alerts.jsonl`, one JSON object per line, one file for every account on the machine. Fields: `id` (RA-YYYYMMDD-HHMMSS-xxxx), `when`, `seat`, `session`, `home` (account name), `kind` (a short lower-case slug the session chooses), `title`, `why`, `evidence`, `card`, `parley`, `played` (true, or the reason nothing sounded), `verdict` (`pending`, `merited`, `not_merited`), `verdict_at`, `verdict_by`, `verdict_note`, `source` (`fired` or `example`), and `worse`, `worse_than` and `verdict_history` when used. A corrupt line is skipped, never fatal. The hook and the read commands read only the last 400 KB.

Every firing and every verdict is a line in that one log. A session runs `check` before it fires. The per-turn hook text carries a short paragraph (under 1,200 characters): what a red alert is, how to fire, and the kinds the person ruled merited and not merited (up to 6 each, newest per kind first). Merited tells the next session such a finding should fire; not merited tells it a comparable finding should not.

## The page for a verdict

Firing is not complete until the person can rule on it. With the parley skill, the seat puts a card on its page with the alert's id, kind, why and evidence and the question "Did this merit a red alert?"; the person's click is read on the next tick and passed to `redalert verdict`. Without a parley page, a seat records the alert wherever the person will see it and asks for the verdict in its next report.
