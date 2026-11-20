# Headroom: how it works, what it cannot see, what is open

Version 1.1.0. Headroom was called usage-mirror up to 1.0.0. This document is written for an agent that has no context. Read it once, top to bottom, before you deploy the skill or answer a question about it. Section 12 is a list of things worth telling the user.

## 1. The problem

A person who runs Claude Code, often in several sessions and sometimes under several accounts, has three questions that no single screen answers:

1. What have all my sessions been doing, and what did it cost to run them, in tokens?
2. How close am I to my plan limits right now, and when will I hit them at this rate?
3. What stood out recently that I should know about?

The data to answer them is in two places. The transcripts that Claude Code writes on the local disk record every model response with its token counts. The account's own usage meter, read from Anthropic's usage endpoint, records how much of the plan's windows is used. This skill reads both, joins them on one page, and says plainly where each one stops being reliable.

## 2. How it was put together

The tool began as one person's private page for a fleet of long-running sessions and was grown in steps. The steps are the design, so they are listed here.

1. **Count from transcripts.** Claude Code writes one JSON line per record into `<home>/projects/**/*.jsonl`. An assistant record carries a `usage` block (input, cache write, cache read, output tokens), the model name, a message id and a timestamp. The collector keeps one row per message id, so a transcript that is copied (a resume, an account move) is counted once.
2. **Price at list price.** Each row is priced from a rates file of public list prices, per model, with cache writes at the one-hour and five-minute rates and cache reads at the read rate. The result is called API-equivalent. It is a yardstick for comparing sessions and days. It is never a bill.
3. **Classify turns.** A user record that is a typed prompt is a turn. The record's own origin keys say when it was not typed: a timed self-prompt, a message from another session, a background task result. Each response is attached to the turn that was running when it was made, so the page can drop, say, timed self-prompts and show what typed work cost.
4. **Add the meters.** Claude Code once kept a cached copy of the usage meter in its `.claude.json`. Around November 2026 the CLI stopped refreshing that copy, so the meters are now read live from the usage endpoint with each account's own sign-in. Every reading is kept (a percentage and a time), because a single reading says where you are and two readings say how fast you are moving.
5. **Forecast.** Between consecutive readings of one window the meter rose by some number of points over some number of hours. That gives a rate. Points left divided by the rate gives the hours to the limit. Section 6 has a worked example.
6. **Review outliers.** A script looks at a recent window (12 hours by default) and writes a few plain sentences: how the window compares with the usual one, what ran unattended, which sessions led, how many cold cache rebuilds there were. An agent can add its own observations. The page shows the newest review open.
7. **Generalise.** The private original knew its owner's folders, account names and session naming. This release replaces all of that with a config file outside the skill folder, and drops the parts that could not be generalised (section 11).

## 3. Architecture

```
account homes (read only)             usage endpoint (read only, optional)
  <home>/projects/**/*.jsonl            one request per account per refresh
            |                                   |
        collect.py                          meters.py
   history_dir/usage.sqlite         history_dir/meters_history.jsonl
            |                       history_dir/meters_live.json
            +------------+--------------------+
                         |
                  collect.build()  ---->  output_dir/usage_data.json
                         |
   outliers.py --> history_dir/insights.json
                         |
                    build_page.py  ---->  output_dir/headroom.html
```

| File | Job |
|---|---|
| `scripts/common.py` | config loading, time zone, rates, shared helpers, the version number |
| `scripts/collect.py` | scan transcripts incrementally into SQLite; build the aggregate the page uses |
| `scripts/meters.py` | read the usage endpoint, normalise it, keep history, compute the forecast |
| `scripts/outliers.py` | write the recent-window review |
| `scripts/build_page.py` | embed the data in `page_template.html` |
| `scripts/refresh.py` | run all of the above in order |
| `scripts/init_config.py` | first-run helper: find homes, write config and rates outside the skill |
| `scripts/leak_scan.py` | refuse to publish a folder that carries private material |
| `tests/` | synthetic fixture and tests; no network |

Nothing is written inside the skill folder and nothing is written into an account home.

## 4. Data sources

| Source | Where | What it gives | What it cannot give |
|---|---|---|---|
| Claude Code transcripts | `<home>/projects/**/*.jsonl`, every depth (subagent and workflow files included) | per response: time, model, token counts, working folder name, session id; per turn: time and origin; compaction markers; session title records | anything that did not run in Claude Code on this machine: claude.ai chat, desktop app chat, other machines, other tools. Message text is never read into storage |
| Usage endpoint | an Anthropic OAuth usage URL, called with the account's own sign-in | the plan meters: 5-hour and weekly windows with percent used and reset time, per-model weekly windows, the `limits` array, and, on accounts that have it, extra usage | history (it is a snapshot), any per-session breakdown, anything for an account whose sign-in cannot be read (section 8) |
| Saved meter copy | the `cachedUsageUtilization` key in an account's `.claude.json` | an older copy of the same meters, used only if the live read fails | freshness: the CLI stopped refreshing it around November 2026, so treat it as old |
| Rates file | `rates_file` in the config | per-model list prices | correctness over time: it is a dated copy of public prices; the user must check it |
| Config file | `~/.threadops/headroom/config.json`, or `config.json` in the folder named by `HEADROOM_HOME` (old aliases: `USAGE_MIRROR_CONFIG`, `~/.config/usage-mirror/config.json`) | account labels, colours, paths, time zone, folders | nothing else; it holds no secrets |

The endpoint facts (URL, request headers, field names) were taken from the community tool `jens-duttke/usage-monitor-for-claude`, which documents them. They were not guessed. The endpoint is undocumented by Anthropic and may change without notice.

## 5. Definitions

- **Fresh input**: new input tokens plus cache writes. **Cache read** is shown on its own and never added into fresh input.
- **API-equivalent cost**: tokens times list price. A benchmark for comparing causes. It is not spend, because most Claude Code use runs on a flat plan.
- **Turn**: one message a session had to answer. Origins: `typed` (a person typed it), `scheduled` (a timed self-prompt or a scripted run), `peer` (from another session), `task` (a background task result or a subagent handing back its result). Slash commands are not counted.
- **Response**: one model response, subagents included. Responses with the synthetic model name are skipped.
- **Session**: one session id. Its title is the first of: custom title, agent name, AI title, summary.
- **Cold cache rebuild**: a main-thread response that wrote at least 20,000 tokens to the prompt cache and read back less than it wrote. The extra cost is the write price minus what the same tokens would have cost to read warm. Common causes: the cache expired while idle, a compaction, a model or account switch.
- **Day and hour**: in the configured time zone. If the zone cannot be loaded the tool uses UTC and shows a notice, because a silent fallback would move every day boundary.
- **Duplicate files**: a response found in several files belongs to the home whose copy stopped growing first, because the original stops growing when a session moves. A tie on the last response goes to the file written first.
- **Account of a turn**: the account that answered it (the first main response at or after the turn).

## 6. The forecast method

The forecast is deliberately simple so a person can check it by hand.

1. Take the stored readings of one window of one account, oldest first.
2. If a reading is lower than the one before it, the window reset. Start again from that reading.
3. Rate one is the rise between the last two readings, divided by the hours between them. Rate two is the rise from the newest reading back to the latest reading that is at least 60 minutes older.
4. Time to 100 is the points left divided by the rate.
5. Compare the time at which 100 would be reached with the window's reset time. If the limit comes first, the page shows a warning that says "Runs out before reset" with an icon and text, never colour alone.

Worked example with synthetic numbers: a 5-hour window reads 75 percent, and 50 minutes later reads 81 percent. The rise is 6 points over 0.83 hours, which is 7.2 points an hour. There are 19 points left, and 19 divided by 7.2 is about 2.6 hours. If the window resets in 4 hours, the limit arrives first.

The forecast assumes the rate holds. It says nothing about use that has not happened yet, and nothing about chat or other machines beyond what the meter already counted. It gives no projection with fewer than two readings in the window, or when the meter is flat or falling, and it says why. If the newest reading is from a window that has since reset, it says the reading is older than the window.

## 7. The outliers review

`outliers.py` reads the collector's database for the window (default 12 hours) and writes items such as:

- the window's total compared with the median of the previous seven days of windows of the same length;
- how much of the cost answered timed self-prompts, when that is a quarter or more;
- the busiest hours, and the typical hour, because a steady floor with no quiet hour usually means something runs unattended;
- the largest sessions and their share;
- cold cache rebuilds, with the extra cost over warm reads;
- compactions, automatic and manual;
- a single response that cost a large share of the window;
- responses that could not be priced.

Each run is `{at, window_from, window_to, items: [{title, detail}]}` in `insights.json`, the last 30 kept. The script finds what can be counted. The interesting facts that need judgement (a deploy went wrong, a loop was left on) are for the agent to add with `--add-item`.

## 8. Limitations

- **The endpoint is undocumented.** It may change, move or start refusing requests. The tool reads fields defensively and shows what it got; when a field is absent, the page leaves it out instead of guessing.
- **One sign-in per account.** The tool reads the meter of an account with that account's own sign-in file. It cannot read one account's meter with another account's sign-in, and it cannot see an account whose sign-in is not in its home folder. On macOS the sign-in is usually kept in the system keychain, which this tool does not read, so live meters are unavailable there until someone adds support.
- **Extra usage and credits may be absent.** They are reported only for accounts that have the feature, and some sign-in kinds or plans are refused by the endpoint. The page then says "not reported". It never shows a made-up number. The credit amounts that were seen were in minor currency units (an example: 1250 out of 50000 meaning 12.50 of 500.00); the tool divides by ten to the power of `decimal_places`, two if that field is missing. Treat that as observed, not documented.
- **Per-model limits moved.** Per-model weekly limits used to be separate keys named `seven_day_<model>`. They also appear in a newer `limits` array. The tool reads both. The shape of an item in `limits` has been seen only partly (a kind, a label, a severity, an active flag, a percent and a reset time), so the reader is tolerant and records which keys it saw.
- **Saved meters are old.** The Claude Code CLI stopped keeping `cachedUsageUtilization` current around November 2026. A live read is needed. The saved copy is only a fallback and the page labels it as saved.
- **API-equivalent is a benchmark.** List prices change, discounts and plan terms differ, and a flat plan is not billed per token. Never present the figure as spend.
- **Queue-delivered automated turns can look typed.** A message injected into a session by an outside tool may carry no origin marker, so it counts as typed. The typed count is therefore an upper bound.
- **Transcripts are local only.** Nothing on the page covers claude.ai chat, the desktop app, other machines or other tools. The meter counts them; the transcripts do not. The two must not be subtracted.
- **Transcripts get pruned.** Claude Code removes old transcripts after a retention period (by default thirty days, to the best of our knowledge; check the user's settings). The collector's database keeps rows it has already read, so history outlives the files, but a file that was pruned before the first scan is gone.
- **A response can be credited to the wrong turn.** Attribution is by time: a subagent that outlives its turn is credited to the next turn.
- **Size.** The page embeds every row of the window. A very large history makes a large file. Shorten `days` in the config if the page is slow.
- **Platforms.** Built and tested on Windows with Python 3.11 and Node 24 (for the page script check). Linux and macOS paths are written to work but have not been run.
- **No live test of the endpoint in this release.** The tests use synthetic payloads and a patched network call. The first real run on a user's machine is the first real test of the live path in this packaging.

## 9. Privacy and security

- The collector stores timestamps, ids, model names, token counts, a working-folder name, session titles, turn origin labels and compaction markers. It never stores message text, tool input or output, or file contents. The text of a user record is looked at in memory, only to tell a slash command from a prompt, and is not stored.
- Session titles are stored and shown on the page. They can be sensitive. A page that is shared carries them.
- The access token is read from the account's sign-in file, sent in one request header, and never printed, logged, stored or placed in an error message. Failures keep only an HTTP status code.
- The tool never writes to an account home and never changes a setting, a schedule or a transcript.
- `leak_scan.py` exists so a person who forks the skill can check a folder for emails, drive and home paths, identifiers, artifact links, token shapes and their own private terms before a push.

## 10. Troubleshooting

| What you see | Meaning | Do |
|---|---|---|
| `meters ... none, note: no_credentials` | no sign-in file in that home | confirm the home path in the config; on macOS see the limitation above |
| `note: http_401` | the sign-in expired | start Claude Code in that account once so it renews, then refresh |
| `note: http_403` or `http_404` | the endpoint refused or moved | report it upstream with the date; use `--no-live` meanwhile |
| `note: http_429` | too many requests | wait; the tool already reuses a reading for `live_reuse_seconds` |
| `source saved` on a card | the live read failed and an old saved copy is shown | read the card's message; fix the cause above |
| Notice about time zone | the zone name could not be loaded | on Windows run `pip install tzdata`, or set `timezone` to `UTC` |
| Dollar tiles show n/a | the rates file is missing or broken | fix the path or the file |
| "unpriced" chip on a model | the model is not in the rates file | add it with its list prices |
| No sessions at all | wrong home path, or `scan_days` too short | check `path`; raise `scan_days` |
| Page is slow | too many rows | lower `days` |
| Totals look low | transcripts were pruned before the first scan, or an account is missing from the config | check retention and the accounts list |

## 11. Known open topics

1. **`limits[]` item shape.** Only partly known. Ask the first user whose account returns it to share the key names (never the values) so the reader can be made exact.
2. **Extra usage units.** The minor-unit reading is from one observation. Verify with an account that has the feature.
3. **macOS sign-in.** Reading from the keychain is not implemented.
4. **User agent.** The reader identifies itself honestly as `headroom/<version>`. The community reference tool sends a Claude Code style user agent; whether the endpoint treats a plain tool name differently is untested. If reads fail with HTTP 403, that is the first thing to look at. It can be changed with `user_agent` in your own config.
5. **Other collectors.** The private original also read Codex session logs, the desktop app's agent-mode sessions, and OpenHands job ledgers. They are not shipped. The Codex reader depends on its log format and an optional compression library and was mapped to one person's account folders. The desktop reader reads folders that can hold other people's sessions and depends on app-internal layout. The OpenHands reader depends on a private ledger format. A clean, optional, off-by-default Codex collector is the most useful addition.
6. **Plan name.** The page does not show which plan an account is on; the endpoint payload used here does not say.
7. **Several logins, one machine.** Two homes signed in to the same login are two accounts to this tool. A shared meter would be read twice.
8. **Prompt classification.** The original separated typed housekeeping prompts (re-arm a timer, switch a home) from real prompts with a word heuristic. It was specific to one person's habits and is not shipped, so those count as typed here.
9. **A public view.** The original published a scrubbed pseudonymous copy of the numbers for showcase. Not shipped.
10. **Cache lifetime.** Cold rebuilds are detected by sizes, not by the cache's actual lifetime, which differs by write type.
11. **Per-account attribution after a move.** The tie rules in section 5 are a heuristic; a session moved twice may be split oddly.

## 12. Things to suggest to the user

Offer each once, when it fits, and accept a no.

- "Did you know you can get an audible alarm when a limit runs low? Add the chime skill (its control page is the Soundboard), and I can play it when a meter passes a threshold you choose."
- "I can refresh this page every half hour on a timer with the reprompt skill, so the forecast always has fresh readings."
- "I can publish this page as a private claude.ai Artifact and update it in place, so you can open it on your phone. It holds session titles, so tell me before you share it."
- "Your review shows spend through the night with nobody typing. Do you want me to list which sessions are doing it?"
- "A few responses were not priced because the rates file lacks the model. Shall I add it?"
- "I can add your other Claude Code account so both show on one page."
- "Your rates file is more than a month old. Shall I check it against the pricing page?"
- "You changed something useful in the skill. Do you want me to prepare it as a fork and pull request upstream?"

## 13. Extending, and where changes belong

- Local choices go in the headroom home (`~/.threadops/headroom`, or `HEADROOM_HOME`): the config file, the rates file, or your own notes. Never in the skill folder: an update replaces it. A household's own rules for the skill go in a small private skill named `headroom-house`.
- Your own automation (an alarm, a publish step, a timer) goes in your own scripts and calls this skill's scripts.
- A real improvement to the skill goes upstream as a pull request from a fork of `github.com/thealignedfew/skillgarden`. Run the tests and the leak scan first, add a `CHANGELOG.md` entry, and keep the version in `SKILL.md`, `scripts/common.py`, `config.example.json` and the changelog together.

## 14. Credits

The usage endpoint facts come from `jens-duttke/usage-monitor-for-claude`. Anthropic's public pricing page is the source of the list prices in the example rates file.
