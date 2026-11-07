---
name: ramgovern
description: "ramgovern: control a Windows machine's Working Set Governor, which pages idle Claude Code sessions (claude.exe) and idle VS Code extension hosts out of RAM so many sessions can run side by side. /ramgovern status shows whether it is on and what it last did; /ramgovern on turns trimming on; /ramgovern off turns it off; /ramgovern pid <n> trims one process now. Use when the user types /ramgovern, or says 'ramgovern', 'Governor', 'working set', 'trim the idle sessions', 'page out idle sessions', 'free up RAM from idle Claude sessions' or 'turn the Governor on or off'."
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

## Hard limits

- Never trim VS Code's main process, its renderers, explorer.exe, dwm.exe, or the foreground process. Never kill or suspend anything.
- Do not widen `targets`, `stage` or `code_types` beyond what the user asked for.
- Do not delete `govern.stop` unless the user tells you to.
