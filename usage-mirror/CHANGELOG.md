# Changelog

All notable changes to usage-mirror. The version is kept in the `SKILL.md` header, `scripts/common.py` (`VERSION`) and here; the tests check that they agree.

## 1.0.0

First public release, generalised from a private page that mirrored a fleet of sessions.

- Collector: reads Claude Code transcripts from any number of account homes, incrementally, one row per response, duplicate-safe; turn origins; compaction markers; titles. No message text is stored.
- Page: one self-contained HTML file. Totals, plan meters with forecast, daily and hourly history, outliers review, models and sessions tables, light and dark themes.
- Meters: live read of the account usage endpoint with the account's own sign-in, a saved-copy fallback, per-model weekly windows from both `seven_day_<name>` keys and the `limits` array, extra usage where reported, and a stored history of every reading.
- Forecast: straight-line run-out between consecutive readings, with the arithmetic shown.
- Outliers: a 12-hour review (any window length) with room for the agent's own observations.
- Settings live in a config file outside the skill folder (`USAGE_MIRROR_CONFIG`); rates in a separate file; `config.example.json` and `rates.example.json` ship.
- `init_config.py` first-run helper, `leak_scan.py` publish gate, synthetic fixture and tests.
- Not included from the private original: Codex, desktop agent-mode and OpenHands collectors, the typed-housekeeping heuristic, the seat map and the public scrubbed view. See the whitepaper, open topics.
