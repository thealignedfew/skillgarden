# Components: what the reader gets, and what you write for it

You write no script for these. Mark the table, the figure or the card with the attribute in the right-hand column and the include file does the rest. Defaults named here (the filter box threshold, the countdown, money formats) come from the person's settings; `PB_CONFIG.defaults` carries them into the page and the reader can change them in the page's Options panel. `BUILD_NOTES.md` is the full reference.

| Part | What you write |
|---|---|
| Header: who made the page, whether a session is watching, how old the data is | `PB_CONFIG.header`. Write `heartbeat/owner` in the page's database on every check so the status stays true. Set `published` to `YYYY-MM-DD HH:MM` plus EST, EDT, ET or nothing: a page published a minute ago says its author is live from that time, before the first check. This header replaces the older artifact header of the parley skill: a page never carries both (two header boxes, two sliders, two Pin to top buttons). `scripts/inject_stagecraft.py` removes the older header and carries its author values into `PB_CONFIG.header`; the publish check reminds about a page that has both. |
| Options panel (gear button, or `o`) | Nothing. Add a page option with `PB.options.add({name, label, default, section, onChange})`. |
| Shortcuts (the header button after Options, the lower floating tab, or `?`) | Nothing. It toggles a list of the shortcuts that apply to this page, right under the control, and the list stays there while the reader works. There is no Shortcuts panel. |
| Options and Shortcuts that follow the reader | Nothing. Once the header buttons have scrolled away the same two controls show again, Options first (small tabs at the left edge, Options above Shortcuts, or a strip); `reader.floating_menu` switches them off. |
| Bind Shortcuts (an entry in Options) | Nothing. The reader presses a key button, then the new key; a taken or browser-owned key is refused with a line that says why. `reader.bind_shortcuts` locks it; `reader.shortcut_keys` gives the starting keys. |
| Tab name | `PB_CONFIG.tab`: for a page with one tab, name it for what the page is ("Weekly review", "Bank audit"), from the context you are working in. |
| Several named tabs | `PB_CONFIG.tabs: [{ id: "stores", label: "Stores" }, ...]` and `data-pb-tab="stores"` on each top-level block of the page. |
| Method tab | `{ id: "method", label: "Method" }` in `PB_CONFIG.tabs` and the seven sections of `assets/method-skeleton.html`, filled, as plain text. |
| Table of sentences | `data-pb-prose` on the table: its rows wrap (used for the Method tab's tables). |
| Log tab | `PB_CONFIG.log.qa` (question, answer, what changed) and `log.versions`. The reader can hide the tab; `log: false` leaves it out. |
| Detail slider | Classes `l1`, `l2`, `l3` on blocks: the lowest level that shows the block. Zero shows only what has no class. One slider, with one Pin to top button; the open list of shortcuts never covers it (it moves down, or is held at the top while the list is open when the window is too short for both). |
| Themes | Nothing. Auto follows the browser; the reader can pin Dark or Light. |
| Tables | Nothing. Every table sorts by header, gets a filter box above 8 rows, copies as CSV, and is never inside a scroll box. |
| Column reorder and hide | Nothing. Ctrl-drag a header moves it, Ctrl+X over a header hides it, a chip restores hidden columns. |
| Fit to width | `data-priority="1..n"` on the `th` of columns that may drop on a narrow screen, highest number first. |
| Tooltips | `data-tip="text"` on any element; `data-series="1,2,3"` adds a sparkline with first, last, low and high; `data-source` and `data-asof` add a footer. Glossary terms are marked for you. |
| Sparklines in the page | `<span data-spark="1,2,3"></span>`. |
| Summary cards that filter | `<div class="pb-cards" data-target="#table">` holding `<button class="pb-card" data-filter="Region=North">`. |
| Chips and legends | `<div class="pb-chips" data-target="#table" data-column="Status"></div>`: one chip per value, with counts. |
| Signed rulings | `data-pb-rulings="reviews/q3"` on a table. Each row gets Approve, Hold and Strike. |
| Ask card | `<section class="pb-ask" data-id="q1" data-title="..." data-question="..." data-dflt="..."></section>`. What a reader types in its box is kept as a draft until it is sent. |
| Comment shortcut | Nothing. Ctrl+Space, then C, comments on the element under the pointer or on the selection. Unsent text stays in the box (a draft) when it is closed or the page is refreshed. |
| Shortcuts | Nothing. Add one with `PB.keys.add("g", "Go to totals", fn, { id: "totals" })`: the id never changes, so a reader's own key for it survives an update. |
| Numbers | `data-money`, `data-total="USD"`, `data-pct`, `data-int` on a cell or any element. |
| View in the link | Nothing. Filters, sort, hidden columns, tab and detail level travel in the page's link. |
| Links to other pages | A plain `<a href>`. The include file decides how it opens (`links.claude_pages`); do not set `target` or `rel` yourself and do not use `window.open`. |

## Notes on a few parts

**The list of shortcuts.** One control, three ways in (the floating tab, the header button, `?`), one list, drawn from the one registry with the keys in use now. It hangs directly under the control: in the left band under the Shortcuts tab whenever the left band exists (the slider floats, the window is 1168 px wide or more; the slider moves down below the list, or is held at the top while the list is open when the window is too short for both; `layout.md` has the numbers), otherwise in the page directly under the header, and once the header has scrolled away pinned under the strip, where it takes its own height out of the page and pushes the content down instead of covering it. It is no taller than 46 percent of the window and scrolls inside itself. The same control or Escape closes it; open or closed is remembered per page and "Reset all options" resets it. With `reader.floating_list` off it is a plain drop-down that is forgotten on reload and never uses the left band.

**Bind Shortcuts.** In Options. A list of every shortcut that applies to the page, each with its key. The reader presses a key button and then the new key (or Ctrl+Space and a second key for the comment chord). A key that another shortcut holds is refused with a line that names it; so are the keys a page cannot or should not take: Escape, every key with Alt, function keys, Tab, Enter, Space, Backspace, Delete, the arrow and page keys on their own, Ctrl with a letter (Ctrl+W, Ctrl+T, Ctrl+N, Ctrl+R, Ctrl+L and the rest, except Ctrl+X, which is a shortcut already), Ctrl with a digit or punctuation key, and Ctrl+Shift with N, T, W, Q, B, O, I or J. Escape cancels a capture. A shortcut can be unbound, put back to its default, or all of them at once. The choice is stored per reader against the shortcut's id (`pb.<key>.keys`, mirrored to the reader's private record when the page has a database, like the other options), so it survives a republish; the list, the hint under the detail slider and the tooltips show the new key at once. `PB.keys.list()`, `.all()`, `.current(id)`, `.check(id, key)`, `.bind(id, key)`, `.unbind(id)`, `.reset(id)` and `.resetAll()` do the same from script. `reader.bind_shortcuts` off keeps the keys as the settings give them and greys the entry out; `reader.shortcut_keys` (a map from shortcut id to key, `""` for none) gives the starting keys.

**Shortcuts you add.** `PB.keys.add(key, label, fn, { id, when, order })`. Give an id that never changes. `when()` says where the shortcut applies (it is listed and works only there); `order` is its place in the list. The old form without an id still works and takes `key:<default key>` as its id. Return `false` from `fn` when there was nothing to do, so the key keeps its normal meaning. The ids of the built-in shortcuts are `shortcuts`, `options`, `theme`, `detail-less`, `detail-more`, `filter`, `tab-prev`, `tab-next`, `tab-1` to `tab-9`, `method`, `item-next`, `item-prev`, `approve`, `hold`, `strike`, `send`, `comment`, `copy-csv`, `restore-columns`, `hide-column`.

**The owner line.** On a page published from a live session the header says "Questions: the author's question page" and links it (`PB_CONFIG.header.questions`). On a page published headless (`header.headless` true) it says "Source: link" and "question page": link opens the page the copy was made from (`header.source`, an http or https address), the second link opens the author's question page. With one of the two addresses only that link shows; with neither the line is hidden. `header.questions_label` replaces the words "question page", and `header.questions_live` the words "the author's question page" on a live page (plain text, up to 40 characters, shown as text). The person sets both once in their own settings (`header.question_link_headless`, `header.question_link_live`); the injector writes them into the page's header when the page gives none.

**The author status.** The header counts the author as last seen at the later of the last `heartbeat/owner` check and the page's publish time (`PB_CONFIG.header.published`, as `YYYY-MM-DD HH:MM` plus EST, EDT, ET or nothing for the viewer's own time). Live up to one check period plus 10 minutes (the period from the heartbeat, else `header.period_min`, else 50), idle up to three periods, quiet after. A publish time that does not parse, or is more than 10 minutes ahead of the viewer's clock, is ignored; a headless page, a page with no database and a heartbeat that says it is not watching are as before.

**Named tabs.** List the tabs in `PB_CONFIG.tabs`, two or more, each `{ id, label }` (an id of lowercase letters, digits, `-` or `_`; `log` is reserved; the label is what the reader sees). Put `data-pb-tab="<id>"` on each top-level block of the page that belongs to a tab; several blocks may share one tab. Content that no tab claims stays above the tab bar. The Log tab follows the last tab. The shape of a page with one tab (`PB_CONFIG.tab`) is unchanged, and a `tabs` list with fewer than two valid entries is ignored with a warning. Tab ids are part of the reader's stored setup: do not rename them on an update. What the include file does: the ARIA tabs pattern (roles, arrow keys that wrap, Home and End); the chosen tab is remembered per page and shown in the address as `#tab-<id>` (`#log` for the Log); a link to `#<id>` of an element inside a tab that is not showing opens that tab first; in script, `PB.tabs.reveal(idOrElement)` does the same, and `PB.tabs.show(id)`, `.list()` and `.report()` (declared tabs with no content, and the Method tab's state) are there for your own shortcuts and checks. A tab that is declared and left empty is reported by the page's self-test, in `PB.warnings`, and by the publish check.

**The Method tab.** The tab that explains the page to a reader with no context and no tools. Its words are in the page source, as plain HTML text: the include file adds a contents bar and some styling and never a word, so an agent that only reads the file gets all of it. Declare `{ id: "method", label: "Method" }` (put it last before the Log) and copy the seven sections of `assets/method-skeleton.html`, each marked `data-pb-tab="method"` with its fixed id and heading:

| Id | Heading | What goes in it |
|---|---|---|
| `method-purpose` | What this page is for and who it is for | Two to four sentences: the question it answers, who reads it, what they decide, how often it is rebuilt. |
| `method-derived` | How each figure was derived | A table: figure, where it appears, the rule in words, the source. Say which figures are typed in and which are worked out. |
| `method-sources` | Sources | A table: source (as the page names it), what it is, how it was reached (route and account, never a credential), data through, owner. |
| `method-assumed` | Hard-coded and assumed values | A table: value, where it is used, why this value, who set it and when, when to revisit it. Every number or rule typed into the page or the code that built it. Add the row in the same change as the value. |
| `method-limits` | Limits: what this page cannot tell you | What is missing, late, estimated or out of scope; what a reader must not conclude. |
| `method-open` | Open topics | Unanswered questions, known defects and decisions waiting on someone, each with who it waits on. |
| `method-rebuild` | How to rebuild or extend this page | For an agent with no context: what to read first, what it needs and where to get it, the steps, what it must not change, what it must ask the owner for instead of guessing. |

A section that does not apply says "None"; a section that is left out or left empty (headings and table headers only, or a placeholder such as TODO) counts as a missing Method tab. Write for someone who knows nothing: say what a thing is the first time it appears, name the system and the field a figure came from, give a date or a version wherever it matters, write negatives in parentheses. Mark its tables of sentences `data-pb-prose`. `method.tab` decides what the publish check does with a page that shows data (a table with rows, a figure, a summary card, a trend mark or a data-through block) and has no filled Method tab: `recommended` (the default) reminds, `required` refuses, `off` says nothing. The demo page's Method tab is a complete example.

**Unsent text.** The answer box of an ask card and the comment box keep what the reader types as a draft in their browser, written a moment after the last keystroke and when the box loses focus or the page is hidden. It comes back after a refresh or when the page rebuilds the box, with one muted line under the box ("Draft kept in this browser, not sent yet") and a Discard button. It goes when it is sent or saved, discarded, emptied, or 30 days old; "Reset all options" does not remove it. Filter boxes are not drafts.
**Numbers.** Put the raw value in the attribute and let the library write the text; it formats as `numbers.*` says (decimals, negatives, where the currency is named). Do not format figures by hand: a hand-formatted figure ignores the reader's setting. Negative amounts are in parentheses unless `numbers.negatives` says otherwise, and the reader can switch that in the Options panel; this is the reason a negative must never be typed into the page as text. In the parentheses form a figure in a table cell that is not negative leaves room for the closing parenthesis, so the last digits (and percent signs) of a column line up; that room is invisible, is not in the copied CSV or what a screen reader says, and needs nothing from you.

**Links to other pages.** Every link opens in a new tab, so the reader keeps the page they were on. A link to another Claude page needs one more thing. When the reader has a Claude app installed (a browser web app or the desktop app), the browser hands an ordinary new-tab link to that app: the reader is pulled out of their browser, often into a different login that cannot see the page. A browser only does this for a link that does not keep its opener, so with `links.claude_pages` at `browser` (the default) the include file opens Claude links with the opener kept (`target="_blank" rel="opener"`), and they stay in the browser. With `app` it uses `rel="noopener"` and lets the app take them. Links to anywhere else always get `rel="noopener noreferrer"`. "A Claude page" means the host is exactly the Claude site or a subdomain of it, never a name that merely contains it. The reader can switch between browser and app from the page's controls (the Options label reads "Claude links open in"); the choice is kept in that browser for that page.

**Rulings.** A click is saved and the cell shows who ruled and when; another click changes it. Whether a click waits out a countdown with Undo is `feedback.undo_countdown`. Under its default (a countdown only when the click makes the row leave or move) the include file cannot tell which tables those are: mark such a table `data-pb-ruling-moves`, and every other table saves at once. Use `PB_CONFIG.signer_labels` to add a role or account label beside a name. Mark a finished review `data-pb-closed` so it shows the outcome without buttons. Read the answers at every check: the `answers` collection and each rulings path.

**Ask card.** State the default on the card (`data-dflt`): what happens if nobody answers.

**Log.** Add a line to `log.versions` on every republish and move answered questions into `log.qa`.

## Shortcuts

Each is listed in the page's list of shortcuts only where it applies, and each can be given another key in Options, Bind Shortcuts. The keys below are the defaults.

| Keys | What it does | Where it applies |
|---|---|---|
| `?` | Show or hide the list of shortcuts | Every page |
| `o` | Open the options | Every page |
| `t` | Change the theme: Auto, Dark, Light | Every page |
| `[` and `]` | Less and more detail | Pages with the detail slider |
| `/` | Focus the nearest filter box | Every page |
| `1` to `9` | Go to tab 1 to 9 (the Log counts) | Pages with named tabs, as many as there are tabs |
| `,` and `.` | Go to the previous and next tab (they wrap) | Pages with named tabs |
| `m` | Go to the Method tab | Pages with a Method tab |
| `n` and `p` | Go to the next and previous item waiting for you: an ask card with no answer, a review row with no ruling (a tab that is not showing opens first; the item is scrolled into view and takes the focus) | Pages with an ask card or a review table |
| `a`, `h`, `s` | Approve, hold or strike the review row in focus | Pages with an open review table; only when a row has focus and the reader may rule |
| Ctrl+Enter | Send the answer or comment being typed | Every page |
| Ctrl+Space, then `C` | Comment on the element under the pointer, or on the selection | Every page |
| Ctrl+Shift+C | Copy the table in focus, or under the pointer, as CSV | Pages with a table |
| `r` | Restore the hidden columns of the table in focus, or under the pointer | Pages with a table |
| Ctrl+X over a header | Hide that column | Every page |
| Ctrl-drag a header, or Ctrl+Left and Ctrl+Right on a focused header | Move that column | Every page |
| Arrow keys, Home, End on the tab bar | Move between tabs and select the one reached (the arrows wrap) | Pages with tabs |
| Escape | Close the options, a tooltip, the comment box or the list of shortcuts (the list only when none of the others was open); it cannot be bound | Every page |

Shortcuts work while the keyboard focus is inside the page. A plain key never fires while the reader is typing in a box, a text area, a drop-down or an editable element, nor while a key is being captured for Bind Shortcuts. On a Mac, Cmd stands in for Ctrl. Ctrl+Space is taken by some input-method switchers; where it is, the comment box is still on `PB.comment.open()` and can be given another key in Bind Shortcuts. Chrome also uses Ctrl+Shift+C to open its inspector; this draft was not tried in a headed browser, so if the browser takes that key before the page does, Bind Shortcuts moves the shortcut to another key.
