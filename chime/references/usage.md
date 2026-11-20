# The low-usage alarm and its mute

## What it does

At the end of every turn of a session (any kind of turn), the Stop hook reads that account's usage. When any limit is at or above `usage_alert_pct` (default 90), it plays `low_health` first, ahead of the turn's own sounds, with a toast naming the account and the limit ("ALPHA weekly limit at 97%"). At most once per `usage_alert_every_min` (default 30) per account, so a busy afternoon near the limit does not repeat it every turn. The session does not name it on the Sound line; the toast says it.

It watches every limit the reading reports: the 5-hour limit, the weekly limit, each per-model weekly limit, and the monthly extra-usage spend.

## It needs a usage reader you name

chime does not know how to read usage by itself. Set the config key `usage_server` to the path of a Python file that offers either `fetch_raw()` (returns the usage payload as a dict with `five_hour` and `seven_day` objects holding `utilization` and `resets_at`, an optional `limits` list with `percent`, `scope.model.display_name` and optionally `resets_at`, and an optional `extra_usage` object with `is_enabled` and `utilization`) or `fetch_usage(refresh=True)` (returns `session_pct`, `weekly_pct` and `model_breakdowns`). With no `usage_server` there is no alarm. chime imports that file and runs it, so set it only to code you wrote or trust. The account is the one named by the environment variable `CLAUDE_CONFIG_DIR` of the session; the reader is expected to use that account's own credentials, which chime never reads itself.

A reading is cached for five minutes per account, in `%TEMP%/chime`. The cache also keeps each limit's reset time and the account folder, so `usage mute` can find the end of a cycle. A path written with backslashes and the same path with forward slashes find the same cache and the same played marker.

## The record

`<chime home>/usage_log.txt` gets one line per fresh reading at or above `usage_log_from_pct` (default 70, at most one per account per five minutes), one per failed or empty reading (at most one per account per 15 minutes) and one per alarm played: time, account name, decision, the values read. The file is cut back when it passes 60 KB. When an alarm seems to be missing, read this file first. The alarm runs only at the end of a turn of a session on that account, so an account with no session ending a turn is never checked.

## A muted turn does not use the alarm up

While chime is muted (the mute file, a Zoom meeting, clocked out) the alarm stays unspent and sounds, with its toast, at the end of the first turn after the mute lifts.

## Muting one account's alarm

```
chime.py usage status [--json]
chime.py usage mute <ACCOUNT> [--cycle | --until "YYYY-MM-DD HH:MM"] [--by SEAT] [--why "text"]
chime.py usage unmute <ACCOUNT> [--by SEAT]
```

- `<ACCOUNT>` is a name from the config's `account_names`, the account's folder name, or `this`. `account_names` maps an account home's folder name to a short name for toasts, for example `{"work": "WORK", "home": "HOME"}`. With none configured, `this` and the folder name work.
- `--cycle` (the default) lasts until the reset of the cycle that is over the alert line, read from the cache. When no reset time is known it lasts 24 hours and says so (`until_source: "fallback_24h"`). `--until` takes a local time in the future.
- A mute silences only that account's alarm and toast. It does not touch other accounts, the global mute, the 30-minute rule or other sounds, and it ends by itself. The usage log notes a muted account that is at or above the line.
- The mutes are in `<chime home>/usage_mute.json`. An expired entry is ignored and removed at the next write.
- `usage status --json` is `{"alert_pct": 90, "accounts": [{"account", "home", "muted", "until", "until_source", "by", "why", "set_at", "last_reading": {"at", "values": [{"limit", "pct", "resets_at"}]} | null, "marker_quiet_until"?}]}`. Every account in `account_names` is listed (or just this one when none are configured).
