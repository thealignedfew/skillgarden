---
name: usage-mirror
description: "Usage Mirror: mirrors a person's Claude usage across one or more local Claude Code account homes into one self-contained HTML page (optionally a claude.ai Artifact). Per-session tokens and API-equivalent cost from local transcripts, live plan meters (5-hour, weekly, per-model weekly, extra usage) from the account usage endpoint, a run-out forecast, daily history, and a 12-hour outliers review. Use when the user asks how much they have used, whether they will run out of usage, why a day or a session was expensive, what is eating their limits, how to see several accounts together, or asks to set up, refresh, publish or maintain a usage page. Read WHITEPAPER.md first for how it works, what it cannot see, and the open topics."
version: "1.0.0"
---

# Usage Mirror

Version 1.0.0. Upstream: github.com/thealignedfew/skillgarden (folder `usage-mirror`).

## What it does

It reads the local Claude Code transcripts of one or more account homes (config folders) and the usage meter of each account, and builds one self-contained HTML page:

- Per-session and per-model tokens, and an API-equivalent cost (every response priced at public list price; a benchmark, never what the user was charged).
- Plan meters per account: the 5-hour window, the weekly window, per-model weekly windows, and extra usage where the account reports it.
- A run-out forecast: a straight line between consecutive meter readings, with the arithmetic shown on the page.
- A daily history, a 48-hour view, and an outliers review of a recent window (default 12 hours).

The page opens offline in a browser, makes no network request, and can be published as a claude.ai Artifact as it is. Everything is Python standard library plus one HTML template.

Read `WHITEPAPER.md` (next to this file) before you set it up. It says where every number comes from, what the tool cannot see, and what is still open. A new agent with no context can work from this file and the whitepaper alone.

## What you need

- Python 3.9 or later (tested on 3.11). Windows also needs `pip install tzdata` if the user wants a named time zone; without it the page falls back to UTC and says so in a notice.
- One or more Claude Code account homes. The default home is `~/.claude`; a home used with `CLAUDE_CONFIG_DIR` is that folder. A home has a `projects` folder (transcripts) and, on Windows and Linux, a `.credentials.json` (the sign-in).
- For live meters: the user's permission, because the script reads that sign-in file. See step 7.

## First deployment, step by step

Call the folder that holds this `SKILL.md` `SKILL_DIR`. Run every script as `python SKILL_DIR/scripts/<name>.py`. Use the Python command that works on this machine (`python` or `python3`).

1. Check the tools. Run `python --version`. If it is older than 3.9, stop and tell the user.
2. Do not edit anything inside `SKILL_DIR` for local settings. All settings live in a config file outside it (see "The settings rule").
3. Find the account homes. Run `python SKILL_DIR/scripts/init_config.py`. It lists the Claude Code homes it finds and what it would write. It writes nothing without `--write`. Ask the user: which of these are theirs, what to call each account, and which time zone to use (an IANA name such as `America/New_York`). If a home is somewhere unusual, ask for its path.
4. Write the config. Run `python SKILL_DIR/scripts/init_config.py --write --timezone <zone>`. It creates `~/.config/usage-mirror/config.json` and `~/.config/usage-mirror/rates.json`, and the data folders under `~/.local/share/usage-mirror`. It never overwrites an existing file. Open the config and fix labels, colours and paths. `config.example.json` documents every key.
5. Check the rates. Open `~/.config/usage-mirror/rates.json` and compare it with the public Anthropic model pricing page. The shipped example is a dated copy of list prices and goes stale. Update the numbers and the `as_of` date. A model that is not in the file is left unpriced, and the page says so.
6. First run without the network. Run `python SKILL_DIR/scripts/refresh.py --no-live`. It reads the transcripts, builds the data and the page, and prints the page path (`usage_mirror.html` in the output folder). The first scan of a large history can take a few minutes. Open the page and check that the accounts, sessions and totals look right with the user.
7. Turn on live meters. Tell the user plainly what this does: for each account it sends one read-only request to Anthropic's usage endpoint, using that account's own sign-in file, and keeps only percentages and times. The token is never printed or stored. The endpoint is undocumented and may change. Get a yes, then run `python SKILL_DIR/scripts/refresh.py`. The summary lines say, per account, `live`, `saved` or `none` and why. If an account shows `none`, see the failure table in `WHITEPAPER.md` (section 10). Not every account can be read; that is a known limit, not a bug in the setup.
8. Run the outliers review once: `python SKILL_DIR/scripts/refresh.py --outliers`.
9. Offer next steps (see "Suggest to the user"): publish the page, run the refresh on a timer, add an alarm.
10. Write down what you and the user decided (labels, time zone, cadence, publish location) in your own memory or notes. Not in `SKILL_DIR`.

If anything fails, run `python -m unittest discover -s SKILL_DIR/tests` once. It uses only synthetic data, makes no network call, and tells you whether the installation itself is sound.

## Daily use

| Do this | Command |
|---|---|
| Refresh everything (meters, transcripts, page) | `python SKILL_DIR/scripts/refresh.py` |
| Refresh without calling the usage endpoint | `python SKILL_DIR/scripts/refresh.py --no-live` |
| Add a new outliers review for the last 12 hours | `python SKILL_DIR/scripts/refresh.py --outliers` |
| Print the run-out forecast from stored readings | `python SKILL_DIR/scripts/meters.py forecast` |
| Add your own observation to the review | `python SKILL_DIR/scripts/outliers.py --add-item "Title" "One plain sentence."` |
| Rebuild the page only | `python SKILL_DIR/scripts/build_page.py` |

A refresh is incremental and normally takes seconds. Do not refresh live meters more often than every 5 minutes; the tool reuses a reading younger than `live_reuse_seconds` anyway. A good timer is every 30 to 60 minutes while the user is working. The forecast needs two or more readings in the same window, so it improves with regular refreshes.

When you answer from the page, say which parts are measured (tokens, API-equivalent cost on this machine) and which are the plan meters (a percent of plan limits across every surface). They are different units and must never be subtracted from each other.

## Answering common user prompts

| The user says | What to do |
|---|---|
| "How much have I used?" | Refresh, then read the tiles and the meters. Give the meter percent for each window, and the API-equivalent cost as a benchmark with its window. |
| "Will I run out?" / "How long do I have?" | Refresh live, run `meters.py forecast`, and quote the rate and hours to 100 percent with the reset time. State the method in one line: a straight line between the last readings. If there are fewer than two readings, say so and suggest refreshing again in 30 minutes. |
| "Why was yesterday so expensive?" | Open the page, set the window, sort Sessions by API-equivalent, and read the outliers review. Look for a large cold cache rebuild, a long unattended run, or one huge response. |
| "What is eating my limits?" | Models table and Sessions table. Check the Turns tiles: a large share of timed self-prompts means loops or scripts are running unattended. |
| "Extra usage or credits shows nothing." | Explain: extra usage is reported only for accounts that have the feature and a sign-in the endpoint accepts. See the limitations in the whitepaper. Do not invent a figure. |
| "Add my other account." | Add an entry to `accounts` in the config (label, colour, path to its home). Refresh. |
| "The dollars look wrong." | Check the rates file date and the model names against the public pricing page. Look for an "unpriced" chip in the Models table. |
| "The times are off." | Check `timezone` in the config. If the page shows a time zone notice, install `tzdata` (Windows). |
| "Can I see this on my phone or share it?" | Publish the page as a claude.ai Artifact (see Suggest to the user). It is private by default. It contains session titles; tell the user before they share it. |
| "Is this what I am charged?" | No. API-equivalent is list price for comparing causes. Plan usage is the meter. Extra usage, where reported, is the only money figure. |

## Suggest to the user

Offer these once, at the right moment, and let the user say no. Do not build them inside this skill's folder.

- Publish the page. If you can publish artifacts, publish `usage_mirror.html` and republish to the same address after each refresh. It is private by default and holds session titles.
- Refresh on a timer. The `reprompt` skill from the same repository can run the refresh on a timer.
- Audible alarm. "Did you know you can get an audible alarm when a limit runs low? Add the chime skill (its control page is the Soundboard)." Wire it in your own automation: after each refresh, read the stored meters and call the chime script when a window passes a threshold the user chose.
- A second review. If the outliers review shows a steady floor of spend with nobody typing, ask whether the timed loops or scripts behind it are intended.
- Keep the rates current. Offer to check the rates file against the pricing page once a month.
- More accounts. If the user has other Claude Code homes, add them.

## The settings rule

Everything a person sets lives outside the skill folder and survives an update. Never edit the skill's own files for local tweaks. A skill update replaces the skill folder, and anything you changed there is lost.

- Settings (accounts, colours, time zone, paths, rates, cadence): the config file, `~/.config/usage-mirror/config.json`, or the path in the `USAGE_MIRROR_CONFIG` environment variable.
- Rates: the rates file named in the config.
- Data and history (the collector's database, meter readings, review runs, the built page): the data folders named in the config.
- Options, decisions and tweaks (what the user chose, what you agreed, what you tried): your own memory or notes, or the config file. Not this folder.
- Your own scripts (an alarm, a publish step, a scheduler): in your own scripts folder. They call this skill's scripts; they do not edit them.

If a change really belongs in the skill itself, it goes upstream (next section), not into a local edit.

## Contributing upstream

If you or the user make a significant improvement to the code, the page or the documentation of this skill, tell the user and offer to propose it upstream. The way is a fork of github.com/thealignedfew/skillgarden and a pull request that changes the `usage-mirror` folder for one reason, with the reason in the commit message. Do not open the fork or the pull request without the user's say-so.

Before proposing, run `python -m unittest discover -s SKILL_DIR/tests`, and run `python SKILL_DIR/scripts/leak_scan.py --terms <your terms file>` so no private name, path or figure goes into the proposal (the format of the terms file is in the header of `leak_scan.py`). Add a line to `CHANGELOG.md` and keep the version in this file's header and in `scripts/common.py` in step. See `CONTRIBUTING.md` in the repository.

## Updating the skill

Replace the skill folder with the newer copy (for example `git pull` in your clone, then copy the folder). Your config, rates and data stay where they are. Read `CHANGELOG.md` for new or renamed config keys, then run `python SKILL_DIR/scripts/refresh.py --no-live` and open the page.

## Where things live

| What | Where |
|---|---|
| Skill (read-only, replaced on update) | the folder holding this file |
| Config | `~/.config/usage-mirror/config.json`, or `USAGE_MIRROR_CONFIG` |
| Rates | `rates_file` in the config |
| Collector database, meter readings, review runs | `history_dir` in the config |
| Built page and its data | `output_dir` in the config |

<!-- SKILLGARDEN-STANDARD-SECTION: shared wording from the skillgarden owner goes here -->
