---
name: ramgovern
description: "ramgovern: a Windows RAM governor for many Claude Code sessions. Pages idle claude.exe and VS Code extension hosts out of RAM; optionally slows background programs (the brake) and checks drives. Use for /ramgovern (status, on, off, pid, brake, drives) or when asked to trim idle sessions, free RAM, or slow a program that hogs the PC."
---

# ramgovern

The engine, its settings and its log live in the ramgovern folder (call it `<GOV>`: the folder holding `govern.ps1` and `govern.json`; ask the user where it is if you do not know). This skill only reads and flips them. See `README.md` in that folder for how it works and how to install it.

## What a trim is

A trim (psapi `EmptyWorkingSet` on one process) moves a process's resident pages to the standby list and then the pagefile. The process keeps running and faults pages back in on demand, so there is nothing to undo. `govern.ps1` decides which processes may be trimmed: `claude.exe` at stage 1, plus VS Code extension hosts at stage 2. Only idle processes qualify, and never the foreground window's process, a name in `exclusions`, the caller's own ancestor chain, or a VS Code host that carries a live AI-extension session. A page-in storm writes `<GOV>\govern.stop` and halts every later run until a person clears it.

## Commands

Each command replies with one line of figures and the full path of any file it names. None of them kills, suspends or restarts a process, edits Claude Code settings, or changes a system setting.

### /ramgovern status (read-only)

1. Read `<GOV>\govern.json`: `enabled`, `stage`, `cadence_minutes`, `task_name` (default `ramgovern`).
2. If `<GOV>\govern.stop` exists, say plainly that the Governor is halted by a storm and show that file's content.
3. `Get-ScheduledTask -TaskName <task_name>`: its state, and `Get-ScheduledTaskInfo` for the last and next run. If the task is absent, say so and point to `register_task.ps1`. The task's Last Result always reads 0 (the headless console host masks exit codes), so judge runs by the log, not by that field.
4. Quote the last three lines of the log (`log_path`, default `<GOV>\govern.log`) as written, and give today's `summary-YYYYMMDD.md` path if it exists.
5. Reply: `ramgovern on|off, stage N, task <state>, last run <stamp> trimmed <n>, resident <before> -> <30 s> MB, storm none|HALTED.`

### /ramgovern on

1. If `govern.stop` exists, report it and stop. Clearing a storm halt is the user's decision: they read the file, then delete it.
2. Run a dry run first, `& "<GOV>\govern.ps1" -Mode task`, and show its one `DRY` line.
3. Set `"enabled": true` in `govern.json` by changing that one key and touching nothing else.
4. If the task is not registered, give the user the one line to run themselves: `powershell -NoProfile -ExecutionPolicy Bypass -File "<GOV>\register_task.ps1"`. Registering a scheduled task is persistence, so the user runs it, not the agent.
5. Reply with the dry-run figures and whether the task exists.

### /ramgovern off

1. Set `"enabled": false` in `govern.json` (one key). The task keeps firing and writes a `DRY` line each run, so the log shows it is alive; nothing is trimmed.
2. Say what is unchanged: trimmed processes regrow on their own, `govern.stop` (if present) stays, and the scheduled task stays registered. To remove the task: `Unregister-ScheduledTask -TaskName <task_name> -Confirm:$false`.
3. Reply: `ramgovern off; task still logs DRY lines.`

### /ramgovern pid <n>

Trims one process now, using the full idle test.

1. Run `& "<GOV>\govern.ps1" -Mode seat -TargetPid <n> -Apply`. It trims only if `enabled` is true, the process is idle for `idle_seconds`, is not the foreground process and is not the caller's own ancestor; otherwise it logs `SKIPPED`, `REFUSED` or `DRY` and says why. Never guess a pid from a name or a memory size: ask the user for it.
2. Reply with the log line's resident and free-RAM figures, or the reason it was skipped.

### /ramgovern brake (list | suggest | add <name> | off <name>)

The brake is optional (0.2.0). It slows listed background programs while the user is at the machine and puts each back as it found it when they have been away ten minutes. It never stops, suspends or kills.

- `list`: show the targets in `<GOV>\brake.json` (name, the command-line match, helpers, on or off, who approved it and why) and the last ten `brake` lines of the log. If there is no `brake.json`, say the brake has no targets.
- `suggest`: run `python <GOV>\scripts\brake_suggest.py --days 7` and show its lines. It needs the sampler's lines (`samples-*.jsonl`); if there are none, say so and point to `scripts\sampler.ps1` and `scripts\register_brake.ps1`. "suggest" means worth asking the user about; it is not an instruction.
- `add <name>`: only with the user's yes, in their own words, for that process. Copy `assets\brake.example.json` to `brake.json` if it does not exist, then add one target: `name` (without `.exe`), a `match` that keeps the user's own copies out, `enabled` true, `approved` (their name and the date) and `why` (the evidence). The running brake logs a `CONFIG loaded` line within one interval; confirm it.
- `off <name>`: set that target's `enabled` to false. That is the undo.

The brake refuses its protected list even if `brake.json` names one. Registering the scheduled tasks is the user's step: give them `powershell -NoProfile -ExecutionPolicy Bypass -File "<GOV>\scripts\register_brake.ps1" -DryRun` first.

### /ramgovern drives (read-only)

Run `python <GOV>\scripts\disk_health.py` and show its `FLAG` and `ok` lines. It reads the brake's once-a-minute lines, the System event log and, where Windows allows it, the drives' own counters. It changes nothing. If `drives.json` is missing, say that the endurance line is skipped until the user names their SSDs and rated terabytes written (`assets\drives.example.json`).

## Hard limits

- Never trim VS Code's main process, its renderers, explorer.exe, dwm.exe, or the foreground process. Never kill or suspend anything.
- Do not widen `targets`, `stage` or `code_types` beyond what the user asked for.
- Never add a brake target the user has not named and approved, and never brake anything on the protected list.
- Do not delete `govern.stop` unless the user tells you to.
