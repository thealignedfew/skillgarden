# reprompt

A Claude Code skill that lets a session prompt itself again on a timer, between your own prompts. Two kinds of tick: a warm tick that does almost nothing but keep the prompt cache alive, and a full tick in which the session checks its inbox, its builds and the steps you said you would take, and acts on what it finds. One numbered command, `/reprompt <level> <step-down> <quiet-first>`, chains them.

It is for people who leave long-lived Claude Code sessions open and are tired of paying to reload a cold context, or of finding that a session stalled while they were away.

## What you get

- Six loops: #KeepWarmHigh (warm, with a full check every 10th tick), #KeepWarmLow (warm only), #StandReadyLow, #StandReadyMid and #StandReadyHigh (full unattended work every 50, 30 or 15 minutes), and #CompactionForm (a 10-minute watch through an auto-compaction).
- A numbered plan: `/reprompt 3 4 8` is eight quiet ticks, four fast ticks, four slow ticks, then warm.
- A tick script that decides everything countable: the next cron time, whether a second chain exists, what changed in the files you point it at, the context fill, when a compaction is near.
- Compaction prep at 50 percent context and a watch at 92 percent, so an auto-compaction does not lose the thread.
- A one-line reply form, so a quiet tick costs one line of screen.
- Optional links to a parley page (the sibling skill) and optional hooks of your own.

## What it needs

- Claude Code with the cron tools (`CronCreate`, `CronList`, `CronDelete`). The loops are chains of one-shot, session-only jobs.
- Python 3.11 or later. The scripts use only the standard library.
- Permission for the session to run `python <path>/keepwarm_tick.py`. If you use a permission mode that asks, allow that one command.

## Install

1. Copy the skill folder into your Claude Code skills directory:

   ```
   cp -r reprompt ~/.claude/skills/reprompt
   ```

   On Windows, copy it to `%USERPROFILE%\.claude\skills\reprompt`. The skill is `SKILL.md`. The two thin shorthands in `shorthand/keepwarm` and `shorthand/standready` are optional: copy them into the skills directory too only if you want `/keepwarm` and `/standready`.

2. Put the scripts in a permanent folder that will not move, for example `~/.reprompt/scripts`: copy `keepwarm_tick.py`, `keepwarm_common.py` and `time_stamp.py` there, together. Every wake prompt names this folder, and a moved folder breaks a running chain.

3. Tell the session where they are. Put one line in your `CLAUDE.md`, for example "The reprompt scripts are in ~/.reprompt/scripts", or say it when you first arm a loop. The skill calls that folder `<TICK_DIR>`.

4. Optional: set the environment variables below. With none set, state goes to `~/.reprompt` and the context window is taken to be 200000 tokens.

Use the command that runs Python 3.11 or later on your machine in the wake prompts (`python` or `python3`).

## Worked example

You type `/reprompt 2 0 1` in a session: one quiet tick, then #StandReadyLow for good. (Times and context figures below are illustrative.) The session checks `CronList`, then arms the plan:

```
python ~/.reprompt/scripts/keepwarm_tick.py --seat demo --arm --plan "2 0 1" --session "<transcript path>" --watch notes.md
PLAN 2 0 1: quiet 0/1 as #KeepWarmHigh, then level 2 #StandReadyLow
FIRST cron="28 17 18 11 *"   recurring=false   next tick 17:28
watch baseline recorded for 1 file(s)
```

It creates that one-shot cron with the plan's wake prompt (from `SKILL.md`) and tells you in one line what runs now, what follows, the next tick time and how to stop. At 17:28 the prompt fires and the session runs the same script with `--loop Plan`:

```
PLAN 2 0 1: quiet 1/1 as #KeepWarmHigh, then level 2 #StandReadyLow
REARM cron="18 18 18 11 *"   recurring=false   next tick 18:18
watch: no change in 1 file(s)
CONTEXT 41% (was 39%, 0 compactions)
MODE minimal: warm only, no sweep
REPLY #KeepWarmHigh, noop, context 41% (was 39%), next tick 18:18 (hybrid 1/10) (plan 2 0 1: quiet 1/1 as #KeepWarmHigh, then level 2 #StandReadyLow)
```

The session creates the next one-shot cron from the `REARM` line, echoes the `REPLY` line, and nothing else. The next tick prints `MODE full`, and the session does its full check. `/reprompt stop` ends it.

## Optional integrations

None of these ship here and nothing requires them.

- **A transcript path each turn.** The context reading, compaction prep and #CompactionForm need the session's transcript path. A UserPromptSubmit hook can print it into context. In `~/.claude/settings.json`, as a starting point (check the hooks documentation for your Claude Code version, since hook settings change):

  ```
  {
    "hooks": {
      "UserPromptSubmit": [
        { "hooks": [ { "type": "command",
          "command": "python -c \"import json,sys; print('Transcript path for this turn: ' + json.load(sys.stdin)['transcript_path'])\"" } ] }
      ]
    }
  }
  ```

  Without it, leave `--session` out of the wake prompt. Ticks still run, keyed on the `--seat` name, with `CONTEXT unavailable`.

- **A compaction hook.** A SessionStart hook for the `compact` source can tell the session to read the prompt it registered (the `compaction_prompt` key in its state file) before anything else. Without one, point `/compact` at the file.
- **A per-prompt hook** can call the helpers in `keepwarm_common.py`: `measure`, `prep_due`, `form_due`, `lost_loop_line`.
- **An alerting hook.** The first words of every REPLY line are the loop's name, so a sound or notification hook can key on them. Such a hook can also write `blocked_ticks` and `abandoned` into the session's state file, which switches on the blocked-session upgrade and the ignored drop.
- **A signature command.** Set `REPROMPT_SIGNATURE_CMD` to run any command after each tick, with `{seat}`, `{session}`, `{stamp}` and `{out}` filled in. Off by default.
- **Parley.** If a session owns a parley page, register it with `--parley <url>` and full ticks link it, read its comments and statuses, and write its heartbeat.

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `REPROMPT_STATE_DIR` | `~/.reprompt` | where state files live, one JSON file per session, plus `quiet_notice.json` if you use it |
| `REPROMPT_CONTEXT_WINDOW` | `200000` | the model's context window in tokens, for the context percentage; set it for a larger model |
| `REPROMPT_SIGNATURE_CMD` | unset | an optional command run after each tick |
| `REPROMPT_RECHECK_HOUR` | `7` | the local hour from which the once-a-day parley recheck reminder may print |

## Limits and honest caveats

- The loops are session-only crons: they fire only while the session is idle, and they can be lost on a reload or restart. `CronList` is the truth, and a lapsed chain costs one cold cache, not a wrong answer.
- The 50-minute default period assumes a one hour cache lifetime. If yours differs, pass `--period`.
- The context percentage is a reading of the previous turn against a window size you supply. It cannot know the real window of your model.
- Nothing in the loops can start a session that has ended, or one that a usage limit has stopped.
- This was built for one person's workflow and then generalized. Some defaults may still feel specific; `seat` and `codename` are just labels.
- The scripts were exercised on Windows with Python 3.11 in an isolated state folder, and the skill text was not re-run inside a fresh Claude Code session for this edition. The hook snippet above is untested.

Apache-2.0, see the repository LICENSE.

Not affiliated with Anthropic. 'Claude Code' is named only to say what this works with. By The Aligned Few.
