# headroom

**Moving from usage-mirror?** This skill was called usage-mirror up to 1.0.0 and is now headroom. If you cloned or copied the old `usage-mirror` folder, install `headroom` in its place and remove the old folder. Your settings move to `~/.threadops/headroom/config.json`; until you move them, the old config (`USAGE_MIRROR_CONFIG` or `~/.config/usage-mirror/config.json`) is still read as an alias, with a one-line notice. See `CHANGELOG.md`.

A Claude Code skill that shows how much headroom is left in your Claude usage. It mirrors your usage, across one or more local account homes, into one self-contained HTML page. Per-session tokens and API-equivalent cost from your local transcripts, live plan meters from the account usage endpoint, a run-out forecast, a daily history, and a short review of what stood out in the last 12 hours.

It is for people who run Claude Code a lot, sometimes under more than one account, and want one place to see where the usage went and how close they are to the limits.

## What you get

- Totals for any window: API-equivalent cost, fresh input, cache read, output, responses, turns (typed, timed self-prompts, from others) and active sessions.
- Plan meters per account: the 5-hour window, the weekly window, per-model weekly windows, and extra usage where the account reports it.
- A run-out forecast under each meter, with the arithmetic shown, and a warning that uses an icon and words when the limit would arrive before the reset.
- Daily and hourly history, by account.
- An outliers review: how the last 12 hours compare with the usual, what ran unattended, which sessions led, how many cold cache rebuilds there were. An agent can add its own observations.
- Models and sessions tables you can sort and filter.
- One HTML file. It opens offline, makes no network request, and can be published as a claude.ai Artifact as it is.
- A whitepaper for an agent with no context: how it was built, where every number comes from, what it cannot see, and what is still open.

## What it needs

- Python 3.9 or later. Standard library only. On Windows, `pip install tzdata` if you want a named time zone.
- One or more Claude Code account homes (`~/.claude`, or a folder you use with `CLAUDE_CONFIG_DIR`).
- For live meters, the account's sign-in file in its home. The tool reads it, sends one read-only request per account per refresh, and never prints or stores the token. On macOS the sign-in is usually in the keychain, which is not supported yet.

## Install

1. Copy the skill folder into your Claude Code skills directory:

   ```
   cp -r headroom ~/.claude/skills/headroom
   ```

   On Windows, copy it to `%USERPROFILE%\.claude\skills\headroom`.

2. Ask your agent to set it up ("set up headroom"). It follows `SKILL.md`. Or do it by hand:

   ```
   python ~/.claude/skills/headroom/scripts/init_config.py --write --timezone America/New_York
   python ~/.claude/skills/headroom/scripts/refresh.py --no-live
   ```

   Then open `headroom.html` in the output folder it prints. Check `~/.threadops/headroom/rates.json` against the public pricing page first: the shipped rates are a dated copy and go stale.

3. When you are happy, run `refresh.py` without `--no-live` to add the plan meters.

## Settings live outside the skill

The skill folder is replaced when you update it. So everything you set lives elsewhere, in your headroom home: `~/.threadops/headroom`, or the folder named by `HEADROOM_HOME`. It holds your config file (`config.json`), your rates file (`rates.json`) and your data folders (`history/`, `out/`), unless your config names other places. A household's own rules for the skill go in a small private skill named `headroom-house`. Do not edit the skill's own files for local tweaks. If you make an improvement worth sharing, propose it as a pull request from a fork; every pull request is reviewed and tested before any merge, and none is merged automatically. See `CONTRIBUTING.md` in the repository.

## Worked example

Synthetic output, to show the shape (the numbers are examples):

```
meters acct-a: live 5-hour 81% 7-day 41%
meters acct-b: none note: no_credentials
collect {"files_seen": 3, "files_read": 3, "records": 31, "bytes": 9120, "seconds": 0.1}
data sessions=2 rows=9
page ~/.threadops/headroom/out/headroom.html bytes=61874
```

```
$ python scripts/meters.py forecast
acct-a five_hour: runs_out_before_reset, 7.2 points an hour, 2.639 h to 100%
acct-a seven_day: runs_out_before_reset, 1.2 points an hour, 49.167 h to 100%
```

## Tests

```
python -m unittest discover -s tests -v
```

The tests use a synthetic fixture and make no network call. `scripts/leak_scan.py` checks a folder for private material before you push.

## More

- `SKILL.md`: the instructions an agent follows.
- `WHITEPAPER.md`: how it works, sources, limits, open topics.
- `CHANGELOG.md`: versions.

Licensed under the repository licence (Apache-2.0).
