# chime

Audible alerts and toasts for Claude Code sessions. When you run several sessions at once, each kind of moment has its own sound, and a toast names the session, so you can tell from across the room which one needs you and how badly: a decision is waiting, a session is blocked, your own prompt has finished, a loop is ticking, an account is near its usage limit, a session found a material risk.

A fresh install makes sound with nothing downloaded and ships no audio: every event plays a short tone that chime generates itself on first use. You can give any event your own mp3 or wav, or another generated tone, from the command line or from the Soundboard page.

## What you get

- One script, `scripts/chime.py`, run by three Claude Code hooks (Stop, UserPromptSubmit, PreCompact). It never blocks or fails a session: every hook mode exits 0.
- 21 sound events, a toast per turn that needs you, spoken session names, and a mute for Zoom meetings, dictation, and a clock-out.
- A low-usage alarm with a per-account mute (it needs a usage reader you name; see `references/usage.md`).
- RED ALERT, a first-line phrase with a log of every firing and of your verdicts.
- The Soundboard, a control page that your own Claude session publishes as an artifact (`soundboard/`).
- An optional script that fetches third-party sound clips for your own local use (`scripts/fetch_clips.py`).

## What it needs

- Windows for sound and toasts (PowerShell, the Windows media player, `winsound`). On other systems the script decides but cannot play.
- Python 3 (tested on 3.11). Only the standard library. The optional spoken names use the `edge-tts` package if you have it installed, and fall back to the Windows voice if not.
- Claude Code with hooks.

## Install

1. Copy this folder to `~/.claude/skills/chime/` (on Windows `%USERPROFILE%\.claude\skills\chime`), or to the `skills` folder of another Claude Code account home.
2. Add three hooks to that account's `settings.json`. They are shown, with the exact JSON, in `SKILL.md` under "Install". Hooks are never added for you: an agent that installs this shows you the edit and waits for your yes.
3. Try it: set `CHIME_DRY_RUN=1` and see `SKILL.md`, "Verifying", or just finish a turn and listen for the tone.

Your own settings, your sound files and the tones chime generates live in `~/.threadops/chime` (or the folder named by `CHIME_HOME`), never in the skill folder, so you can replace the skill folder with a newer one at any time and lose nothing. `SKILL.md` explains this, and what an agent should do when you ask it to customise chime.

## The optional clips

`scripts/fetch_clips.py` can download third-party sound clips named in `clips.json` into your sounds folder, if you want recognisable sound effects instead of generated tones. You run it yourself; nothing runs it for you; and this repository contains no audio. The clips are third-party sounds that you fetch for yourself. They are owned by others, you download them for your own local use, you are responsible for that download, and nothing here grants a licence to them. `clips.json` lists names and source addresses only, and an entry without an address cannot be fetched. As shipped, the list names 21 clips and gives no address for any of them: add a `source_url` for the ones you want in your own `<chime home>/clips.json`.

## The Soundboard

`soundboard/SOUNDBOARD.html` is a single page: every sound with a mute on it, a mute for each account's low-usage alarm, your clock in and out, and for each sound a way to replace it with your own file (browse or upload an mp3 or wav), generate a tone locally, or go back to the default. A page cannot run commands on your PC, so it writes requests into its own database, and the Claude session that published it applies them with `chime.py`. `soundboard/README.md` says how, and `CONTRACT.md` pins the request documents.

## Files

| Path | What it is |
|---|---|
| `SKILL.md` | what an agent reads: how it works, install, the commands, the two rules every session follows |
| `chime.json` | the skill's defaults (every event is a generated tone) |
| `clips.json` | the optional clip list |
| `scripts/chime.py` | the hook script and the commands |
| `scripts/migrate_config.py` | moves choices out of an old skill folder's `chime.json` into your chime home |
| `scripts/soundboard_sync.py` | the bridge between the Soundboard and chime |
| `scripts/fetch_clips.py` | the optional clip fetch |
| `references/` | the long mechanics: sounds, loops, usage, red alert, configuration |
| `soundboard/` | the control page and how to publish it |
| `CONTRACT.md` | the commands' JSON and the Soundboard's request protocol |

## Licence

Apache License 2.0, as the rest of this repository (see the `LICENSE` file at its root). The licence covers the code and text here. It does not cover, and this folder does not contain, any third-party sound clip that `fetch_clips.py` may download for you.
