# Layout: how a page fits its window

Read this before laying out a page. The settings named here (`layout.*`, `tables.*`) are in `options/catalog.json`; `python scripts/options.py show` prints the person's values. Where this file says "by default", the setting can say otherwise.

## The one idea

A reader opens a page in whatever window they have. The page's job is to use that window: show everything, cut nothing off, and not leave a band of empty background beside content that is squeezed. Prose, cards and controls are flexible, so they do the adapting. A table is not flexible in the same way, so it follows its own rules (below).

Think of each block as answering two questions: how wide is the thing I belong to, and what else could share my row?

## Text blocks

**A paragraph is as wide as the block it belongs to or introduces** (`layout.text_blocks: match`). An introduction above a row of cards and a table spans the same width as those cards and that table. Its left and right edges line up with theirs.

The mistake this rule exists for: a heading and an intro paragraph capped at a reading width (a `max-width` of 60 or so characters) sitting above content that runs the full page width. The paragraph wraps to five lines in the left half of the row, the right half is empty, and the page looks broken, because the eye reads the empty half as a missing element. It usually happens because a "comfortable measure" rule written for articles was applied to a dashboard.

What to do instead, in order of preference:

1. **Let the text run the width of its block.** A two-sentence intro across a 1,200 pixel row is two lines. That is fine: short text on long lines is not a readability problem.
2. **Give it a neighbour** (`layout.spare_width: side_by_side`). If the intro is long enough that full-width lines would be tiring (more than about four lines at full width), put it in a row with something that belongs beside it: the page's links, its key facts (data as of, source, snapshot date), the summary cards. Two columns on a wide window, stacked on a narrow one.
3. **Shorten it.** An intro that needs a reading measure on a dashboard is usually three ideas; move two of them into tooltips or the detail levels.

Only a page that is prose from top to bottom (`layout.page_width: reading`) uses a reading measure, and then the whole column uses it, centred, so nothing is wider than the text. A person who wants capped paragraphs everywhere sets `layout.text_blocks: measure`; the cap is `layout.measure_ch` characters. One block that should stay narrow on an otherwise matched page carries `data-pb-measure`.

The classes that do the arranging: `pb-row` puts its children side by side while each can keep a readable width and stacks them when it cannot (`pb-grow` gives a child a double share, `pb-fit` lets it keep its natural size); `pb-grid` flows cards into as many columns as fit; `pb-facts` holds label and value pairs that wrap as a unit.

Other text-block cases:

- **Metadata lines** (data as of, generated at, snapshot dates) are facts, not prose. Put them in the header or a small facts row, not at the end of a paragraph where they force a wrap.
- **Code-like fragments inside prose** (keys, ids, file names) must be allowed to break (`overflow-wrap: anywhere`) or they push the block wider than the window.
- **A label and its value** stay on one line together; let the pair wrap as a unit, never the label from its value.

## Page width and spare space

By default (`layout.page_width: wide`) the content area grows with the window up to `layout.max_width_px` (1440), centred, with a clear band each side (128 pixels on a window wider than 1140, otherwise a gutter that never drops below 16). `fill` removes the cap; `reading` is one 980 pixel column. The reader switches per page in Options or with the w key. Do not centre a narrow fixed-width column in a wide window and leave the rest black.

When the window is wider than the content needs, spend the width before leaving it empty:

- Cards flow into more columns (a grid with `auto-fit` and a sensible minimum, not a fixed count).
- Short sections sit side by side.
- A table that is narrower than its row does not stretch to fill it (stretched columns are harder to read across); it takes its natural width and the space beside it can hold its filters or cards.

When the window is narrower than the content needs, give up things in this order: side-by-side blocks stack; card columns reduce; low-priority table columns drop (with a chip to restore them). Density does not change by itself: it is the person's setting (`layout.density`) and the reader's choice in the Options panel. Font size for body text is the last thing to shrink, and never below 13 pixels.

## Floating things and the band around them

Some parts of a page float at an edge and stay in view while the page scrolls: the detail slider, the "data through" dates (`freshness.placement`), a back-to-top button. A page that fills the window must still leave them room.

- **Keep a clear band of `layout.float_gap_px` between the content and every floating thing, on the left and on the right.** The content area's width is the window minus the floating things minus that band on each side. A page widened to "fit the screen" that ends a few pixels from the detail slider is the mistake this rule exists for: the slider looks like part of the nearest card, and a click meant for one lands on the other.
- Keep the band symmetric. If something floats only on the right, the left still gets the same band, so the content stays centred between equal margins.
- Floating things never cover content. If the window is too narrow for content plus band plus a floating block, the block moves into the page flow (the dates go to the header, the slider to the toolbar); it does not sit on top of a table.
- Two floating things on the same edge stack with the same band between them; they do not overlap.

**Options and Shortcuts stay in reach** (`reader.floating_menu`). Once the header's Options and Shortcuts buttons have scrolled out of view, the same two controls show again, in the same order as the header: Options first. On a window 1141 px wide or more with the slider floating they are two small tabs (96 by 72 px together), Options above Shortcuts, at the top of the slider's band, with the slider moved down if it would come within the band of them (this happens below a window height of about 544 px; they are not offered under about 440 px, where the strip is used, except while the list of shortcuts is open: then they float and the slider is held at the top). On any other window they are a strip 40 px high fixed at the top of the content column, between the content's own edges, Options at its left end, and the page keeps scroll padding so a jump to an anchor is not hidden under it. The Options panel opens beside its tab. Nothing floats over content in either form.

**The list of shortcuts** (`reader.floating_list`). The Shortcuts control (the lower tab, the strip's second tab, the header button, or the `?` key) toggles the list of keyboard shortcuts on screen. It is not a window and not a panel: it hangs directly under the control that was used, and it stays there while the reader works, until the same control, `?` or Escape closes it. It is one box drawn from one registry, in one of three places:

- **In the left band**, when the tabs float and there is room. Top to bottom: the tabs, the list (224 px wide, never shorter than 168 px, scrolling inside itself when the window is short), the data-through block when `freshness.placement` is `float_left`, then the slider, with `layout.float_gap_px` between each. The left band grows to the list's width plus 8 px and the right band grows with it, so the content stays centred. While the list is open there its tabs stay on screen. It is there whenever the left band exists: the slider floats at the left (the reader has not pinned it, the window is 1141 px wide or more) and the content column beside the wider band stays at least 640 px wide, which at the default band is a window of 1168 px (at a 48 px band, 1200 px). The slider never lies under the list. With room for both (the tabs 84 px, the band, the list, the band, the slider at its real height, and 12 px at the foot; the list may shrink to 168 px, or to its real height when that is less, and scrolls inside itself) the slider starts below the list with the band between, and moves back when the list closes. Without room (a window about 640 px high or less at the default band; more with a larger band, and more again when the data-through block floats at the left) the slider is held at the top of the page, exactly as its own Pin to top button would hold it, for as long as the list is open, and goes back to the side when the list closes. That hold is not the reader's choice and is not stored: a reader who had pinned the slider stays pinned (and then there is no left band, so the list is in the page as below), one who had not gets it back unpinned. The smallest window the band holds is 296 px high at the default band. The header button opens the list here too, and brings the tabs with it, so that the page does not change width when the header scrolls away.
- **In the page, directly under the header**, wherever there is no left band (a window under 1168 px wide, the slider pinned to the top by the reader, no slider, the floating menu off, a window under 296 px high). It is a block in the page flow, so it pushes the content down and covers nothing; its columns are at least 200 px wide, it is at most 46 percent of the window height (420 px) and scrolls inside itself, and at 520 px it is two columns that a thumb can scroll.
- **Pinned under the strip**, once the header has scrolled away in that window (at the top of the content column when the tabs float but the band has no room). The same block turns sticky: it keeps its place in the flow, so it takes its own height out of the page and the content that was in view slides down by that height instead of being covered, and it stays at the top of the window while the page scrolls. Closing it slides the content back. Scroll anchoring is switched off while it is pinned so that the browser does not undo the push.

Open or closed is remembered per page and "Reset all options" resets it. With `reader.floating_list` off the list is never in the left band and is forgotten on reload.

**The "data through" block.** One line per source: its name and the last date its data covers. One source: one line, "Data through 30 Jan". Several: list them oldest first, and mark any source that is behind the others. This is the date the data covers, not when the page was published or the query ran; if those differ in a way that matters, the publish time is in the header. A page with no data (a form, a note) has no block.

## Tabs

A long page is split into named tabs (`PB_CONFIG.tabs`; `references/components.md` has the markup). What the page does with them:

- **The intro stays.** Content that no tab claims (the title, a lead paragraph) sits above the tab bar and shows on every tab, including the Log. Keep it short: it is the part every tab pays for.
- **The tab bar never pushes the page sideways.** On a narrow window the tabs wrap onto further rows (eight tabs take two rows at 520 px and still do at 400). Use names that are short and in the reader's words, and merge tabs before a third row appears at 520 px.
- **A tab is measured when it is shown.** A tab that has never been shown has no layout, so its tables have no width until it is shown; the include file fits them, and re-measures the floating things, at the moment of the switch. Do not read a size out of a hidden tab yourself.
- **A link or an address that points into a tab that is not showing** opens that tab first (`#tab-<id>` for a tab, `#<id>` for an element in one).
- **Printing shows every tab**, one after another, each under its label as a heading (a tab that already opens with a heading of its own name gets no second one), then the Log. The tab bar and every floating control are left out.
- **Prose tables.** A table whose cells are sentences (the Method tab's tables) is marked `data-pb-prose`: its rows wrap, it keeps its sorting and filtering, and in a column narrower than 640 px each row becomes a small card. Every other table follows the one-line rule above.

## Nothing is cut off

- No fixed heights on blocks that hold text. A fixed height plus more text than expected is the usual cause of clipped content.
- No `overflow: hidden` on a container whose content you did not size yourself.
- A sticky header or toolbar must not cover the first row of what scrolls beneath it: give the scrolling content matching top padding.
- Long words, ids and URLs wrap; a single unbreakable string must never set the page width.
- Pop-ups (tooltips, menus, the Options panel) are placed inside the window: flipped or shifted when they would cross an edge.

## Tables

A table is read by row, so by default (`tables.rows: one_line`):

- **Each record stays on one line.** Body cells do not wrap.
- **Header text may wrap.** A header is read once; two-line headers are how narrow numeric columns stay narrow.
- **Columns size to their content**, numbers right-aligned, with the total row and currency label as `numbers.*` says.
- **The table is never inside its own scroll box and never has a maximum height.** One scroll bar per page. A long table is filtered, not boxed.

**When one field holds long text** (`tables.long_text: shrink_then_widen`), go down this ladder and stop at the first step that fits. A table that fits at its natural width is left alone: the ladder starts only when the table is wider than its row.

1. Reduce the font size of that column only, one pixel at a time, to no smaller than `tables.min_font_px`.
2. Give that column more width by taking it from other text columns, never from columns that hold numbers or dates.
3. Cut the text at the column edge with an ellipsis and put the full text in the cell's tooltip.

A long column is one with a cell of 40 characters or more; mark a header `data-pb-long="1"` or `"0"` to say so yourself. If the table still does not fit after the ladder, `tables.narrow_screen` decides what gives.

The reason for the order: a note column in a smaller font is still readable and still one line; a note column that takes half the table pushes the figures the reader came for off the screen.

**On a narrow screen** (`tables.narrow_screen: drop_columns`): mark columns with `data-priority`, highest number dropped first, and keep the identifying column and the main figure. The reader gets a chip that brings hidden columns back.

What tables are exempt from: the "text matches its container" and "fill the width" rules above. A table does not reflow its rows to fit, and it does not stretch to fill a wide row.

## Check before publishing

Until the include file and the publish check do this for you, do it yourself. Open the page (or reason through its CSS) at about 400, 900 and 1,500 pixels wide and answer:

1. Is any block narrower than about two thirds of its row while its neighbours above or below span the full row? Fix it by rule "Text blocks".
2. Does anything scroll sideways, or is any text clipped at an edge or by a fixed height?
3. Is there a band of empty background wider than a card beside content that wraps or is squeezed?
4. Does any table row wrap to two lines (when `tables.rows` is `one_line`)? Is any table inside a scrolling box?
5. Does a sticky bar cover content? Does a pop-up leave the window?
6. Is there a clear band (`layout.float_gap_px`) between the content and each floating control, on both sides, at every width? Open the list of shortcuts at the same widths: does it cover anything (the detail slider above all), or push the page sideways?
7. Does the page say what date its data runs through, for each source?
8. With named tabs: at 400 px is every tab reachable without sideways scroll, and does every declared tab hold content?

If the person sends a screenshot of a page that "looks strange", start with question 1: it is the most common one.
