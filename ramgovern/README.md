# ramgovern

A Working Set Governor for Windows machines that run many Claude Code sessions at once.

Each Claude Code session is a `claude.exe` process that holds a few hundred MB of RAM even while it sits idle, waiting for its next prompt. VS Code adds an extension host per window. Run dozens of sessions and idle processes fill physical memory, the machine starts paging, and the window you are actually using lags.

ramgovern pages idle sessions out of RAM on a schedule. It never kills, suspends or restarts anything. A trimmed process keeps running and pulls its pages back the moment it needs them.

Not affiliated with Anthropic or Microsoft. "Claude Code", "VS Code" and "Windows" are named only to say what this works with.

## How it works

A **trim** is one Win32 call, `EmptyWorkingSet` (psapi), on one process. Windows moves that process's resident pages to the standby list, then to the compressed store, then to the pagefile. Nothing is lost and there is nothing to undo: the process faults pages back in on demand.

A trim on its own does not last, because idle sessions regrow within the hour as they wake for their own work. So `govern.ps1` runs on a scheduled task every 5 minutes and trims whatever is idle at that moment:

1. **Collect candidates.** At stage 1 that is every `claude.exe`. At stage 2 it also includes VS Code's extension-host processes (`Code.exe --type=utility --utility-sub-type=node.mojom.NodeService`).
2. **Run the idle test.** A candidate must use under 0.05 CPU-seconds across `idle_seconds` (default 10). It must also not have grown more than `recent_cpu_seconds` since the previous run. A VS Code host must have been quiet for `code_idle_runs` x `cadence_minutes`.
3. **Apply the guards.** These are never trimmed:
   - the foreground window's process;
   - any process on the Governor's own ancestor chain;
   - names in `exclusions`;
   - processes younger than the minimum age;
   - VS Code's main process, renderers, GPU, network-service and crashpad processes, whatever the settings say;
   - a VS Code host that is the direct parent of a live `claude.exe` or `codex.exe`. That host carries an AI coding extension, and trimming it just before its sessions wake makes it fault its whole heap back at once.
4. **Trim, then watch for 30 seconds.** The run records resident memory and free RAM before, at 2 s and at 30 s, and the system page-in rate.
5. **Halt on a storm.** If a trimmed process climbs above `storm_threshold_pct` of one CPU core over 10 s within those 30 s, that is a page-in storm. The Governor writes `govern.stop` and every later run exits at once until a person reads and deletes that file. A trim that makes something thrash should stop the tool, not repeat every 5 minutes.

Every run writes one line to `govern.log`. Once an hour the scheduled run also writes `summary-YYYYMMDD.md`: runs, MB released, regrow between runs, storms, failures and a VS Code renderer watch.

### Optional: trim right after an unattended turn

If you run sessions unattended on a timer (a scheduler re-prompts each session every N minutes), the best moment to page a session out is right after its own scheduled turn ends. `govern_posttick.py` is a Claude Code **Stop hook** for that. Your scheduler writes `<posttick_state_dir>\<session_id>.json` with `{"last_tick": "<local ISO time>", "stopped": false}` whenever a scheduled turn starts. When the hook sees a Stop event within `posttick_window_seconds` of that tick, it spawns `govern.ps1 -Mode self` detached against its own session's `claude.exe` and exits within 200 ms. Without those files the hook does nothing. Skip it if you have no unattended sessions; the scheduled task does the main work.

## Requirements

- Windows 10 or 11, Windows PowerShell 5.1 (built in). No admin rights: a user can trim their own processes.
- Python 3.8+ only for the optional Stop hook and its test.
- A pagefile. Trimmed pages go to the pagefile, so a machine with the pagefile disabled gains little.

## Install

1. Copy this folder anywhere, for example `C:\Tools\ramgovern\`. Everything finds its files relative to `govern.ps1`, and `govern.json`, the log, the state file and the summaries live beside it.
2. Look before you trim. This lists what would be released and changes nothing:
   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\wstrim_probe.ps1
   powershell -NoProfile -ExecutionPolicy Bypass -File .\govern.ps1 -Mode task -List
   ```
3. Run the self-check. It uses a temp copy of the settings with `enabled: false`, so it never trims, and takes a few minutes (longer on a machine that is short of memory):
   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\govern_selfcheck.ps1
   ```
4. Register the scheduled task (once, as the user whose sessions should be trimmed):
   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\register_task.ps1
   ```
   The task runs every 5 minutes but trims nothing while `govern.json` has `"enabled": false`. Each run writes a `DRY` line instead. Read a few of those first.
5. Turn it on: set `"enabled": true` in `govern.json`. The file is re-read every run, so there is nothing to restart.
6. Optional, stage 2: set `"stage": 2` to include idle VS Code extension hosts. Watch the log for a day at stage 1 first.
7. Optional, the Stop hook: add it to the `Stop` hooks in your Claude Code `settings.json`, with `async` so it never delays a turn:
   ```json
   { "hooks": [ { "type": "command", "command": "python", "args": ["-I", "C:/Tools/ramgovern/govern_posttick.py"], "timeout": 5, "async": true } ] }
   ```
   Run `python govern_posttick_test.py` first. It uses a temp folder and trims nothing. Run from a Claude Code session, its first case also proves the hook finds its own `claude.exe`; from a plain terminal that case checks the "no claude.exe ancestor" path instead.

8. Optional, the slash command: copy `SKILL.md` into a `ramgovern` folder in your Claude Code skills directory to get `/ramgovern status | on | off | pid <n>`.

## Settings (`govern.json`)

The engine ignores keys it does not know. The table shows the shipped values. If a key is missing from the file the engine falls back to a cautious value: `enabled` false, `stage` 1, `targets` `["claude"]`, `exclusions` `["Code","explorer","dwm"]`; the others fall back to the values shown.

| Key | Shipped | What it does |
|---|---|---|
| `enabled` | `false` | Master switch. Off: every run only looks and writes a DRY line. On: idle processes are trimmed. |
| `stage` | `1` | 1 = `claude.exe` only. 2 = also VS Code extension hosts (limited by `code_types`). |
| `targets` | `["claude","Code"]` | Process names (no `.exe`) the Governor may trim; the stage filters this list. |
| `code_types` | `["utility:NodeService"]` | Which VS Code process kinds may be trimmed. This list can only narrow; no other kind is ever trimmed. |
| `code_idle_runs` | `2` | Runs a VS Code host must stay quiet before it counts as idle (2 x 5 min = 10 minutes). |
| `code_min_age_minutes` | `10` | A VS Code process younger than this is never trimmed, so a new window's extension host can finish loading. 0 = off. |
| `claude_min_age_minutes` | `2` | The same for `claude.exe`. 0 = off. |
| `idle_seconds` | `10` | Seconds of near-zero CPU that make a process idle (5 to 300). |
| `foreground_guard` | `true` | Never trim the foreground window's process, or a process that used CPU since the last run. Off is for testing only. |
| `recent_cpu_seconds` | `0.5` | CPU time since the previous run above which a process counts as active and is skipped. |
| `cadence_minutes` | `5` | How often the task runs. Changing this does not re-register the task; the log notes a MISMATCH until the trigger matches. |
| `exclusions` | `["explorer","dwm"]` | Names never trimmed, whatever the stage. |
| `storm_threshold_pct` | `50` | Share of one CPU core, over 10 s within 30 s of a trim, that counts as a page-in storm (10 to 100). |
| `storm_action` | `"stop"` | `stop`: write `govern.stop` and halt until a person deletes it. `log`: record the storm and carry on. |
| `summary_hour_interval` | `1` | Hours between rolling daily summaries; the first run after 00:05 also finalizes the previous day. 0 = off. |
| `task_lock_wait_seconds` | `90` | How long a scheduled run waits for a post-turn run to release the run lock before giving up its slot (0 to 280). |
| `task_name` | `"ramgovern"` | Scheduled task name, used for the cadence check. If you register the task under another name (`register_task.ps1 -TaskName`), set it here too. |
| `log_path` | `""` | Log file; empty = `govern.log` beside `govern.json`. |
| `pagesin_sentinel_pattern` | `""` | Optional path pattern to an external monitor's JSON-lines samples (fields `t` and `pagesIn`), e.g. `C:\Monitor\samples-{0:yyyyMMdd}.jsonl`. It is quoted in storm lines. |
| `posttick_window_seconds` | `120` | Stop hook only: a turn end counts as "just after a tick" within this many seconds of `last_tick`. |
| `posttick_state_dir` | `""` | Stop hook only: folder with the per-session tick files; empty = a `ticks` folder beside `govern.json`. |

## Reading the log

One line per run, stamped in local time with the UTC offset:

```
2026-01-15 09:30:42 +01:00 stage2 task APPLY: 41 idle of 96 claude,Code; resident 6210 -> 940 (2s) -> 1480 (30s) MB;
  free 2100 -> 7300 -> 6800 MB; cpu-within-30s 3 of 41; storm none; failed 0; 180 ms; regrow-since-last ...;
  skipped fg 1 recent 22 busy 18 own 0 quiet 4 young 2 claudehost 9; ...; pagesin-max 4200/s; steps-ms ...
```

(The sample is wrapped here; in the log it is one line.) Other kinds: `START` (a task run began, with its launch delay and lock wait), `DRY` (not enabled, or no `-Apply`), `SKIP` (run lock busy), `SKIPPED` / `REFUSED` (a single-process run that did not trim, and why), `ERROR`. A `START` with no matching `APPLY` or `DRY` means a run stalled or was killed.

The scheduled task runs PowerShell under `conhost.exe --headless` so no window flashes every 5 minutes. As a side effect, Task Scheduler's Last Result always reads 0. Judge runs by the log.

## Engine modes and exit codes

```
govern.ps1 -Mode task [-Apply] [-List]        sweep everything (the scheduled task)
govern.ps1 -Mode seat -TargetPid N [-Apply]   one process, full idle test
govern.ps1 -Mode self -TargetPid N [-Apply]   one claude.exe, no idle test (the Stop hook's call)
govern.ps1 -ListCode                          show how every Code.exe is classified, then exit (read-only)
```

Exit codes: 0 ok, 1 error, 2 storm halted the run, 3 `govern.stop` present, 4 run lock busy, 5 bad arguments, 6 refused (wrong kind of process), 7 single-process run skipped its target.

## Files

| File | What |
|---|---|
| `govern.ps1` | The engine. |
| `govern.json` | Settings. Ships with `enabled: false`. |
| `govern_summary.ps1` | Daily summary writer; the engine calls it. |
| `register_task.ps1` | Registers the scheduled task for the current user. |
| `govern_selfcheck.ps1` | 16-case self-check of the engine, dry runs only. Run it after any engine edit. |
| `govern_posttick.py` | Optional Claude Code Stop hook: trims a session right after its own unattended turn. |
| `govern_posttick_test.py` | Test of the Stop hook, temp folder only. |
| `wstrim_probe.ps1` | Stand-alone probe: what would one trim release right now? |
| `SKILL.md` | Claude Code skill: `/ramgovern status | on | off | pid <n>`. |

Created at run time beside `govern.json`: `govern.log`, `govern.state.json` (CPU baselines between runs), `posttick.state.json`, `summary-YYYYMMDD.md`, and `govern.stop` after a storm. The probe writes `wstrim_probe.log` beside itself when run with `-Apply`.

## Uninstall

```powershell
Unregister-ScheduledTask -TaskName ramgovern -Confirm:$false   # or your task_name
```

Then remove the Stop hook entry if you added one, and delete the folder. Trimmed processes need nothing: they regrow on their own.

## Limits and honest caveats

- A trim frees RAM but does not reduce **commit**. A machine that is short on commit (the pagefile limit) needs a larger pagefile or fewer processes, not trimming.
- Trimming costs page-ins later. If a trimmed process wakes, it reads its pages back from the pagefile, which is slower than RAM and slowest on a spinning disk. The idle test, the quiet history for VS Code hosts and the storm halt keep that cost small. Watch `cpu-within-30s` and the daily regrow table.
- The idle test sees CPU only. A process that is idle on CPU but about to be used (for example, a window you are about to click into) can be trimmed; it pages back in on first use.
- Windows only. The approach would carry to other process names, but the guards are written around `claude.exe`, `codex.exe` and VS Code's process model.

## Licence

MIT. See [LICENSE](LICENSE).

## Field study

[FIELD_STUDY.md](FIELD_STUDY.md) reports eight days of use on one workstation running about a hundred sessions (first draft).
