# ramgovern

A Working Set Governor for Windows machines that run many Claude Code sessions at once.

Each Claude Code session is a `claude.exe` process that holds a few hundred MB of RAM even while it sits idle, waiting for its next prompt. VS Code adds an extension host per window. Run dozens of sessions and idle processes fill physical memory, the machine starts paging, and the window you are actually using lags.

ramgovern pages idle sessions out of RAM on a schedule. It never kills, suspends or restarts anything. A trimmed process keeps running and pulls its pages back the moment it needs them.

Not affiliated with Anthropic or Microsoft. "Claude Code", "VS Code" and "Windows" are named only to say what this works with.

Version 0.2.1. New in 0.2.0: an optional brake that slows background programs you name, a read-only sampler, a suggester that names programs worth braking, and a drive check. New in 0.2.1: a one-page dashboard, and the brake now puts back a program that was already slowed when it started. The trim engine is unchanged from 0.1.0. See [CHANGELOG.md](CHANGELOG.md).

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

## The brake and the drive check (0.2.0, optional)

Two more parts, both off until you set them up. Neither stops, suspends or kills anything.

**The brake.** While you are at the machine, it slows the background programs you list: fewer processor threads, below-normal priority, and low memory and disk priority. When you have been away for ten minutes each one gets back the affinity and priority it had before. It exists for programs that other programs start behind your back and that take most of the machine for minutes at a time (a scheduled spreadsheet refresh, an emulator, a sync client). It ships with no targets, so until you add one it only writes the memory and drive lines described below.

1. Check the sampler, which writes one read-only line every 15 seconds (free RAM, commit charge, total processor use, the application in front, the five busiest processes). One run, one line:
   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\sampler.ps1 -Once
   ```
   `register_brake.ps1` (step 4 below) runs it all day.
2. After a day or two, ask which programs are worth a brake:
   ```
   python scripts\brake_suggest.py --days 7
   ```
   It counts how often each program was among the five busiest, at half a core or more, while the machine was struggling (free RAM under 500 MB, commit over 95 percent, or processor use over 90 percent; change them with `--free-mb`, `--commit-pct`, `--cpu-pct`). A program that is often in front of you is your own work and is never suggested, and neither is anything on the protected list or already a target. A suggestion is a question for you, not an order.
3. Add a target only after you have seen it cause trouble. Copy `assets/brake.example.json` as `brake.json` in the ramgovern home and set `name` (the process name without `.exe`), a `match` that keeps your own copies out (a regex over the command line; empty means every copy), `enabled`, who approved it and why. The running brake re-reads the file within one interval and logs a `CONFIG loaded` line. A target with `"trigger": "stress"` is braked only while the machine is already struggling, whether or not you are there.
4. Register the two tasks, once, by hand. Look first:
   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\register_brake.ps1 -DryRun
   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\register_brake.ps1
   ```
   They run as you, without elevation, one copy each, started at logon.

The brake refuses a protected list even if `brake.json` names one: Windows itself, `claude`, `Code`, explorer, dwm, the Defender engine, PowerShell, conhost, Zoom, Chrome and Edge. The suggester also leaves out `python` and `node`, because slowing them slows your agents. Undo a target by setting its `enabled` to false; undo the brake with `Unregister-ScheduledTask -TaskName ramgovern-brake -Confirm:$false` and by ending its PowerShell process.

**The drive check.** Reads the brake's once-a-minute lines and says, in plain lines, whether a drive is short of room, saturated, or being written faster than its rating allows over five years, and lists drive errors from the last day:
```
python scripts\disk_health.py
```
It works without any settings. Copy `assets/drives.example.json` as `drives.json` to name your SSDs and give each disk's rated terabytes written; without that the endurance line is skipped and says so. It also reads the drives' own wear and temperature counters where Windows lets an ordinary user read them.

**Where the new parts keep their files.** In the ramgovern home: the folder named by the environment variable `RAMGOVERN_HOME`, or else the folder holding `govern.json` (the script's folder or the one above it), or else `.threadops\ramgovern` in your user profile. That is `brake.json`, `drives.json`, `govern.log`, `samples-YYYYMMDD.jsonl` and `procmem-YYYYMMDD.jsonl`.

**Tests.** `python -m unittest discover -s tests` runs 31 tests on made-up samples, drives and dashboard data. They touch no process and no setting.

**The dashboard (0.2.1, optional).** One page of free RAM now, the lowest free RAM today, how much of the last hour the machine struggled, trims and brakes today, a day-by-hour heat grid of when it struggled, and a table of programs the suggester would ask you about. It reads the sampler's lines, `govern.log` and `brake.json`, and a Method tab explains how every figure was worked out. It needs the `stagecraft` skill from the same repository installed; without it the script stops with a message and writes nothing.
```
python scripts\build_dashboard.py
```
The page is written to `dashboard\ramgovern-dashboard.html` in the ramgovern home; `--out`, `--days` and the limits that count as "struggling" (`--free-mb`, `--commit-pct`, `--cpu-pct`, `--late-pct`) can be changed. It is a capture, rebuilt whenever you run the script.

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
| `scripts/brake.ps1` | The brake. Slows listed background programs while you are at the machine; writes a memory and drive line a minute. |
| `scripts/sampler.ps1` | Read-only sampler: one line every 15 seconds for the suggester. |
| `scripts/brake_suggest.py` | Names programs worth a brake, from the sampler's lines. |
| `scripts/disk_health.py` | Drive check: free space, saturation, write endurance, drive errors. |
| `scripts/build_dashboard.py` | Builds the one-page dashboard (needs the `stagecraft` skill). |
| `scripts/register_brake.ps1` | Registers the brake and sampler tasks. `-DryRun` shows them first. |
| `assets/brake.example.json`, `assets/drives.example.json` | Example settings to copy into the ramgovern home. |
| `tests/` | 31 tests of the suggester, the drive check and the dashboard, on made-up data. |
| `SKILL.md` | Claude Code skill: `/ramgovern status | on | off | pid <n> | brake | drives`. |

Created at run time beside `govern.json`: `govern.log`, `govern.state.json` (CPU baselines between runs), `posttick.state.json`, `summary-YYYYMMDD.md`, and `govern.stop` after a storm. The probe writes `wstrim_probe.log` beside itself when run with `-Apply`.

## Uninstall

```powershell
Unregister-ScheduledTask -TaskName ramgovern -Confirm:$false   # or your task_name
Unregister-ScheduledTask -TaskName ramgovern-brake -Confirm:$false     # if you registered the brake
Unregister-ScheduledTask -TaskName ramgovern-sampler -Confirm:$false   # and the sampler
```

Then remove the Stop hook entry if you added one, and delete the folder. Trimmed processes need nothing: they regrow on their own.

## Limits and honest caveats

- The brake slows a program; it does not make a machine that is too small big enough. A program waiting on a slowed helper takes longer to finish, so check that a target is not something you are waiting on.

- A trim frees RAM but does not reduce **commit**. A machine that is short on commit (the pagefile limit) needs a larger pagefile or fewer processes, not trimming.
- Trimming costs page-ins later. If a trimmed process wakes, it reads its pages back from the pagefile, which is slower than RAM and slowest on a spinning disk. The idle test, the quiet history for VS Code hosts and the storm halt keep that cost small. Watch `cpu-within-30s` and the daily regrow table.
- The idle test sees CPU only. A process that is idle on CPU but about to be used (for example, a window you are about to click into) can be trimmed; it pages back in on first use.
- Windows only. The approach would carry to other process names, but the guards are written around `claude.exe`, `codex.exe` and VS Code's process model.

## Licence

MIT. See [LICENSE](LICENSE).

## Field study

[FIELD_STUDY.md](FIELD_STUDY.md) reports eight days of use on one workstation running about a hundred sessions (first draft).
