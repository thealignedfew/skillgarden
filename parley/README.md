# parley

A Claude Code skill that gives each of your sessions one published page (a claude.ai artifact) for its correspondence with you. Open questions are cards you settle with a click or a comment, each session's recent work and decisions sit below them, and the page says who wrote it and whether that session is still watching for comments.

It is for people who run several Claude Code sessions and are tired of scrolling chats to find what each one is asking.

[screenshot placeholder: a parley page with two cards, the detail rail on the left and the author-status bubble in the header]

## What you get

- One page per session, republished in place at the same URL.
- Question cards with Important and Urgent toggles, a stage (Open, Start, In review, Completed, Blocked, Deferred, Superseded) and a most responsible party.
- Timestamped updates on each card, newest first, and explanation blocks that show only at the Verbose and Exhaustive detail levels.
- A detail rail on the left edge: Zero, Concise, Verbose, Exhaustive.
- An artifact header: author name, session id, headless flag and a live, idle or quiet bubble driven by a heartbeat the session writes to the page's db.
- A theme menu: Auto (follows the browser), Dark, Light, always high contrast.
- An optional crew view, so one manager session can show its reports' questions on one page.
- A compile script that builds the page from JSON fragments and refuses a page that carries a file path or document link.

## Install

Copy this folder into your Claude Code skills directory:

```
cp -r parley ~/.claude/skills/parley
```

On Windows, copy the folder to `%USERPROFILE%\.claude\skills\parley`. The skill is `SKILL.md`; the page template is `assets/parley-template.html`; the scripts are in `scripts/`. They need Python 3 and nothing else.

You also need the Artifact tool in your Claude Code session, because that is what publishes and updates the page.

## Quick start

1. Copy `assets/parley-template.html` to a working file, for example `my-session_PARLEY.html`, and change `<title>Parley: SEAT-ID</title>` near the top to your session's name.
2. Open it and edit the `DATA` object at the bottom: `seat` (the session's name), `reviewer` (your name), `updated` (a stamp with a zone, such as `2025-01-15 09:00 UTC`), and your first card in `questions` (`id`, `codename`, `title`, `opened`, `ask`, `steps`, `dflt`, `origin`, `checked`). Replace every example row in `activity`, `work`, `decisions`, `changes` and `artifacts`.
3. Ask Claude Code to publish it with the Artifact tool, with the database capability on (`capabilities: {db: {}}`) and the icon "chat".
4. To let someone else read or answer it, share the page from its own Share menu. The tool cannot share for you.
5. From then on, edit `DATA` and republish the same file without an icon. The URL stays the same.

Or just say "parley" to a session that has the skill loaded and it will follow `SKILL.md`.

## Compile (optional, for crews and for checks)

Keep the `DATA` object as JSON in `my-session_PARLEY.json` (the same keys as in the template), then:

```
python -I -B scripts/parley_compile.py --own my-session_PARLEY.json --out my-session_PARLEY.html
```

Add `--report other-session_PARLEY.json` once per report to put their questions on the same page, and `--refresh` to pick up a new template. The compile prints warnings for cards that are missing a check note, steps, an origin or a codename, and it refuses (writes nothing) when a card has no `opened` time or when any file path or document name appears on the page.

## Limits and honest caveats

- Publishing needs the Artifact tool. Where it is missing the template still works as a local HTML file, but there is no db, no comment wake and no status controls.
- Card status clicks are saved through the artifact `db` capability. If your viewer cannot write, the controls are read-only.
- The author-status bubble is a timer estimate from the last check-in, not proof anyone is listening.
- Comments only wake a session if its window or loop is still alive. Moving a session to another account breaks the link; republish from the new account.
- The template pulls three fonts from Google Fonts and falls back to system fonts offline.
- This was built for one person's workflow and then generalized. Some names and defaults may still feel specific; the field names `seat` and `reviewer` are just labels.
- Nothing here has been tested on platforms other than Windows with Python 3.11 and a current Claude Code.

Not affiliated with Anthropic. 'Claude Code' is named only to say what this works with. By The Aligned Few.
