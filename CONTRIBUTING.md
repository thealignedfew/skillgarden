# Contributing

Thank you for looking. This repository is maintained by a small team and by the agent sessions that use these skills every day, so the review loop is short and plain.

## What helps

- A bug report with the skill name, the agent and model you ran it with, what you expected and what happened.
- A pull request that changes one skill for one reason, with the reason in the commit message.
- A new skill that solves a problem you actually had, in the same shape as the existing folders: `SKILL.md` first, a `README.md` with the install step, scripts under `scripts/`, assets under `assets/`.

## What we hold to

- A skill is read by an agent with no other context. Every instruction in it must stand on its own.
- No secrets, no transcripts, no telemetry, no personal data in any commit. The maintainers scan for these before merging and will ask for a rewrite rather than edit a submission.
- Plain prose. Say what the thing does and why, not how clever it is.
- Keep the licence header of a folder as it is; a new folder takes the repository licence (Apache-2.0) unless there is a stated reason for another.

## Licence of contributions

By opening a pull request you agree that your contribution is licensed under the licence of the folder it lands in (Apache-2.0 for the repository, or the folder's own `LICENSE` where one exists). You keep your copyright.
