# Configuration

Two files, and only the second is the person's.

1. `<skill folder>/chime.json` holds the skill's defaults. It is replaced by every update. Do not edit it.
2. `<chime home>/config.json` holds the person's overrides, with the same keys, merged over the defaults key by key. `<chime home>` is `~/.threadops/chime`, or the folder named by the environment variable `CHIME_HOME`. It is written by `chime.py sounds set|generate|reset` and may be edited by hand. A missing, unreadable or wrongly typed value means the default: it never stops a sound, and `sounds set` refuses to rewrite a `config.json` it cannot read.

Keys named `names`, `labels`, `account_names`, `words`, `spoken_names` and `texts` are merged one level deep (an entry in the person's file replaces the same entry, other entries stay).

## Sound keys

One key per event (see `sounds.md`): `urgent`, `important`, `boing`, `default`, `tick`, `tick_ready`, `tick_high`, `tick_low`, `peer`, `compact`, `relay`, `tick_compaction`, `ack`, `done`, `questions`, `low_health`, `brakes`, `red_alert`, `escalate`, `abandon`, `ignored`. A value is one of:

- `gen:<style>` a tone the script generates (the skill's defaults);
- `user:<file>` a file in `<chime home>/sounds/` (a missing file falls back to the skill's default);
- `sounds/<file>` a file in the skill's own folder (the skill ships none);
- an absolute path to an `.mp3` or `.wav`;
- `""` for no sound (useful for `ack`).

## Other keys

| Key | Default | Meaning |
|---|---|---|
| `names` | each event's own name | the name of each event on the closing Sound line |
| `labels` | a label for `red_alert` | a plain-words label per event for the Soundboard |
| `account_names` | none | an account home's folder name to the short name shown in the usage toast, for example `{"work": "WORK"}` |
| `sessions_glob` | none | a glob of session registry files (`*.json` with `sessionId`, `name`, `nameSource`, `cwd`) used to name a session when its transcript has no title |
| `usage_server` | none | path of a Python file offering `fetch_raw()` or `fetch_usage()`; without it there is no low-usage alarm (`usage.md`) |
| `usage_alert_pct` | 90 | the alert line, percent |
| `usage_alert_every_min` | 30 | at most one alarm per account per this many minutes |
| `usage_log_from_pct` | 70 | readings at or above this are logged |
| `questions_cooldown_min` | 120 | minutes between `questions` plays across the machine |
| `ignore_after_ticks` | 4 | needy #StandReadyHigh ticks before a seat is ignored |
| `question_addressees` | `["you"]` | the names a "Questions for ..." line may be addressed to |
| `speak_names` | `attention` | `attention`, `all` or `off` |
| `words`, `spoken_names`, `voice_pool` | none, none, twelve English neural voices and more | how a session's name is spoken (`loops.md`) |
| `seat_id_regex` | none | a regular expression for the shape of a seat id, used to find one in a reply ("Sent by X", "[X]", "seat X") |
| `seat_suffix_regex` | none | a suffix of a session title that is not read aloud |
| `mute_file` | `~/.chime_muted` | the file whose existence mutes chime |
| `mute_during_zoom` | true | mute while a Zoom meeting is open |
| `hold_during_dictation`, `dictation_apps`, `dictation_hold_max_s` | true, `["wispr flow"]`, 300 | wait while a dictation app records |
| `head_gain` | 1.2 | volume factor for a lead session |
| `peer_prefixes` | none | text at the start of a prompt that marks it as another session's relayed message (a literal prefix, not a regex) |
| `notification_prefixes` | none | text at the start of a prompt that marks it as a system notification, not the person |
| `tick_dir` | `~/.reprompt/scripts` | the folder of the reprompt skill's scripts, whose `keepwarm_common` module holds the tick counters |
| `rules_text` | `full_once` | how often the prompt hook injects the whole rules block. `full_once`: the whole block on a session's first prompt and on the first prompt after each compaction, one short line (350 characters at most) on every other prompt, plus the clock-out, mute, silenced-sound or RED ALERT notice only when it differs from what the session was last shown. `full_always`: the whole block on every prompt (how chime behaved before version 21). `short_always`: the short line only. Any other value is `full_once` |
| `stop_gate` | none | path of an optional Python file with `decide(data, config())` and `config()`; when it says `block`, this stop is not the end of the turn and chime stays quiet |
| `transcripts_glob` | `~/.claude/projects/*/*.jsonl` | where `soundboard_sync.py roster` finds session transcripts; when the glob has a `*` followed by a folder named `home` that wildcard is read as the account folder |

`usage_server`, `stop_gate` and `tick_dir` name files chime imports and runs. Set them only to code you wrote or trust.

## texts: every sentence chime injects

The prompt hook, the clock, mute, silence, brakes and red alert paragraphs are defaults in `scripts/chime.py` (`DEFAULT_TEXTS`). The config key `texts` replaces any of them by key; a text whose `%` placeholders do not fit is ignored and the default is used.

| Key | Placeholders, in order |
|---|---|
| `prompt_rules` | the Python path, the script path |
| `prompt_rules_short` | none (at most 350 characters; the line a session gets on every prompt after the first) |
| `rules_status_clear` | none (said once when an earlier clock-out, mute or silenced-sound notice no longer holds) |
| `grid` | 22: the sound names (urgent, default, boing, important, urgent, boing, important, tick, tick_high, tick_low, peer, done, ack, urgent, escalate), the ignore count (`%d`), abandon, ignored, questions, the cooldown in minutes (`%d`), relay, compact |
| `clock_out` | since, an optional " (note)" |
| `clock_in` | since |
| `silenced` | the silenced names, comma separated |
| `muted` | the reason |
| `person_clocked_out` | none |
| `brakes_rules` | none |
| `ra_base`, `ra_merited`, `ra_not_merited`, `ra_advice_not_merited` (one `%s`: a date), `ra_example_tag`, `ra_example_note`, `ra_default_by` | the red alert paragraph and commands |

A household that keeps its own wording does it here, in the person's `config.json`, so an update to the skill never overwrites it.
