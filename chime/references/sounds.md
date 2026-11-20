# Events, sounds and tones

chime has 21 sound events. A sound event is a name for a moment; which file plays for it is the person's choice and is kept in their chime home, never in this folder.

## The events

| Event | What sets it off | Default tone |
|---|---|---|
| `urgent` | URGENT DECISION NEEDED; the first sound of URGENT AND IMPORTANT and of MAJOR PROBLEM FOUND; played three times by a blocked seat on a loop tick; `play urgent` and `play major` | double |
| `important` | the last sound of an important decision and of MAJOR PROBLEM FOUND; `play important` | chord |
| `boing` | the bridge between the opener and `important` | rise |
| `default` | the opener of an important-only decision; stands in for `done` when `done` is not set | soft |
| `tick` | a #KeepWarm tick with nothing for the person | tick |
| `tick_ready` | a #StandReady tick with nothing for the person | tick |
| `tick_high` | a #StandReadyHigh tick with nothing for the person | tick |
| `tick_low` | a #StandReadyLow tick with nothing for the person | tick |
| `tick_compaction` | a #CompactionForm tick | tick |
| `peer` | a turn another session started has finished | beep |
| `compact` | auto-compaction, or a reply that hands over a compaction prompt (always last) | fall |
| `relay` | the reply carries a `[BATON ...]` block for the person to paste | double |
| `ack` | the person's own prompt has reached the session | beep |
| `done` | a turn the person started has finished | rise |
| `questions` | a lead session surfaced its reports' questions on two ticks in a row (at most once per cooldown) | double |
| `low_health` | an account is at or above the usage alert line | alarm |
| `brakes` | the only sound of a session that is braked | fall |
| `red_alert` | a reply opens with RED ALERT | alarm |
| `escalate` | a blocked seat's loop moves up to #StandReadyHigh | rise |
| `abandon` | an ignored seat stops trying and drops to #StandReadyLow | fall |
| `ignored` | each tick of an ignored seat that still needs the person | soft |

Ticks are all `tick` by default, so they are quiet and alike; give `tick_high` and `tick_low` different sounds if you want to tell the loops apart by ear.

## Generated tones

Every default is written in `chime.json` as `gen:<style>`. The first time an event needs its sound, the script writes `gen-<event>-<style>.wav` into `<chime home>/sounds/` (16-bit mono, 44.1 kHz, under 1.5 seconds, standard library only, the same bytes every time) and plays it. Nothing is downloaded and nothing is written in the skill folder. Styles, each defined by one table in `chime.py` that `sounds styles --json` prints:

| Style | Sounds like | Length |
|---|---|---|
| beep | one steady beep | 320 ms |
| double | two short high beeps | 370 ms |
| rise | a pitch that climbs | 520 ms |
| fall | a pitch that drops | 520 ms |
| chord | three notes together | 700 ms |
| alarm | six square-wave alternations, harsh and urgent | 840 ms |
| tick | one very short click | 45 ms |
| soft | a quiet, slow-fading note | 450 ms |

## Changing a sound

- `chime.py sounds set <event> <file>` copies an `.mp3` or `.wav` (up to 5 MB, and it must look like one) into the sounds folder and writes `"<event>": "user:<file>"` into `<chime home>/config.json`. A name that already exists with different content is never overwritten: a suffix is added.
- `chime.py sounds generate <event> [--style STYLE]` makes a tone in that style for that event and maps the event to it. With no style it uses the default style for the event.
- `chime.py sounds reset <event>` removes the person's mapping; their file stays.
- `chime.py sounds list --json` prints one row per event: `event`, `label`, `file` (`gen:<style>`, `user:<file>` or a path), `source` (`default`, `user` or `generated`), `exists`, `name`, and `style` when the sound is a generated tone; and at the top level `user_dir` and `accepts`. If a `user:` file has gone missing, the default plays and the row carries `mapped_missing`.
- `"ack": ""` in the config turns off the sound on prompt arrival; leave an event out of the config to keep its default.
- Only `.mp3` (through the Windows media player) and `.wav` (through `winsound`) play. Other formats are refused by `sounds set`.

## The Sound line names

The closing Sound line names a sound by its `names` entry in the config, which is the event key unless the person gave it a friendlier name. Setting a file does not change the name.

## Third-party clips

`scripts/fetch_clips.py` is optional and runs only when a person runs it. It reads `clips.json` (a list of `name`, `file`, `source_url`), downloads each missing clip into `<chime home>/sounds/`, checks that it starts like an mp3 and is at most 5 MB, and refuses a non-https address. A person's own `<chime home>/clips.json`, in the same shape, adds entries or replaces ones of the same name. An entry with no `source_url` cannot be fetched and is reported. The clips are third-party sounds a person fetches for themselves: owned by others, downloaded for the person's own local use, no licence granted.
