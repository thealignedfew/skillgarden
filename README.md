# skillgarden

Open agent skills and small tools for running many AI coding sessions at once, by The Aligned Few.

A skill here is a folder with a `SKILL.md` that an agent reads on demand, plus whatever scripts and assets it needs. Each folder has its own README with the install step and the reason the skill exists. They were grown in one working estate of several dozen long-lived Claude Code sessions and are published as they are generalised.

| Folder | What it is |
|---|---|
| `parley` | One published page per agent session for its correspondence with the person running it: open questions as cards, answered in a box on the card, by a click or by comment. |
| `reprompt` | Timed loops in which a Claude Code session prompts itself again between your prompts: keep the prompt cache warm, or keep checking its own work while you are away. |
| `chime` | Audible alerts and toasts for Claude Code sessions: each kind of moment has its own sound and a toast names the session, so you can tell from across the room which one needs you. Ships no audio: every sound is a tone the skill generates itself, and a Soundboard page lets you replace, generate or reset each one. An optional script fetches third-party clips for your own use, from addresses you supply. |
| `headroom` | How much room is left in your Claude usage: one self-contained page with per-session tokens and API-equivalent cost from your local transcripts, live plan meters for one or more accounts, and a run-out forecast. Called `usage-mirror` up to 1.0.0; the old settings place is still read until you move it. |
| `stagecraft` | How to build, lay out and publish an artifact page so it fits the person who reads it: an author header, an Options panel, sortable and filterable tables, themes, tooltips, summary cards, signed rulings and an answer box, driven by the reader's own settings. |
| `ramgovern` | A Working Set Governor for Windows machines running many Claude Code sessions. |
| `familycfo` | A household money ledger in one web page. |

## Licence

Everything in this repository is released under the Apache License 2.0 (see `LICENSE`) unless a folder carries its own `LICENSE` file, in which case that file governs that folder. `ramgovern` carries its own MIT licence from its first release.

"The Aligned Few", "skillgarden" and the product names used here are names of The Aligned Few. The licence covers the code and text; it does not grant a right to use those names to describe a modified version as ours.

## Contributing

See `CONTRIBUTING.md`. Issues and pull requests are welcome; the bar is that a change keeps working for an agent reading it cold.

Skills here are replaced whole when you update them, so keep your own settings, sound files and notes outside the skill folder: in `~/.threadops/<skill>` (or the folder named by `<SKILL>_HOME`), and a household's own rules in a small private skill named `<skill>-house`. If you or your agent make a significant improvement to a skill, we would like to see it as a pull request from a fork; every pull request is reviewed and tested before any merge, and none is merged automatically. See `CONTRIBUTING.md`.
