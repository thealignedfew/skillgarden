---
name: chime
description: "Audible alerts and toasts for Claude Code sessions, so a person who runs several sessions at once can tell from across the room which one needs them and how badly. Use when a reply must open with RED ALERT, MAJOR PROBLEM FOUND, URGENT DECISION NEEDED, IMPORTANT DECISION NEEDED or Decision needed, when writing the closing Sound line every reply carries, when playing an alert mid-turn, when changing which sound an event plays, or when installing, testing or repairing the sound hooks. Owns one alert script (scripts/chime.py). Windows is the supported platform for sound and toasts. A fresh install makes sound with nothing downloaded."
---

# chime

One script, one set of rules. Each kind of moment in a Claude Code session has its own sound, and a toast names the session, so a person running many sessions hears which one needs them without looking. Every account installs the skill once and points its hooks at the installed `scripts/chime.py`. A project never keeps its own copy of the script: two copies play twice per turn.

## How it works

- Three hooks run `scripts/chime.py`: `decision` when a turn ends (Stop), `prompt` when the person submits a prompt (UserPromptSubmit), `autocompact` before an automatic compaction (PreCompact).
- At the end of a turn the script picks ONE sound from the reply's first line and from what started the turn, shows a toast, and plays the sound.
- The skill ships no audio. Every event's default sound is a short tone the script generates itself the first time it is needed, into the sounds folder of the person's chime home (see "Your settings live outside this folder"). Nothing is downloaded and nothing is written into this folder. A person can give any event their own mp3 or wav, or another generated tone.
- Python 3 and its standard library only. Sound and toasts work on Windows (PowerShell, the Windows media player, `winsound`). On other systems the script runs and decides but cannot play.
- It never blocks or fails a session. Every hook mode swallows its errors and exits 0.

## Install

An agent installs this skill for one account home like this. It never changes a settings file on its own: it shows the exact edit and waits for the person's yes.

1. Copy this whole folder to `<account home>/skills/chime/` (for a default setup, `~/.claude/skills/chime/`).
2. Show the person the three hook entries below, with `<python>` and `<skill folder>` filled in with real paths. After their yes, add them to `<account home>/settings.json`, keeping every other setting as it is. Write the file atomically and check that it is still valid JSON.
3. Find and remove any other hook entry that runs a sound or alert script (project `.claude/settings.local.json` files too). Keeping one would play every turn twice.
4. Verify (see "Verifying").

```json
{
  "hooks": {
    "Stop": [{"hooks": [{"type": "command", "command": "\"<python>\" \"<skill folder>/scripts/chime.py\" decision", "timeout": 40}]}],
    "PreCompact": [{"matcher": "auto", "hooks": [{"type": "command", "command": "\"<python>\" \"<skill folder>/scripts/chime.py\" autocompact", "timeout": 40}]}],
    "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "\"<python>\" \"<skill folder>/scripts/chime.py\" prompt", "timeout": 40}]}]
  }
}
```

If the account already has hooks of these kinds, add these entries to the existing lists rather than replacing them.

## What plays, and when

The Stop hook picks ONE sound for each finished turn, from the reply's FIRST non-empty line only (leading markdown such as `**`, `#` or `>` is ignored). A phrase anywhere else in the reply plays nothing: a reply that only mentions a phrase is not an alarm.

| The reply's first line opens with | Plays | Toast |
|---|---|---|
| RED ALERT (capitals) | `red_alert` alone, then `relay` if the reply carries a baton | RED ALERT: seat, and the words after the phrase |
| MAJOR PROBLEM FOUND | `urgent`, `boing`, `important` (no `done`: a blocked turn did not finish the request) | URGENT + important: seat |
| URGENT DECISION NEEDED | `urgent` | URGENT: seat |
| IMPORTANT DECISION NEEDED, or Decision needed | `default`, `boing`, `important` | Important: seat |
| URGENT AND IMPORTANT | `urgent`, `boing`, `important` | URGENT + important: seat |
| none of these | by what started the turn, below | |

| What started the turn | Plays | Toast |
|---|---|---|
| the person's own prompt | `ack` the moment it arrives, then `done` when it finishes (not after MAJOR PROBLEM FOUND) | Finished: seat |
| a #KeepWarm or #StandReady tick (see the reprompt skill) | `tick`, `tick_ready`, `tick_high` or `tick_low` by loop, `tick_compaction` for #CompactionForm | none |
| another session's message | `peer` | Session message handled: seat |
| anything else (another cron prompt, a background task, a continuation) | nothing, unless the reply opens with a phrase or carries a baton | |

A reply with a `[BATON ...]` block at the start of a line plays `relay` after the opener sound, or in place of `tick`, `peer` or `default`: the person has something to paste. Auto-compaction plays `compact`, and so does a reply that hands over a compaction prompt (its first line opens #CompactionPrep or #SmartCompact, or a line opens "Type /compact"), always as the very last sound. A turn is never chimed twice.

All 21 events, what sets each off and its default tone are in `references/sounds.md`. Ticks, blocked seats, questions, brakes, mute, the clock, silence and the other loop behaviour are in `references/loops.md`. The low-usage alarm is in `references/usage.md`, and RED ALERT in `references/red-alert.md`.

## The two rules the prompt hook gives every session

The `prompt` hook adds a short text to every turn, so each session knows these without reading this file:

1. **A session blocked on the person says so loudly.** When it stops on something only the person can clear, the reply's first line opens with MAJOR PROBLEM FOUND, and the session also plays it mid-turn, so the person hears it while the turn still runs:

   ```
   "<python>" "<skill folder>/scripts/chime.py" play major "<SEAT>" "<what is blocked>"
   ```

   `play urgent`, `play important`, `play compact` and `play redalert` exist for the other levels. A baton line alone is not enough.
2. **Every reply ends with one Sound line**, naming the sound the Stop hook will play and the seat (the session's name), so the person can match a sound they heard to the reply that made it:

   ```
   Sound: done (turn the person started) · MY-SEAT
   Sound: done + default + boing + important (decision) · mid-turn: important · MY-SEAT
   ```

   The separator is a middle dot, or a spaced full stop when the middle dot is awkward to type. The hook reads the seat from this line for the toast. While muted the line reads `Sound: muted (would play <name>) · SEAT`, and for a silenced sound `Sound: silenced (would play <name>) · SEAT`.

The wording of both rules, and of every other text the hook injects, is a default in the script that a person's config can replace (`references/config.md`).

## Commands

All of them print one line of plain text, or one JSON object with `--json`. Pass `--by <seat>` on every command that changes something, so the change can be traced in `<chime home>/config_log.txt`.

```
chime.py sounds list [--json]                         each event, its file, whether it is a default, the person's own or a generated tone, and "accepts" (the file types the player plays)
chime.py sounds set <event> <file.mp3|file.wav>       copy a file (up to 5 MB) into the sounds folder and play it for that event
chime.py sounds generate <event> [--style STYLE]      make a short tone for that event; styles: beep double rise fall chord alarm tick soft
chime.py sounds generate --all-missing                make a tone for every event whose chosen file is missing
chime.py sounds reset <event>                         back to the skill's default for that event (the person's file stays)
chime.py sounds styles [--json]                       the recipe of every style, as data
chime.py usage status [--json]                        every account's last usage reading and mute
chime.py usage mute <ACCOUNT> [--cycle | --until "YYYY-MM-DD HH:MM"] [--by SEAT] [--why "text"]
chime.py usage unmute <ACCOUNT> [--by SEAT]
chime.py redalert check|fire|verdict|list|example ...   the red alert log (references/red-alert.md)
chime.py play urgent|major|important|compact|redalert "<SEAT>" "<what>"
```

Only `.mp3` and `.wav` play; other formats are refused with a plain message. `<ACCOUNT>` is a name from the config's `account_names`, an account folder name, or `this`.

## The Soundboard

`soundboard/SOUNDBOARD.html` is a control page: every sound, a mute on each, a mute for each account's low-usage alarm, a clock in and out, and per sound "replace with my own file", "generate a tone" and "reset to default". It is published by the person's own Claude session as an artifact, and the session applies the page's requests with the commands above. See `soundboard/README.md` and `CONTRACT.md` (the request documents and the JSON the commands print). The page ships no audio.

## Optional: real sound clips

`scripts/fetch_clips.py` fetches third-party sound clips named in `clips.json` into the person's sounds folder, only when the person runs it. Nothing runs it automatically, and nothing here needs it. The clips are owned by others: the person downloads them for their own local use and is responsible for that download. Run `fetch_clips.py --list` to see the manifest and `--check` to see which clips are present, then give a clip to an event with `chime.py sounds set <event> <file>`.

## Your settings live outside this folder

This folder is replaced whole whenever the skill is updated, so anything kept inside it is lost. Never put local configuration, decisions, tweaks, sound files, notes or edited copies of this skill's files in this folder.

- A person's settings, choices and files go in the per-person folder `~/.threadops/<skill>`, or in the folder named by the environment variable `<SKILL>_HOME` when it is set. It is one folder per person, shared by all of that person's accounts. For this skill: `~/.threadops/chime`, and `CHIME_HOME`.
- A household's own rules for the skill (how it is used in your team, extra steps, preferences that are instructions rather than settings) go in a small private skill named `<skill>-house`, installed beside this one, which says: read the public skill, then these additions. For this skill: `chime-house`.
- An agent that is asked to customise, tune or extend this skill writes to those two places and nowhere else. If a request can only be met by changing a file in this folder, the agent says so and offers the pull request below instead of editing in place.
- After an update nothing of the person's should be missing, because none of it was in this folder.

In this skill the person's settings are `<chime home>/config.json` (the same keys as `chime.json`, merged over it key by key), the sounds in `<chime home>/sounds/` (a path written `user:<file>` points there), and the mute and log files beside them. `references/config.md` lists every key.

## Propose improvements upstream

When a person or their agent makes a significant improvement to this skill (a fix, a new behaviour, a better default, a clearer instruction), the agent offers, once, to propose it to the public repository (github.com/thealignedfew/skillgarden) as a pull request from a fork. Before asking, it says in plain words what would be shared: the changed files and a short summary of why.

- Nothing is sent without the person's yes. A no is final for that change: the agent does not ask again.
- Nothing personal goes into it: no names, accounts, paths, addresses, settings or sound files from the person's own chime home, no transcripts, no credentials. The agent reads the diff for these before showing it.
- The change is made against the unmodified public skill, never against a customised copy.
- Every pull request is reviewed and tested by the maintainers before any merge, and none is merged automatically. See `CONTRIBUTING.md` in the repository.

## Verifying

`CHIME_DRY_RUN=1` makes the script print its decision (`TOAST title | body`, `PLAY key (name) vol`) instead of playing it. Point `CHIME_HOME`, `TEMP` and the user profile at a scratch folder so nothing real is touched, then feed the Stop hook one test reply per row of the tables above through a fake transcript: each first-line phrase, a reply that mentions a phrase past its first line (must play `done` or `default`, not the phrase), a duplicate of the same turn (must print `SKIPPED duplicate`), an `autocompact` call, and a `prompt` call (must print valid UserPromptSubmit JSON carrying the two rules). Check that the toast names the seat from the Sound line. Then play one real sound per account to confirm the audio path.

## Never

- Block, delay or fail a session: every error is swallowed and the script exits 0.
- Keep a second copy of the script in a project.
- Put credentials, transcripts or a person's own settings in this folder or in a pull request.
- Change a settings file, a hook or a permission without showing the person the exact edit first.
- Run what `fetch_clips.py` downloads: it only saves audio files, and refuses anything that does not look like an mp3.
- Name a module in the config (`usage_server`, `stop_gate`, `tick_dir`) unless the person wrote that path themselves: chime imports and runs those files.
