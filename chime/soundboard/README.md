# The Soundboard

`SOUNDBOARD.html` is a control page for chime. It shows every sound event with a mute, a mute for each account's low-usage alarm, a clock in and out, and the names chime uses for desktops and sessions. For each sound you can replace it with your own file (browse or upload an mp3 or wav, up to 5 MB), generate a tone in one of eight styles (with a preview in the page), or reset it to the default. The page ships no audio and plays only tones it builds itself, from the recipe chime prints.

## What it is, and what it is not

It is a published page, not a program on your PC. A page cannot run commands on your machine, so a button writes a request document into the page's own database, and the Claude session that published the page applies the request at its next check, or at once when you press "Push now with a comment" and send the comment to Claude. The page says "requested, applied at the next check" until chime's own state confirms the change.

The page is published by your own Claude session as an artifact, with these capabilities (exactly):

```
capabilities: {"db": {"rules": [{"path": "", "read": "view", "write": "admin"}]}, "assets": {}, "user": {}, "comments": {"composer_only": true}}
```

- `db` holds the requests and the state documents. The rule lets only editors write, because every request ends as a command on your PC.
- `assets` (editors only) carries the audio file you pick for Replace. The artifact asset store takes no audio type, so the page wraps the file in a small JSON envelope (see `CONTRACT.md`, section 4) and the sync script unwraps it.
- `user` gives the viewer id written into each request. `comments` is used only by the "Push now" button.

Every control that needs a capability the view lacks is off, with a reason, and a line at the top says what the view can do.

## Publish it

1. Copy `SOUNDBOARD.html`, fill in the block that starts `var AH =` (your session name, its full session id, your account, optional questions link), and publish it with the capabilities above.
2. Keep the session that published it as the page's owner session. It applies the requests.

## How the owner session applies requests

At each check (and whenever you comment on the page):

1. Read the page's pending requests. The older kinds carry `kind`; run `python scripts/soundboard_sync.py apply requests.json --out results.json` on those. It leaves the newer kinds alone.
2. Write the pending requests that carry `type` (`usage_mute`, `sound_replace`, `sound_generate`, `sound_reset`) into one file and run `python scripts/soundboard_sync.py requests FILE --assets-dir DIR --out PLAN --seat <your seat name>`. `DIR` is a scratch folder you keep for the check.
3. Read the plan. A request marked `failed`: mark it failed with the plan's `result` and run nothing. `blocked`: the uploaded file is not in `DIR` yet; save the asset there (read the artifact's asset by its id into `DIR`), then run step 2 again. `ready`: run the plan's `command_line` yourself. Exit 0: mark the request `done` with the command's one line as `result` and `done_at` now. Any other exit: mark it `failed` with the command's message.
4. When all commands have run, run `python scripts/soundboard_sync.py state --out-dir DIR`, then write `DIR/usage.json` to the page document `state/usage` and `DIR/sounds.json` to `state/sounds`, and `python scripts/soundboard_sync.py roster --out DIR/roster.json` to `state/roster`. If `state` prints a PROBLEM line, leave that document as it was and say so.
5. Write state first, then mark requests done, so the page never shows a change that the state has not caught up with.
6. Never run a command that is not in the plan, and never run `usage mute` or `sounds set` for a request the plan did not mark `ready`. The commands only change files under your chime home, never the skill folder.

The account names the page shows come from the config key `account_names`, and the sessions it lists from the config key `transcripts_glob` (see `references/config.md`). Nothing about your accounts is built into the page or into the sync script.
