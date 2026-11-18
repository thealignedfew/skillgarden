# parley

A Claude Code skill that gives each of your sessions one published page (a claude.ai artifact) for its correspondence with you. Open questions are cards you settle with an answer box, a click or a comment, each session's recent work and decisions sit below them, and the page says who wrote it and whether that session is still watching for comments.

It is for people who run several Claude Code sessions and are tired of scrolling chats to find what each one is asking.

[screenshot placeholder: a parley page with two cards, the detail rail on the left and the author-status bubble in the header]

## What you get

- One page per session, republished in place at the same URL, and only when something on it changed.
- Question cards with an answer box on every open card, Important, Urgent and Pin toggles, a stage (Open, Responded, In review, Completed, Blocked, Deferred, Superseded) and a most responsible party.
- What needs you now on top of each card (the question, the live steps, the newest update, the answer box) and everything older under a collapsed History block on its own shaded panel.
- Completed belongs to the session that asked. Your click on Completed is a claim the session checks against the real work before it closes the card or reopens it.
- Your answer, and the session's reply to it, show on the card.
- A five second countdown with Undo before a click on a stage, Important, Urgent or Pin is saved, so a mistaken click costs nothing.
- Hold as well as Approve and Strike on each row of a list ruling, for the rows that wait on something else.
- Grouping by topic, by the session that asked, or both, in collapsible sections with a narrow bar at the left.
- A daily recheck: cards whose last dated line is more than three days old are flagged, and `parley_stale.py` lists them.
- Timestamped updates on each card, newest first, and explanation blocks that show only at the Verbose and Exhaustive detail levels.
- A detail rail: Zero, Concise, Verbose, Exhaustive. Pin it across the top instead of the left edge, or switch it off for a tiny page.
- An artifact header: author name, session id, headless flag and a live, idle or quiet bubble driven by a heartbeat the session writes to the page's db.
- A Log tab scaffold for any artifact page that is not a parley.
- A theme menu: Auto (follows the browser), Dark, Light, always high contrast.
- An optional crew view, so one manager session can show its reports' questions on one page.
- A moved-page notice, for when a session changes account and its old page has to point to the new one.
- A compile script that builds the page from JSON fragments, flags stale cards, and refuses a page that carries a file path or document link.

## Install

Copy this folder into your Claude Code skills directory:

```
cp -r parley ~/.claude/skills/parley
```

On Windows, copy the folder to `%USERPROFILE%\.claude\skills\parley`. The skill is `SKILL.md`; the page template is `assets/parley-template.html`; the scripts are in `scripts/`. They need Python 3 and nothing else.

You also need the Artifact tool in your Claude Code session, because that is what publishes and updates the page.

## Files

- `SKILL.md`: the skill itself.
- `assets/parley-template.html`: the page. Its `<meta name="parley-template">` tag names the template generation (2.18).
- `assets/artifact-header-snippet.html`: the header, the theme and the detail rail for any other page a session publishes, plus the Log tab scaffold (part 4).
- `assets/moved-page-template.html`: the notice that replaces an old page after a session moves account.
- `scripts/parley_compile.py`: builds the page from JSON and checks the cards.
- `scripts/parley_stale.py`: lists the open cards that are due a recheck.
- `scripts/parley_status.py`, `scripts/parley_tokens.py`: fill the capacity, remote control and token figures.

The sibling `reprompt` skill in this repository supplies the timed loop that keeps a parley's heartbeat, comment reads and daily recheck going while you are away.

## Quick start

1. Copy `assets/parley-template.html` to a working file, for example `my-session_PARLEY.html`, and change `<title>Parley: SEAT-ID</title>` near the top to your session's name.
2. Open it and edit the `DATA` object at the bottom: `seat` (the session's name), `reviewer` (your name), `updated` (a stamp with a zone, such as `2025-01-15 09:00 UTC`), and your first card in `questions` (`id`, `codename`, `title`, `topic`, `opened`, `ask`, `steps`, `dflt`, `origin`, `checked`). Replace every example row in `activity`, `work`, `decisions`, `changes` and `artifacts`.
3. Ask Claude Code to publish it with the Artifact tool, with the database and comments capabilities on (`capabilities: {db: {}, comments: {}}`) and the icon "chat".
4. To let someone else read or answer it, share the page from its own Share menu. The tool cannot share for you.
5. From then on, edit `DATA` and republish the same file without an icon, when something on the page changed. The URL stays the same.

Or just say "parley" to a session that has the skill loaded and it will follow `SKILL.md`.

## Compile (optional, for crews and for checks)

Keep the `DATA` object as JSON in `my-session_PARLEY.json` (the same keys as in the template), then:

```
python -I -B scripts/parley_compile.py --own my-session_PARLEY.json --out my-session_PARLEY.html
```

Add `--report other-session_PARLEY.json` once per report to put their questions on the same page, `--refresh` to pick up a new template, and `--stale-days N` to change how old a card may be before it is flagged. The compile prints warnings for cards that are missing a check note, steps, an origin or a codename, and for open cards with no dated line in more than three days. It refuses (writes nothing) when a card has no `opened` time, when a paste box holds a control character, or when any file path or document name appears on the page.

The daily recheck list on its own:

```
python -I -B scripts/parley_stale.py my-session_PARLEY.json
```

## Limits and honest caveats

- Publishing needs the Artifact tool. Where it is missing the template still works as a local HTML file, but there is no db, no comment wake and no status controls.
- Card status clicks and answers are saved through the artifact `db` capability. If your viewer cannot write, the controls are read-only. The answer box wakes a session only when the page declares the `comments` capability and a session is watching; otherwise the words wait in the status document until the session's next check.
- The author-status bubble is a timer estimate from the last check-in, not proof anyone is listening.
- Comments only wake a session if its window or loop is still alive. Moving a session to another account breaks the link; republish from the new account.
- The template pulls three fonts from Google Fonts and falls back to system fonts offline.
- This was built for one person's workflow and then generalized. Some names and defaults may still feel specific; the field names `seat` and `reviewer` are just labels. The daily recheck, the Completed claim and the Log tab are habits the skill asks of the session; nothing enforces them except the compile's warnings.
- Nothing here has been tested on platforms other than Windows with Python 3 and a current Claude Code.

Not affiliated with Anthropic. 'Claude Code' is named only to say what this works with. By The Aligned Few.
