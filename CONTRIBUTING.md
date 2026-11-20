# Contributing

Thank you for looking. This repository is maintained by a small team and by the agent sessions that use these skills every day, so the review loop is short and plain.

## How to propose a change

1. Fork the repository and make your change on a branch of your fork.
2. Change one skill for one reason. Put the reason in the commit message and in the pull request.
3. Make the change against the public skill as it is in this repository, never against a copy you have customised for yourself.
4. Open a pull request from your fork. Say what you changed, why, which agent and model you ran the skill with, and how you tested it.
5. A maintainer reads it, runs the skill's own checks and its tests, and answers in the pull request. You may be asked to change it.

A pull request can come from a person or from the agent that person works with. When an agent has made a significant improvement to a skill, the skill tells it to offer once to propose it, to say what would be shared, and to send nothing without its person's yes (see the section "Propose improvements upstream" of each skill). The offer is always the person's to accept or decline.

## Every pull request is reviewed and tested; none is merged automatically

Every pull request is read by a maintainer and tested before any merge. No pull request is merged automatically: not by a bot, not by a script, and not because an agent or a test said it was fine. A maintainer may ask for changes, may split a change, and may decline one without giving more reasons than the ones on this page.

## What is refused

A change is declined, whatever else it does well, if it:

- reads credentials, tokens, keys, cookies, password stores or the contents of another program's private files;
- sends data anywhere: no network call that carries what a session, a transcript, a path, a name or a setting contains, no telemetry, no "phone home", no upload to a service the person did not name;
- changes settings silently: a hook, a permission, a settings file, an environment variable, a schedule, or any file outside the skill's own folder and the person's own skill folder, without showing the person the exact change and getting their yes first;
- downloads and runs code, or loads and runs code from an address, a package it installs on its own, or a file it fetched. A script that downloads data (for example audio the person asked for) must only save it, must check what it saved, and must never run it;
- hides what it does: obfuscated code, encoded commands, behaviour that differs from what the skill's text says.

## What helps

- A bug report with the skill name, the agent and model you ran it with, what you expected and what happened.
- A pull request that changes one skill for one reason.
- A new skill that solves a problem you actually had, in the same shape as the existing folders: `SKILL.md` first, a `README.md` with the install step, scripts under `scripts/`, assets under `assets/`, long mechanics in `references/`.

## What we hold to

- A skill is read by an agent with no other context. Every instruction in it must stand on its own.
- A skill is generic. It names no person, account, machine, folder of yours, company or private tool. What is particular to one household belongs in that household's own private skill, not here.
- No secrets, no transcripts, no telemetry, no personal data in any commit. The maintainers scan for these before merging and will ask for a rewrite rather than edit a submission.
- No audio, images or other media that you do not own and may not licence. If a skill can use third-party media, it ships a list of names and a script the person runs themselves, and says so plainly.
- Plain prose. Say what the thing does and why, not how clever it is.
- Keep the licence header of a folder as it is; a new folder takes the repository licence (Apache-2.0) unless there is a stated reason for another.

## Two sections every skill carries

Every skill in this repository carries the same two sections, so an agent that reads any of them finds the same rules. Their intent:

- **Your settings live outside this folder.** A skill folder is replaced whole at every update. Local configuration, decisions, tweaks and files must therefore never be kept inside it. They go in a per-person folder (`~/.threadops/<skill>`, or the folder named by `<SKILL>_HOME`), and a household's own rules go in a small private skill named `<skill>-house`. An agent that is asked to customise a skill writes in those places only. A pull request that makes a skill keep a person's own data inside its folder will be declined.
- **Propose improvements upstream.** When a person or their agent makes a significant improvement, the agent offers once to propose it here as a pull request from a fork, says what would be shared, sends nothing without the person's yes, and puts nothing personal in it.

## Licence of contributions

By opening a pull request you agree that your contribution is licensed under the licence of the folder it lands in (Apache-2.0 for the repository, or the folder's own `LICENSE` where one exists). You keep your copyright.
