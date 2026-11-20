# Changelog

All notable changes to headroom (called usage-mirror up to 1.0.0). The version is kept in the `SKILL.md` header, `scripts/common.py` (`VERSION`), the `user_agent` in `config.example.json` and here; the tests check that they agree.

## 1.1.0

- Renamed from usage-mirror to headroom: the skill name, the folder, the titles, the page file (`headroom.html`, was `usage_mirror.html`), the user agent (`headroom/1.1.0`), the test file (`tests/test_headroom.py`) and the text. Nothing else about the behaviour changed.
- New settings home: `~/.threadops/headroom`, or the folder named by the `HEADROOM_HOME` environment variable. The config is `<headroom home>/config.json`; the rates file, history and built page default to `rates.json`, `history/` and `out/` in the same folder unless the config names other places. `init_config.py` writes there.
- Old places kept as aliases, read only when `<headroom home>/config.json` is absent: the `USAGE_MIRROR_CONFIG` environment variable, then `~/.config/usage-mirror/config.json`. A one-line notice on stderr suggests moving the file. Paths written inside an old config keep working. The leak scan reads `HEADROOM_LEAK_TERMS` and still reads `USAGE_MIRROR_LEAK_TERMS`.
- `SKILL.md` carries the two sections every skill in the repository carries, "Your settings live outside this folder" (with `HEADROOM_HOME` and a private `headroom-house` skill for household rules) and "Propose improvements upstream". They replace "The settings rule" and "Contributing upstream".
- `config.example.json` and every document that names a path updated.

## 1.0.0

First public release, generalised from a private page that mirrored a fleet of sessions.

- Collector: reads Claude Code transcripts from any number of account homes, incrementally, one row per response, duplicate-safe; turn origins; compaction markers; titles. No message text is stored.
- Page: one self-contained HTML file. Totals, plan meters with forecast, daily and hourly history, outliers review, models and sessions tables, light and dark themes.
- Meters: live read of the account usage endpoint with the account's own sign-in, a saved-copy fallback, per-model weekly windows from both `seven_day_<name>` keys and the `limits` array, extra usage where reported, and a stored history of every reading.
- Forecast: straight-line run-out between consecutive readings, with the arithmetic shown.
- Outliers: a 12-hour review (any window length) with room for the agent's own observations.
- Settings live in a config file outside the skill folder (`USAGE_MIRROR_CONFIG`, an alias since 1.1.0); rates in a separate file; `config.example.json` and `rates.example.json` ship.
- `init_config.py` first-run helper, `leak_scan.py` publish gate, synthetic fixture and tests.
- Not included from the private original: Codex, desktop agent-mode and OpenHands collectors, the typed-housekeeping heuristic, the seat map and the public scrubbed view. See the whitepaper, open topics.
