---
name: stagecraft
argument-hint: "[new <what the page is for> | check <page file> | apply <page file> | settings]"
description: How to build, lay out and publish an artifact page so it fits the person who reads it. Use it every time you are about to publish or republish an artifact page (a parley is the exception, the parley skill's own template builds it), and whenever someone asks for a dashboard, report, tracker, review list, status page or internal tool as a page, complains that a page looks wrong (text in a narrow strip, cut-off content, wasted space, a table that wraps or scrolls inside a box), asks where a page should live or why they cannot see one, or wants to change how their pages look or behave. One include file gives a page an author header, an Options panel, themes, sortable and filterable tables, tooltips with history, summary cards, signed rulings and an answer box. The person's own settings decide the rest, and on first use you propose those settings to them.
---

# Stagecraft

Version 0.4.4. A page built with stagecraft behaves like a small app: it fits the window it is opened in, its tables can be sorted, filtered and rearranged, it remembers how its reader set it up, and it can ask its reader a question and carry the answer back to the session that made it.

Stagecraft has two halves, and the split matters.

- **Principles** (below) are the few things that hold for every page, with the reason for each. They are short on purpose.
- **Settings** are everything else: where a page is published, how wide text runs, how a table treats long text, how money is written, whether a click gets an Undo countdown. They live in `options/catalog.json`, not in this text, because they are the reader's taste and not yours. Read the person's settings before you build. When this text and a setting disagree, the setting wins.

## Typed as a command

`/stagecraft` takes one of four words. With nothing after it, say in a few lines what stagecraft does and what the four words do, and ask which page they have in mind. Any other words after the command describe the page they want: treat them as `new`.

- `/stagecraft new <what the page is for>`: build a page for that purpose. Read the settings first ("Before you build"), then follow "Building a page".
- `/stagecraft check <page file>`: run the publish check on that file without publishing it. Give `hooks/stagecraft_gate.py` one JSON object on standard input, `{"tool_name": "Artifact", "tool_input": {"file_path": "<the page file>"}}`, and report in plain words what it printed: nothing means the page passes; a reminder names what is missing; a refusal names the mark and the fix.
- `/stagecraft apply <page file>`: add the stagecraft parts to a page that already exists: `python scripts/inject_stagecraft.py <page file> --seat <author> --session <session id> --key <page-key>`. It is safe to run twice. Stagecraft replaces the older artifact header of the parley skill (a page never carries both): if the page has that header, the script removes it and carries its author values (seat, session, account, headless, questions, published, period) into `PB_CONFIG.header`, and if it cannot find the older header whole it changes nothing and says what it found. Then check the layout at three widths, as step 5 of "Building a page" says.
- `/stagecraft settings`: show the person's settings (`python scripts/options.py show`) and change one when they say so (`python scripts/options.py set <id> <value>`), telling them in one line how to undo it.

## Before you build: read the settings

```
python scripts/options.py status        # has first launch happened?
python scripts/options.py show          # every effective value and where it comes from
python scripts/options.py page-config   # the page defaults, as JSON for PB_CONFIG.defaults
```

Three layers, later wins: the catalog's defaults, the person's own file (`~/.stagecraft/options.json`, shared by all their logins), and a project file (`.claude/stagecraft.json`) for a codebase or team that needs its own.

### First launch: propose, do not interview

If `status` says first launch is not done, do it before the first page, and keep it to one screen.

1. Run `python scripts/options.py first-launch`. Each option carries a `recommend` text written for you: it says what to look at to choose a value for this person.
2. Look before you ask. How many logins or workspaces are on this machine? What pages do they already have, and what do those look like? What did they just ask for? Do they talk like someone who reconciles to the cent, or someone who wants the headline? Most of the answers are in front of you.
3. Show one proposal, grouped as the catalog groups it, listing only the settings where your pick differs from the default or plainly matters to them. Each line: the setting in plain words, the value you would pick, and half a line of why. For example: "Tables: one line per record, long notes in a smaller font before the column widens. You compare rows, and a wrapped row breaks that."
4. Let them change any line. Save with `options.py set <id> <value>`, then `options.py done`.
5. Tell them the three ways a setting changes later: say it in plain words to any session, change it in a page's own Options panel (that page only), or edit their options file.

The aim is that the person ends up owning the settings. A long questionnaire teaches them nothing; a proposal they can argue with does.

### Afterwards: a correction is a setting

When the person corrects a page ("stop wrapping the rows", "why is this on the other account", "use the whole screen"), fix the page and then find the setting behind it. Save it with `options.py set` and say so in one line, with how to undo it. If they have said the same thing twice, it should already have been a setting: check `show`, and if the setting is there and a page ignored it, that is a defect to report, not a preference to ask about again.

If no option covers what they want, do it for this page, say that no setting exists for it yet, and propose one to the skill's owner (an id, the choices, a default, and the `recommend` text). Do not write the preference into this file.

While `coach.tips` is on, add one line when you hand over a page naming the single setting that most shaped it and how to change it. One, not a list.

## Principles

**1. The page fits the window. Nothing is cut off and nothing is wasted.** Open a page at any width from a phone to a wide monitor: every block is fully visible, there is no sideways scroll, and space the content does not need is given to content that can use it, not left as a blank band. Text, cards and prose reflow to do this. Filling the window does not mean touching its edges: anything that floats at an edge (the detail slider, the data dates) keeps a clear band of `layout.float_gap_px` between itself and the content, on both sides, so the content never runs under or right up against a control. Read `references/layout.md` before you lay out a page; it has the cases that go wrong most often, including the paragraph that sits in a narrow strip above full-width content.

**2. A table is the exception: it is read by row.** A table does not reflow like prose. Unless `tables.rows` says otherwise, a record stays on one line, because the eye can only compare rows that are lines. Header text may wrap, since a header is read once. When one field holds long text, follow `tables.long_text`; the default shrinks that column's font before it takes width from the columns that hold numbers. A table is never put inside its own scrolling box: one scroll bar per page.

**3. The reader's setup survives an update.** Their theme, column order, hidden columns, filters, answers and the tab they were on are stored against stable keys. Keep `PB_CONFIG.key`, table keys, tab ids, ask ids, rulings paths and the ids of shortcuts you add unchanged from one publish to the next, and keep header texts stable. A reader's own keys for the shortcuts (Options, Bind Shortcuts) hang on those ids. Text the reader has typed and not yet sent (an answer in an ask card, a comment) is kept as a draft in their browser and comes back after a refresh; it goes only when it is sent, discarded or thirty days old. A page that forgets its reader on every republish trains them to stop setting it up.

**3a. A link keeps the reader where they are.** A link from one page to another opens a new tab in the same browser; it never throws the reader into another program. A browser with a Claude app installed will hand an ordinary link to that app unless the page prevents it, so the include file writes links to Claude pages in the form that stays in the browser, and gives the reader a switch for the other way (`links.claude_pages`). Write plain links and let the include file do this; `references/components.md` has the mechanics.

**4. A page says only what is true about itself, starting with how current it is.** Every page that shows data carries a "data through" date: the last date the data covers, not the time the page was published. Give it with its time, 24-hour (`through: "2026-01-30 17:45"`), whenever the source has one; a date alone is for a source that only exists by the day. When the data comes from several sources, each source gets its own date, because a page is only as current as its oldest source and the reader needs to see which one that is. `freshness.placement` decides where the dates sit; by default they float at the right edge so they stay in view. No dead controls: a page opened without a capability says so in one line and offers a copy button instead. No invented history: a figure gets a sparkline only when the series exists. No promise that a comment reaches a session unless the header says a session is watching.

**5. A page lives where its session lives, and old links keep working.** Follow `publish.home` and `publish.when_session_moves`. By default a page is published under the account of the session that maintains it, so a page made in one workspace starts in that workspace; when the session moves, the page moves with it in the same turn and the old copy becomes a short notice that links to the new one. `references/publishing.md` has the steps, including publishing as another account.

**6. Ask through the page when the question is about the page.** Follow `feedback.ask_on_page`. An ask card or a rulings table keeps the answer on the page, signed, where the next session finds it. Always state what happens if nobody answers.

**7. Hands off credentials, and say who can see the page.** Never read, print or copy a credentials file; only ever point at a configuration folder. A page is private until its owner shares it: when a page is meant for someone else, say so, using `publish.share_note`.

**8. A page explains itself, to a reader who has nothing else.** A page that shows data carries a Method tab (`method.tab`): what the page is for, how each figure was derived, its sources and their dates, every value that was typed in or assumed (with why, who set it and when to revisit it), what the page cannot tell you, what is still open, and how to rebuild it with no context. It is plain text in the page source, not built by script, so a reader or an agent that has only the file gets all of it; a section that does not apply says "None". Why: a figure nobody can trace is a figure nobody can trust, and the session that made the page will not be there to ask. `references/components.md` has the skeleton and `assets/method-skeleton.html` the markup.

## Building a page

1. Write the content: `<title>`, then your own markup. Use the colour tokens the include file defines (`--bg --surface --fg --muted --line --accent --accent-soft --ask --ask-soft --ok --warn --warn-soft`) for every colour of your own, so both themes keep their contrast.
2. Add the include file, `assets/stagecraft-snippet.html`: parts `PB:STYLE` and `PB:HEADER` first in the content, `PB:SCRIPT` last. Or run `python scripts/inject_stagecraft.py page.html --seat <author> --session <session id> --key <page-key>` after a script has written the page; it is safe to run twice. Stagecraft replaces the older artifact header of the parley skill (its header box, detail slider and Pin to top button), so a page never carries both: two headers, two sliders and two Pin to top buttons are what both produce. The script takes the older header out when it finds one, and a page pasted together by hand keeps Stagecraft's own and hides the other (`PB.layout.report().foreign` says so). A page published headless (a copy made by a script or by another login) also gives `PB_CONFIG.header.source`, the address of the page it was copied from (`--source URL` on the injector): its header then reads "Source: link" and "question page" in place of "Questions: the author's question page". The words of that second link are the person's to choose, once: the settings `header.question_link_live` and `header.question_link_headless` (plain text, at most 40 characters); the injector writes them into `PB_CONFIG.header` as `questions_live` and `questions_label` unless the page gives its own.
3. Define the page before the script. `defaults` is the output of `options.py page-config`: paste it, do not retype it.

```html
<script>
var PB_CONFIG = {
  key: "q3-store-review",          // names this page's saved options. Never change it on an update.
  tab: "Store review",             // the first tab's name: what this page is
  defaults: { /* options.py page-config */ },
  header: { seat: "author name", session: "session id", published: "2026-01-31 09:00", refresh_min: 60 },
  sources: [                       // one line per data source: the last date its data covers
    { name: "Orders", through: "2026-01-30 17:45" },   // date and time when the source has a time
    { name: "Bank feed", through: "2026-01-28", note: "feed is two days behind" }
  ],
  glossary: { "proofing": "Letting shaped dough rise before baking." },
  log: { qa: [], versions: [] }
};
</script>
```

4. Mark up what the page holds; you write no script for sorting, filtering, tooltips or rulings. `references/components.md` lists every part, the attribute that turns it on, and the keyboard shortcuts. A long page is split into named tabs: list them in `PB_CONFIG.tabs` (`[{ id: "stores", label: "Stores" }, ...]`) and mark each block of the page `data-pb-tab="stores"`; the include file adds the Log last. Content no tab claims stays above the tab bar. With one tab, keep naming it with `PB_CONFIG.tab`.
5. Check the layout at three widths before you publish (see `references/layout.md`, "Check before publishing"). The demo page's self-test (`assets/demo-page.html#selftest`) shows what a passing page looks like.
6. Publish with the capabilities the page uses, under the account `publish.home` names. Add a line to `log.versions`, and republish an existing page only as `publish.republish` says.

Pages made from a ready-made Artifact type (slides, documents, sheets, a design canvas) are outside stagecraft: the type owns its page. So is a seat's parley: the parley skill's template builds that page and carries its own header, so the include file is never added to a parley and the parley skill's rules govern it. A page that should stay bare (a moved notice, a one-line status page) carries `<!-- stagecraft: exempt (reason) -->`.

## Judgement the settings leave to you

Settings give defaults; these are the calls you still make for each page.

- **What the page is for.** Name the first tab for it. Lead with the three to six figures a reader would ask for first (when `tables.lead_with_cards` is on), each one a filter on the table below.
- **Which columns matter.** Give wide tables `data-priority` so a narrow screen drops the least important columns first.
- **What needs explaining.** Write tooltips as `reader.tooltip_coverage` says: how a derived figure was computed, what an abbreviation or status word means. Put recurring terms in the glossary once.
- **How the page is split.** One tab per question a reader comes with, named in their words. Do not split a page whose reader compares across the parts; do split one that scrolls past three screens of unrelated blocks.
- **What the Method tab says.** Write it as you would want to receive it with no context: each figure's rule in words, every typed or assumed value in its table, and a row added in the same change as the value. If a reader could not rebuild the page from it, it is not finished.
- **Which figures have a past.** Put the series on them, as far back as `reader.history_months` and the data allow.
- **Detail levels.** Mark blocks `l1`, `l2`, `l3` so the detail slider has something to do: the headline at zero, the working at three.
- **Filters focus.** A click on a card or chip shows only that value; a second click clears it; Ctrl-click adds one. Do not build filters that start with everything ticked.
- **Rulings start empty.** Never preselect Approve, Hold or Strike for the reader.
- **Shortcuts you add.** `PB.keys.add(key, label, fn, { id: "totals" })`: give it an id that never changes, and a plain default key that no built-in shortcut holds (`references/components.md` lists them).

## What a served page must not carry

The source of a page is readable by everyone the page is shared with. A kit or template that keeps its history as comments ("Name 2026-11-04: the ruling...") puts that history, and the owner's name, into the source of every page built from it, where no reader sees it on the page and anyone can read it in the source. Keep names and dated rulings in the skill text, not in anything a page is built from.

`scripts/served_scrub.py` removes every comment (HTML, CSS and JS) that names the owner, and touches nothing else: not text, strings, attributes or code. The words that name the owner are the person's own list, one regular expression per line, in `scrub_terms.txt` beside the script or in `~/.stagecraft/`, because no file of the skill may name anyone; with no list it changes nothing. `python scripts/served_scrub.py page.html` is a dry run that says what would go and how many mentions outside comments it leaves; `--apply` rewrites the page and saves the original (`--backup-dir`). An exempt marker keeps its marker and loses a reason that names the owner. A page the script cannot read (an unterminated string or comment) is left as it was. `python tests/test_served_scrub.py` tests it on made-up names.

## The publish check

`hooks/stagecraft_gate.py` is optional and acts as `check.mode` says: it reminds, refuses, or stays out of the way. It looks for the four core marks, for the layout mistakes of `references/layout.md` that can be seen without opening the page (a page that carries the older parley header beside Stagecraft's own is counted among them: a reminder naming the fix, a refusal when `check.mode` is refuse), for a declared tab that has no content, and (as `method.tab` says: reminder, refusal or nothing) for a page that shows data and has no filled Method tab. Installing it is a change to the person's settings file, so it is theirs to run: hand them the one command, do not install it yourself.

## Files

| File | What it is | Read it when |
|---|---|---|
| `options/catalog.json` | Every setting, its default and its `recommend` text | First launch; when a correction might be a setting |
| `scripts/options.py` | Reads and saves settings | Before every build |
| `references/layout.md` | How a page fits its window; text blocks; tables; the pre-publish check | Before laying out any page |
| `references/components.md` | Every part, its attribute, the shortcuts; named tabs; the Method tab | While marking up a page |
| `references/publishing.md` | Which account, moving a page, redirect notices, publishing as another account | Before publishing, and whenever a page cannot be seen |
| `assets/stagecraft-snippet.html` | The include file | Building |
| `assets/method-skeleton.html` | The seven fixed Method sections, to copy and fill | Building any page that shows data |
| `assets/demo-page.html` | Every feature on made-up data, with a self-test and a filled Method tab | To see a part working |
| `tests/contrast_check.py` | Computes the palette's contrast from the include file and fails under the floor | After changing a colour token |
| `tests/check_syntax.py` | Runs `node --check` on every inline script of the include file and the demo | After changing the include file (needs node) |
| `tests/smoke_test.py` | Runs the options script, the injector and the publish check on a machine with none of your folders | After any change to the scripts |
| `scripts/served_scrub.py` | Takes comments that name the owner out of a page's source | Before publishing a page built from a kit or template that keeps history in comments |
| `tests/test_served_scrub.py` | Tests the scrub on made-up names, then on any page you name | After changing the scrub |

## Limits of this release

- The include file was tested in headless Chrome against a stand-in for the capabilities. Rulings, options that follow a reader across browsers, and Send to Claude have had one person's first look in the real viewer and no more.
- The layout rules, the long-text rule for tables, the floating "data through" block and the clear band are in the include file and tested in headless Chrome at three widths. Firefox and Safari have not been tried, and the cut of a long column depends on how the browser sizes a table cell.
- The include file widens a narrow text block and reports what it could not fix (`PB.layout.report()`), but it cannot see a band of wasted space beside squeezed content, and the publish check reads only a page's own style blocks and inline styles. The pre-publish check in `references/layout.md` is still worth doing by eye.
- The link rule (principle 3a) rests on the browser's documented behaviour (a link that keeps its opener is not handed to an installed app); it has not yet been watched working in a browser that has the app installed.
- A countdown "only when the click moves the item" cannot be detected: mark such a rulings table `data-pb-ruling-moves`, or it saves at once.
- Column reorder and hide need a simple table (one header row, no merged cells) and have no touch gesture.
- The page cannot open the print dialog itself; the print style sheet applies when the reader prints from the browser (every tab is printed, each under its label).
- The tabs, the list of shortcuts, Bind Shortcuts and the Method tab were tested in headless Chrome with real mouse, key and touch events; they have not been looked at in the real viewer, in Firefox or Safari, with a screen reader or on a real touch screen. A page with one tab does not mark its first tab as selected until a tab is chosen (as in 0.3.1; a page with named tabs does).
- The one-header rule and the list-and-slider rule (0.3.4) were tested in headless Chrome only, against version 2.12 of the parley skill's header snippet. A hand-made page that still holds the older header is cleaned at run time, but the older script has already run by then: it keeps its own copies and its own storage keys (parley-detail, parley-railpos), which Stagecraft does not clear. The held slider has not been watched on a real small monitor.
