# Loops, blocked seats, questions, brakes, mute, the clock, silence

How chime treats the timed loops of the reprompt skill and the person's own availability. All of this is optional: a person who runs no loops never meets most of it.

## Ticks

A turn that a loop prompt started (its prompt opens #KeepWarm, #StandReady, #StayReady, #CompactionForm and their High, Mid and Low forms) plays its tick sound, with no toast when it has nothing for the person. Which tick sound: #KeepWarm `tick`, #StandReady `tick_ready`, #StandReadyHigh `tick_high`, #StandReadyLow `tick_low`, #CompactionForm `tick_compaction`.

A tick needs the person when it is blocked (the reply opens MAJOR PROBLEM FOUND), opens with a decision phrase, carries a baton to relay, or has a line opening `Questions for you:` (or `Report questions for you:`). Such a tick shows a toast.

## Blocked seats and escalation

- A blocked tick on any #StandReady-family loop plays `urgent` three times, and counts blocked ticks in the reprompt skill's shared state for the session (the module in `tick_dir`, default `~/.reprompt/scripts`).
- On the third blocked tick in a row on a #StandReadyLow or #StandReady chain the tick also plays `escalate`, and the reprompt script runs the loop as #StandReadyHigh from the next tick. A chain the person armed as #StandReadyHigh never escalates.
- Ignored: after `ignore_after_ticks` (default 4) ticks in a row on #StandReadyHigh that needed the person, with no prompt from them between, the seat is ignored. That tick adds `abandon` and an "Ignored" toast, and the loop runs as #StandReadyLow from the next tick. While ignored, a tick that still needs the person plays `ignored` alone, in place of `urgent` three times or its tick sound. A tick that no longer needs the person clears the mark, and so does the person's next prompt.
- A turn the person starts resets the question and ignored counts.

## Questions

A tick report with a line opening `Report questions for you:` (written by a lead session that surfaces its reports' questions) counts as a question tick. From the second in a row the tick plays `questions` instead of its loop sound, at most once per `questions_cooldown_min` (default 120) across the whole machine; the Soundboard's cooldown setting in `silence.json` wins over the config. Every other question sounds by its first-line phrase, every time. The names a "Questions for ..." line may be addressed to are the config key `question_addressees` (default `["you"]`).

## Delegated seats

A seat listed in `~/.threadops/parley/delegated.json` (written by the parley skill) makes no attention sound: its decision phrases, MAJOR PROBLEM FOUND and questions are ignored, and it plays its plain tick, `done` or `peer` sound. Its manager routes and sounds its questions. RED ALERT is the one attention sound a delegated seat keeps.

## Lead sessions are louder

`<chime home>/heads.json`, written by the parley skill and only read here, is `{"<SEAT>": {"reports": <int>, "when": "<ISO UTC>"}}`. A seat is a lead while its entry has `reports` above zero and `when` under 24 hours old. A lead plays at `0.5 x head_gain` volume (default 1.2, so 0.6, never above 1.0); everyone else at the media player's default 0.5.

## Brakes

While `~/.threadops/brakes/<session_id>.json` exists (written by the brakes skill) the Stop hook plays only `brakes` plus the low-usage alarm, the prompt hook plays no `ack` and injects the brakes text instead of the rules, and auto-compaction is silent.

## Mute

All of these silence sounds, while toasts still show without sound:

- the file `~/.chime_muted` (or the path in the config key `mute_file`) exists; one file mutes every account on the machine, delete it to unmute;
- a Zoom meeting is open (a meeting window owned by `zoom.exe`; Zoom merely being open does not mute). Set `"mute_during_zoom": false` to turn this off;
- the person is clocked out (below).

While muted, the prompt hook tells the session, and the closing line becomes `Sound: muted (would play <name>) · <SEAT>`. First-line phrases still open the reply.

## The clock

`~/.threadops/presence.json` is `{"state": "in" | "out", "since": "YYYY-MM-DD HH:MM", "note": "..."}`; the Soundboard writes it. While the state is `out`, chime is muted like the mute file, tick counters do not move (no escalation, no ignored mark), and the prompt hook tells every session the person is away: no decision phrase or MAJOR PROBLEM FOUND for attention, no mid-turn chime play, questions wait. For two hours after the person clocks in, sessions are told they are back.

## Silence

A sound named in `<chime home>/silence.json` under `"sounds"` never plays; toasts still show. The key is the sound's name or its event key. When the turn's sound is silenced the closing line is `Sound: silenced (would play <name>) · <SEAT>`. The Soundboard writes this file through `soundboard_sync.py apply`.

## Dictation

While a dictation app (config `dictation_apps`, default `["wispr flow"]`) holds an active microphone capture session, a turn's toasts, sounds and spoken name are handed to a detached process that waits for the dictation to end plus 0.6 seconds, then plays them one after another, so no alert lands in a dictation. After `dictation_hold_max_s` (default 300) a held turn plays anyway. `hold_during_dictation: false` turns it off. Each hold adds a line to `<chime home>/hold_log.txt`. `CHIME_FAKE_DICTATING=1` (or 0) forces the answer in tests.

## Names in toasts and spoken names

- A toast names the session by its tab title: the newest `custom-title` in its transcript, else its `ai-title`; failing both, the seat on the closing Sound line; then a seat id found in the text (only when the config key `seat_id_regex` says what a seat id looks like); then a name from the session registry (`sessions_glob`); then "a session in <project folder>".
- After the sounds, a turn that needs the person has the session's name spoken (`speak_names`: `attention` (default), `all` or `off`). The words come from `<chime home>/spoken/<tab title>.txt` (one line), else the config `spoken_names`, else the title read token by token with the config `words` (an upper-case token to the words to say) and the suffix `seat_suffix_regex` dropped. Each seat gets its own voice from `voice_pool` on first use, kept in `<chime home>/voices.json`. The clip is rendered once with the `edge-tts` package when it is installed (`pip install --user edge-tts`, internet only while rendering); otherwise the Windows voice speaks.
