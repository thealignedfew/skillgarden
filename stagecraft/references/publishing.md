# Publishing: which account, moving a page, and publishing as another account

Settings: `publish.*` in `options/catalog.json`. Run `python scripts/options.py show` for the person's values.

## Why the account matters

A session is signed in to one account, and a page is visible only inside the organization of the account that owns it. Access follows the session's account, not the person: someone who owns a page under one login cannot read or update it from a session signed in as another. Most "I cannot see the page" and "it made a second copy" problems are this.

## Where a new page goes

Follow `publish.home`.

- `current` (default): publish under the account the working session is signed in to. A page for a session's own correspondence, an internal draft of a tool, a tracker the session maintains: all of these start in the workspace the session is in. Do not offer to put it elsewhere, and do not keep "a local file for now" because another account seems more official.
- `named`: publish everything under `publish.named_account`. If the session is not signed in as that account, use the route in "Publishing as another account" when `publish.other_accounts` allows it; otherwise say which account the page belongs to and stop.
- `ask`: ask once per page, then remember the answer in the page's own record.

Pages for people outside the person's own workspaces are a separate decision: name the audience, publish where the person says, and give them `publish.share_note`.

## When a session moves to another account

Follow `publish.when_session_moves`. With `redirect` (default), in the same turn the move is noticed:

1. Publish the page from its source under the new account. This is a new link.
2. Replace the old copy with a short notice: the page's name, "This page has moved", the new link, the date. Nothing else. The old copy is replaced, not deleted; deleting is the owner's own step. If the session can no longer write to the old account, use "Publishing as another account" when allowed, or tell the person in one line that the old copy still shows the last version and why.
3. Carry over what readers stored there if the page keeps answers or rulings in its database: read them from the old page and write them to the new one before the notice goes up.
4. Write the new link wherever the old one was recorded (notes, other pages that link to it).

Do the same for every internal page the session owns, not only the one being worked on. Do not ask first and do not offer a copy "if you want": two live copies drift apart within a day.

## Before a page goes out: the publish check

If the person has installed `hooks/stagecraft_gate.py` it reads two settings, and you should too (`python scripts/options.py show`):

- `check.mode`: `remind` publishes and prints what is missing, `refuse` also refuses a page with a layout mistake, `off` does nothing.
- `method.tab`: a page that shows data (a table with rows, a figure, a summary card, a trend mark or a data-through block) needs a filled Method tab. `recommended` (the default) publishes with a reminder; `required` refuses until the Method tab is there and every one of its seven sections has words ("None" counts; headings, table headers and placeholders such as TODO do not); `off` says nothing. The sections are in `assets/method-skeleton.html`; the notes on writing them are in `references/components.md`. A moved-page notice carries `<!-- stagecraft: exempt (reason) -->` and is not checked.
- A tab declared in `PB_CONFIG.tabs` that has no content is reminded whatever `method.tab` says.

Build the Method tab as you build the page, not at the end: every figure you add gets a row in "How each figure was derived", every number you type in or assume gets a row in "Hard-coded and assumed values", and a source that changes its date changes its row in "Sources". A refused page is fixed, not exempted; only the page's owner exempts a page.

## Updating a page

Update in place, at the same link. A different file path or a missing link creates a second page. Keep what readers' setups hang on unchanged: `PB_CONFIG.key`, table keys, tab ids, ask ids, rulings paths and the ids of shortcuts the page adds (the tab a reader was on is remembered under its id, and a reader's own key for a shortcut under the shortcut's id). Republish as `publish.republish` says; by default only when something a reader can see has changed. A heartbeat or a last-checked stamp is written to the page's database, not published. On every publish set the header's `published` to the time of the publish (`YYYY-MM-DD HH:MM` plus EST, EDT or ET): the header counts it as the author's first sign of life, so a page published a minute ago by a live session says the author is live before the first heartbeat exists. Publishing arms the comment watch only for a live session; a headless page sets the headless flag and says nobody is watching.

If `publish.version_in_title` is on, the page's name carries its version and changes on each real update; its link does not.

## Publishing as another account

Only when `publish.other_accounts` is `headless`.

1. Keep one configuration folder per login, each signed in once. The `CLAUDE_CONFIG_DIR` environment variable selects the folder, and with it the account.
2. Run a headless session with that folder: `claude -p "<instruction ending with a marker line>" --allowedTools "Read,Artifact" --permission-mode dontAsk --add-dir <folder of the page>`. Allow only what the publish needs; if the artifact tools reach the session through an MCP server, allow that server's tools as well. Never use a mode that skips permission checks. Do this once in a small helper script (find the folder, run the session, parse the markers, verify) rather than by hand each time.
   To update a page that already exists, the instruction must make the session read the page first and, when the read result says the whole page was saved to a file and that the version counts as viewed only once every line of it has been read, Read that whole file before the publish. A session that reads only the first part is refused with "You hadn't viewed the live version"; the fix is the full read, never a forced publish.
3. Prove the route read-only first (list that account's pages or read one), then publish, then verify with a separate read through the same route. Do not trust the publishing run's own report.
4. Parse the marker as a whole line. A substring test passes on a run that only mentions the marker.
5. Pin every scheduled publish to the owning account's folder. A job that uses whichever account the default login is on breaks the day someone signs in again.
6. Never read, print or copy the credentials file inside a configuration folder. Only ever point at the folder.
7. Set the header's headless flag on the page and declare no comment capability: nobody is watching a headless page, and it should say so. Also set `PB_CONFIG.header.source` to the address of the live page the copy was made from (`--source URL` on the injector): the header's owner line then reads "Source: link" and "question page" instead of "Questions: the author's question page".

When the same email address belongs to two organizations, name the configuration folder, not the email.

If the call is refused by the permission system, do not retry and do not try another form. Give the person the one line to run themselves and record the result they paste back.

## Sharing

Pages are private until the owner shares them from the page's Share menu; a session cannot share a page. When a page is meant for someone else, say so when you hand it over, with `publish.share_note`.
