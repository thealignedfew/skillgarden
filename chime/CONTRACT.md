# chime: the contract between chime.py, the Soundboard page and other pages

This file pins what `scripts/chime.py` prints, what a page may ask for, and what travels between them. A page, a sync script or a test can rely on exactly this. If the contract is wrong or cannot be met, say so; do not quietly change it.

## 1. Where a person's own choices live

Nothing a person chooses is stored inside the skill folder, because an update replaces that folder whole.

- Skill defaults: `<skill>/chime.json`. Every default sound is a generated tone written `gen:<style>`.
- The person's overrides: `<chime home>/config.json`, the same keys as `chime.json`, merged over it key by key (`names`, `labels`, `account_names`, `words`, `spoken_names` and `texts` one level deep). `<chime home>` is `~/.threadops/chime`, or the folder named by the environment variable `CHIME_HOME`.
- The person's sound files, and the tones chime generates: `<chime home>/sounds/`. A path in config that starts with `user:` (for example `user:my-ding.mp3`) is resolved there. A path that starts with `sounds/` means the skill's own folder (the skill ships none). A path that starts with `gen:` is a generated tone, made into `<chime home>/sounds/gen-<event>-<style>.wav` the first time it is needed.
- Usage mutes: `<chime home>/usage_mute.json`.
- A missing or unreadable override file means defaults; it never stops a sound.

## 2. Command line

All print one line of plain text; `--json` prints one JSON object. Exit 0 done, 2 bad input (the message starts `ERROR`, or `{"ok": false, "error": ...}` with `--json`), 1 a file could not be written.

```
chime.py usage status [--json]
chime.py usage mute <ACCOUNT> [--cycle | --until "YYYY-MM-DD HH:MM"] [--by SEAT] [--why "text"]
chime.py usage unmute <ACCOUNT> [--by SEAT]

chime.py sounds list [--json]
chime.py sounds set <event> <path to an mp3 or wav file> [--by SEAT]
chime.py sounds generate <event> [--style STYLE] [--by SEAT]
chime.py sounds generate --all-missing [--style STYLE]
chime.py sounds reset <event> [--by SEAT]
chime.py sounds styles [--json]
```

- `<ACCOUNT>` is a name from `account_names`, an account home folder name (case-insensitive), or `this`. With no `account_names` configured, `this` and the current account's folder name work.
- `usage mute --cycle` (the default when neither flag is given) mutes until the reset of the cycle that is over the alert line, from the reset times the usage reading keeps in its cache (`resets_at` of the five-hour and weekly limits). When no reset time is known it mutes for 24 hours and says so (`until_source: "fallback_24h"`). A mute is for one account's low-usage alarm only and ends by itself at `until`.
- `usage status --json`:

```json
{"alert_pct": 90, "accounts": [
  {"account": "WORK", "home": "work", "muted": true, "until": "2026-11-21T23:30:00", "until_source": "cycle|given|fallback_24h",
   "by": "SEAT", "why": "...", "set_at": "2026-11-19T18:01:00",
   "last_reading": {"at": "2026-11-19T17:54:28", "values": [{"limit": "weekly", "pct": 100, "resets_at": "2026-11-21T09:00:00"}]},
   "marker_quiet_until": "2026-11-19T18:30:00"}]}
```

`last_reading` comes from the usage cache when present, else from the last line for that account in the usage log (then without `resets_at`); `null` when neither exists. Every account in `account_names` is listed (just the current one when none are configured). `marker_quiet_until` appears only when a played marker is dated in the future.

- `sounds list --json`:

```json
{"events": [{"event": "urgent", "label": "urgent", "file": "gen:double", "source": "default|user|generated", "exists": true, "name": "urgent", "style": "double"}],
 "user_dir": "<chime home>/sounds",
 "accepts": [".mp3", ".wav"]}
```

  `file` is `gen:<style>`, `user:<file>` or a path. `source` is `default` while the skill's default plays, `user` for a person's own file, `generated` for a tone the person generated with `sounds generate`. `exists` is true for a `gen:` tone (made on first use). `style` is present when the sound is a generated tone. `mapped_missing` is present when a `user:` file has gone missing and the default plays. `accepts` is the list of file types the player plays; a page and a sync script take their list of allowed uploads from it.
- `sounds set`: copies the file into `<chime home>/sounds/` (keeps the extension; mp3 or wav only, 5 MB cap inclusive, the content must look like that format; never overwrites a different file of the same name, a suffix is added), then writes `"<event>": "user:<name>"` into `<chime home>/config.json`. It refuses to run when `config.json` exists but is unreadable. `--json`: `{"ok": true, "event", "file": "user:<name>", "path", "bytes"}`.
- `sounds generate`: writes a short tone, standard library only, no downloads, to `<chime home>/sounds/gen-<event>-<style>.wav` (16-bit mono 44.1 kHz) and maps the event to it. Styles, each under 1.5 seconds: `beep`, `double`, `rise`, `fall`, `chord`, `alarm`, `tick`, `soft`. With no `--style` a table in the code picks one per event (`default_style` in `styles`). `--all-missing` makes a tone for every event whose chosen file does not exist. `--json`: `{"ok": true, "generated": [{"event", "style", "file", "ms"}]}`.
- `sounds reset`: removes the person's mapping for that event (the file stays). `--json`: `{"ok": true, "event", "reset": true|false}`.
- The player plays what `sounds generate` writes: `.wav` through `winsound`, `.mp3` through the Windows media player.

### 2.1 `sounds styles --json`

```json
{"sample_rate": 44100,
 "max_ms": 1500,
 "recipe": "<plain text: how to play a segment list>",
 "default_style": {"<event>": "<style>"},
 "styles": {"<style>": {"about": "<plain words>", "ms": 320,
                        "segments": [{"type": "sine|square|triangle", "freq": [f_start, f_end], "ms": 320, "gain": 0.4,
                                      "attack_ms": 8, "release_ms": 80, "gap_ms": 0}]}}}
```

`styles` has one entry per style (all eight, in this order: beep, double, rise, fall, chord, alarm, tick, soft); `default_style` has one entry per event. A page plays a style in the browser by playing its segments with these rules, which chime.py's synthesiser follows exactly:

- Segments play in order. A segment starts when the previous one ended plus that one's `gap_ms`. A NEGATIVE `gap_ms` starts the next segment early; that is how the chord's three notes sound together.
- Frequency moves linearly in Hz from `freq[0]` to `freq[1]` over `ms`.
- Gain ramps linearly from 0 over `attack_ms`, holds, and ramps linearly to 0 over the last `release_ms`; where the ramps overlap the envelope is the lower of the two. The segment's `gain` scales the peak.
- Types: `sine`; `square` is a full-scale +1/-1 square (`sign(sin)`); `triangle` is `2/pi * asin(sin)`.
- The tone is the sum of its segments, clipped to full scale.

## 3. Requests from a page (the Soundboard, or any other page such as a usage page)

A page cannot run chime.py. It writes a request document into its OWN database, collection `requests`; the session that owns the page applies it at its next check with the commands above and writes the result back. The Soundboard's older request kinds carry `kind`, `target`, `note` and `created`; the four below carry `type`, their fields, `status`, `at` and `by`, and the owner session's pending-list query must read both.

```json
{"type": "usage_mute",     "account": "WORK", "on": true,  "status": "pending", "at": "<ISO>", "by": "<viewer id>"}
{"type": "usage_mute",     "account": "WORK", "on": false, "status": "pending", "at": "<ISO>", "by": "<viewer id>"}
{"type": "sound_replace",  "event": "done", "asset_id": "<32 hex>", "filename": "ding.mp3", "status": "pending", "at": "<ISO>", "by": "<viewer id>"}
{"type": "sound_generate", "event": "done", "style": "chord", "status": "pending", "at": "<ISO>", "by": "<viewer id>"}
{"type": "sound_reset",    "event": "done", "status": "pending", "at": "<ISO>", "by": "<viewer id>"}
```

`by` is an opaque viewer id (empty without the page's `user` capability), not a seat name. The owner session sets `status` to `done` or `failed`, with `result` (the command's one line) and `done_at` (ISO with a time zone offset).

State a page shows comes from documents its owner session writes after each check:

- `state/usage`: the object from `usage status --json` plus `synced_at`.
- `state/sounds`: the object from `sounds list --json` (with `accepts`) plus `styles` (the object from `sounds styles --json`, exactly 2.1) and `synced_at`.
- `state/roster`: the object `soundboard_sync.py roster` prints.

`synced_at` is an ISO time with a time zone offset (`2026-11-19T12:00:00-05:00`), so a page can compare it with `done_at`. A page shows a requested change as "requested, applied at the next check" until the state document confirms it.

## 4. The upload envelope for a replacement sound

The platform's page file store takes no audio type (it takes images, video, PDF, fonts and text, CSV, Markdown, JSON). A sound the person picks in the page is therefore wrapped in a text file, uploaded as `application/json`, and its asset id goes into the `sound_replace` request. The envelope is exactly:

```json
{"format": "soundboard-audio-1", "filename": "ding.mp3", "mime": "audio/mpeg", "size": 20480, "data_base64": "<the file's bytes, standard base64>"}
```

- `format` is the literal `soundboard-audio-1`. `filename` is the person's file name. `size` is the byte count of the audio before encoding. `mime` is `audio/mpeg` or `audio/wav` (the page also accepts what `accepts` lists).
- The audio is at most 5 MB (about 6.7 MB as base64). The page checks the size, the extension against `accepts`, and the first bytes (an mp3 starts `ID3` or a frame sync, a wav starts `RIFF....WAVE`) before it uploads.
- `soundboard_sync.py requests` unwraps an envelope into `<assets dir>/<asset id>-<clean file name>` and hands that local path to `sounds set`. It checks the envelope's `format`, the size, the extension and the header again, and refuses anything that looks like a program. A raw audio file saved under the asset id is accepted as well.

## 5. Not in this contract

No sending of sound files anywhere. No change to hooks or settings. No change to which events exist.
