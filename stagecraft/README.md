# stagecraft

A Claude Code skill for building the pages your sessions publish as artifacts, so that each one behaves like a small app: it fits the window it is opened in, its tables sort, filter and rearrange, and it remembers how its reader set it up.

One include file gives a page an author header, an Options panel, themes, tables you can sort and filter, tooltips with history, summary cards, signed rulings and an answer box. Your own settings (about fifty, in nine groups) decide the rest, and the first time you use it the session proposes those settings to you instead of interviewing you.

It is for people who ask Claude for dashboards, reports, trackers and review lists as pages, and are tired of pages that squeeze text into a strip, cut content off, wrap every table row, or look different every time.

## What you get

- **A header on every page.** Who made it (the author's name and session), whether that session is still watching (a live, idle or quiet status that the page works out from the last time the author checked in), how old the data is, and a box for a quick question to the author. The header can be shortened to a name and a date, or switched off, for pages that leave your team.
- **A detail slider.** A slider at the page's edge shows more or less of the page, from level 0 (the headline only) to level 3 (the working). The author marks blocks `l1`, `l2` or `l3`. It sits beside a single Pin to top button, and it stays out of the way of the other controls.
- **Shortcuts, and a list of them.** Keys for the Options panel (`o`), the theme (`t`), less and more detail (`[` and `]`), the filter box (`/`), tabs (`1` to `9`, `,` and `.`), the next item waiting for you (`n` and `p`), comments (Ctrl+Space then `C`), and copying a table as CSV. `?` shows the list, which shows only what applies to the page you are on. Every key can be changed in Options, under Bind Shortcuts. Shortcuts never fire while you are typing in a box.
- **Tables that behave.** Every table sorts by its header, gets a filter box once it is long, copies as CSV, and lets you move and hide columns. A row stays on one line by default so the eye can compare rows; a long text column shrinks its font before it takes width from the numbers. A table is never put in its own scroll box.
- **Pages that fit.** No sideways scroll, no content cut off, no blank band where the content could have used the space, and a clear gap around anything that floats at an edge.
- **Summary cards and chips that filter a table, tooltips with a sparkline of a figure's history, signed rulings (Approve, Hold, Strike), ask cards, named tabs, a Log tab and a Method tab** that explains how the page was made to a reader who has nothing else.
- **Settings that outlive the page.** A reader's theme, column order, filters and answers are stored against stable keys, so republishing does not reset them. Text a reader has typed and not sent comes back after a refresh.
- **An optional publish check** (a hook script) that reminds you, or refuses, when a page skips these parts.

## What it needs

- Claude Code, with the Artifact tool for publishing pages.
- Python 3.8 or later for the three scripts. They use only the standard library, make no network call and read or write only the settings files described below.
- A current desktop browser to read the pages. Rulings, ask cards and the options that follow you across browsers also need the capabilities that the artifact viewer offers; a page opened without them says so in one line and offers a copy button instead.

## Install

1. Copy the skill folder into your Claude Code skills folder:

   ```
   cp -r stagecraft ~/.claude/skills/stagecraft
   ```

   On Windows, copy it to `%USERPROFILE%\.claude\skills\stagecraft`. The skill is `SKILL.md`; the scripts, the catalog of settings, the include file and the references stay in the folder beside it.

2. Optional: install the publish check. It is a PreToolUse hook on the publish tool. In `~/.claude/settings.json`, as a starting point (check the hooks documentation for your Claude Code version, since hook settings change):

   ```
   {
     "hooks": {
       "PreToolUse": [
         { "matcher": "^Artifact$",
           "hooks": [ { "type": "command", "command": "python ~/.claude/skills/stagecraft/hooks/stagecraft_gate.py" } ] }
       ]
     }
   }
   ```

   Installing a hook changes your settings file, so the skill never does it for you.

3. Check that it works on your machine: `python ~/.claude/skills/stagecraft/tests/smoke_test.py`. It runs the scripts against an empty temporary home and prints one PASS or FAIL per check.

## The one command

`/stagecraft` takes one of four words.

| You type | What happens |
|---|---|
| `/stagecraft` | The session says in a few lines what stagecraft does and asks which page you have in mind. |
| `/stagecraft new <what the page is for>` | It reads your settings, then builds a page for that purpose. Any other words after the command mean the same as `new`. |
| `/stagecraft check <page file>` | It runs the publish check on that file without publishing it and tells you in plain words what is missing. |
| `/stagecraft apply <page file>` | It adds the stagecraft parts to a page that already exists. Safe to run twice. |
| `/stagecraft settings` | It shows your settings and changes one when you say so. |

Claude also uses the skill without the command whenever it is about to publish a page, or when you complain that a page looks wrong.

## Changing the options

Three layers, later wins: the catalog's defaults (`options/catalog.json`), your own file (`~/.stagecraft/options.json`, or the folder named in `STAGECRAFT_HOME`), and a project file (`.claude/stagecraft.json` in a folder or any folder above it) for a codebase or a team.

There are three ways to change one:

1. **Say it in plain words** to any session ("stop wrapping the rows", "show cents", "use the whole screen"). The session finds the setting behind it, saves it and tells you how to undo it.
2. **Change it in a page's own Options panel** (the gear, or `o`). That changes that page only.
3. **Edit the file**, or run the script: `python scripts/options.py show` lists every value and where it comes from; `python scripts/options.py set numbers.negatives minus` saves one; `unset` puts it back; add `--project` to write the project file.

The first time you use the skill, the session looks at what it can see (how many logins you have, what pages you already have, what you just asked for) and shows one short proposal. You change any line or accept it, and it is saved. No questionnaire.

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `STAGECRAFT_HOME` | `~/.stagecraft` | the folder that holds your `options.json` |
| `STAGECRAFT_GATE_LOG` | `~/.stagecraft/gate.log` | where the publish check writes one line per decision |
| `STAGECRAFT_SNIPPET` | the include file in the skill's `assets` folder | the include file the injector adds to a page |

## Limits and honest caveats

- The include file was tested in headless Chrome at three window widths, with a stand-in for the artifact viewer's capabilities. Firefox and Safari have not been tried, and a screen reader and a real touch screen have not been used.
- The layout rules cannot see a band of wasted space beside squeezed content, and the publish check reads only a page's own style blocks and inline styles. The check in `references/layout.md` is still worth doing by eye.
- A link to another Claude page is written so that it stays in the browser instead of opening the installed Claude app. That rests on documented browser behaviour and has not been watched working in a browser that has the app installed.
- Column reorder and hide need a simple table (one header row, no merged cells) and have no touch gesture.
- The page cannot open the print dialog itself; the print style sheet applies when you print from the browser.
- This was built for one person's workflow and then generalised. Some defaults, such as negatives in parentheses, one line per table row and a high text contrast, are opinions: each is a setting.
- The scripts and the demo page's self-test (`assets/demo-page.html#selftest`, which runs in a browser) are the project's checks. The hook snippet above is untested in a fresh Claude Code session.

Apache-2.0, see the repository LICENSE.

Not affiliated with Anthropic. 'Claude Code' is named only to say what this works with. By The Aligned Few.
