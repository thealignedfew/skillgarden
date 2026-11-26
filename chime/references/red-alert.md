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
- From version 22 the card is part of the firing: `fire` writes it (or prints it and says why not), and a pending alert with no card is reported on the firing seat's ticks and on the compile of its page (section "The card is part of the firing").

## The commands

Each prints one line per fact and exits 0, except `fire` (3 when it refuses), 2 for a bad argument, 1 for a missing id or a busy log. None of them can fail a hook.

```
chime.py redalert check --kind usage-limit-burn --words "weekly usage near the line"
chime.py redalert fire --seat <SEAT> --kind <slug> --title "..." --why "..." --evidence "..." [--card <id>] [--parley <url>] [--session <uuid>] [--worse "..."] [--fragment <path>] [--codename "..."]
chime.py redalert card --id RA-20260101-120000-abcd --card <card id> [--parley <url>] [--fragment <path>] [--where "..."]
chime.py redalert card --id RA-20260101-120000-abcd --write [--card <card id>] [--fragment <path>] [--codename "..."]
chime.py redalert uncarded [--seat <SEAT>] [--crew <S1,S2>] [--min-age <minutes>] [--updated "SEAT=ISO;SEAT=ISO"]
chime.py redalert verdict --id RA-20260101-120000-abcd --merited|--not-merited --by "<name>" --note "<their words>"
chime.py redalert list [--pending] [--seat <SEAT>]
chime.py redalert example --kind <slug> --title "..." --why "..." --verdict merited|not_merited [--by "<name>"] [--when <ISO>]
```

- `check` prints the past alerts whose kind equals the slug or shares a word with it or with `--words` (newest first, at most 8, each with its verdict and title), then one line: `ADVICE fire`, `ADVICE do not fire: ...`, `ADVICE mixed: read the lines above` or `ADVICE no precedent`. A pending alert is listed but is no precedent. Run it before every fire.
- `fire` appends one line to the log, sounds `red_alert` unless muted (then the log's `played` holds the reason), shows the toast, and prints `FIRED <id>` and a `SOUND` line. It refuses (exit 3), naming the earlier id, while the same seat and kind has a pending or merited alert under 6 hours old, unless `--worse` is given.
- `verdict` sets the verdict; a second verdict on the same id replaces the first and keeps the old one in `verdict_history`. It is the only command that rewrites the log (atomically, under a lock).
- `example` adds a precedent with `source: example` and no sound: a case the person gave as an example, not an alert that fired.
- `card` records a card on the alert's log line (`--card`, with `--parley` or `--fragment` or `--where` for where it is), or with `--write` writes the card into the seat's page source and records it. It changes that one line and no other.
- `uncarded` prints one line per pending alert that has no card, `ALERT CARD MISSING <alert id> <seat> <hours>`, and nothing when there is none or when there is no log. `--seat` and `--crew` choose the seats (both together are their union), `--min-age` is the minutes an alert may go without a card before it is reported (30). With `--updated` (the parley compile passes each fragment's `updated` stamp) it also prints `FRAGMENT STALE <seat> updated <time>, older than alert <id> fired <time>` for a seat whose page source is a minute or more older than its newest pending alert.

## The log, and how it learns

`<chime home>/red_alerts.jsonl`, one JSON object per line, one file for every account on the machine. Fields: `id` (RA-YYYYMMDD-HHMMSS-xxxx), `when`, `seat`, `session`, `home` (account name), `kind` (a short lower-case slug the session chooses), `title`, `why`, `evidence`, `card`, `parley`, `played` (true, or the reason nothing sounded), `verdict` (`pending`, `merited`, `not_merited`), `verdict_at`, `verdict_by`, `verdict_note`, `source` (`fired` or `example`), and `worse`, `worse_than` and `verdict_history` when used. From version 22 a line also carries `card_where` (where the card was written or said to be) and `card_at` when a card was recorded, and `card_history` when a later record replaced a card the line already named. A line counts as carded when `card` or `parley` is not empty. A corrupt line is skipped, never fatal. The hook and the read commands read only the last 400 KB.

Every firing and every verdict is a line in that one log. A session runs `check` before it fires. The per-turn hook text carries a short paragraph (under 1,200 characters): what a red alert is, how to fire, and the kinds the person ruled merited and not merited (up to 6 each, newest per kind first). Merited tells the next session such a finding should fire; not merited tells it a comparable finding should not.

## The page for a verdict

Firing is not complete until the person can rule on it. With the parley skill, the seat puts a card on its page with the alert's id, kind, why and evidence and the question "Did this merit a red alert?"; the person's click is read on the next tick and passed to `redalert verdict`. Without a parley page, a seat records the alert wherever the person will see it and asks for the verdict in its next report.

## The card is part of the firing (version 22)

The person's standard is that every firing gets a card on a page they read, in the same turn. A seat whose parley is delegated to a manager has no page of its own: its card goes into its fragment (its page source, `<SEAT>_PARLEY.json`), which the manager compiles and publishes. Two alerts of such a seat once sat with no card on any page, one for 15 hours and one for 34 minutes, because nothing wrote the card, nothing said the seat had to, and nothing noticed it was missing.

- **`fire` ends with the card.** After the log line it finds the seat's page source (`--fragment PATH`, else the record the parley compile keeps in `~/.threadops/parley/fragments.json`, seat to path) and writes the card there when that is safe: the file reads as JSON, a backup is made beside it (`<file>.pre-redalert-<alert id>.bak`), the card is added to its questions (or, with `--card <id>` naming a card that is already there and carries no alert, the alert block goes on that card), the `updated` stamp is set, the file's own line endings, indent and byte order mark are kept, what is written is read back and must equal the original plus the card, and the file is replaced in one step. The same alert id never gets a second card. It then records the card on the log line.
- **Where it cannot write**, it says why in one line (no page source recorded, the file is not valid JSON, the card id is taken, the file changed while it was being read), prints the card as JSON (`CARD BLOCK`, or `ALERT BLOCK` when `--card` named an existing card) and the way to record it once the seat has added it by hand: `chime.py redalert card --id <alert id> --card <card id>`. Nothing is written in that case.
- **Then it says what is next.** A delegated seat tells its manager in the same turn that the card is in its page source, so the manager compiles and publishes it; a failed send does not end that duty. A seat with its own page compiles and publishes it.
- **Seeing a missing card.** `redalert uncarded` is the detector. The seat's own ticks (reprompt 19.3) and the compile of a page (parley 2.27) run it and print `ALERT CARD MISSING` lines while an alert has no card. Both are silent and fast when there is no log, and a failure of the check never stops a tick or a compile.
- The card the tool writes has the id of the alert unless `--card` names another, the title `RED ALERT: <title>`, `important` true, the question "Did this merit a red alert?", one step, the alert block, and `checked` saying it was written when the alert fired; the seat adds what it checked in the system of record and its own thread. It compiles without a warning about the alert.
