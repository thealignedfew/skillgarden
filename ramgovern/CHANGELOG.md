# Changelog

## 0.2.1

- New: a one-page dashboard (`scripts/build_dashboard.py`). Free RAM now, lowest free RAM today, struggling share of the last hour, trims and brakes today, a day-by-hour heat grid, the suggester's table and a Method tab. Needs the `stagecraft` skill from the same repository; without it the script stops with a message and writes nothing.
- Fix: a program that was already slowed when the brake started (for example after the brake was restarted) is now put back to every processor and normal priority on release, instead of staying slowed.
- 31 tests (10 new, for the dashboard).
- The trim engine, the sampler, the suggester and the drive check are unchanged.

## 0.2.0

New, all optional and off until you set them up. The trim engine (`govern.ps1`, `govern.json`) is unchanged from 0.1.0.

- The brake (`scripts/brake.ps1`): slows the background programs you list while you are at the machine, then puts each back as it found it. Never stops, suspends or kills. Ships with no targets and a protected list it will not touch. A target can be braked only while the machine is struggling (`"trigger": "stress"`).
- The sampler (`scripts/sampler.ps1`): one read-only line every 15 seconds, for the suggester.
- The suggester (`scripts/brake_suggest.py`): names programs that were often among the five busiest while the machine struggled. A suggestion is a question for you.
- The drive check (`scripts/disk_health.py`): free space, saturated drives, writes against the maker's rating, drive errors. Settings are optional (`assets/drives.example.json`).
- `scripts/register_brake.ps1`: registers the brake and sampler as logon tasks, with `-DryRun` to look first.
- 21 tests (`tests/`), on made-up data.
- Settings and data for the new parts live in the ramgovern home (`RAMGOVERN_HOME`, else the folder holding `govern.json`, else `.threadops\ramgovern` in your profile).

Not in 0.2.0, planned: engine changes that let a storm halt end by itself, skip trimming when RAM is plentiful and cover Chrome renderers (0.3.0).

## 0.1.0

First release: the trim engine, its settings, the scheduled task, a self-check, the optional Stop hook, the daily summary and a field study.
