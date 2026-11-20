# Changelog

## 0.4.0: first public release

This is the first version published outside the project it grew in. Versions 0.1.0 to 0.3.4 were internal drafts and are not listed.

What the release contains:

- The include file (`assets/stagecraft-snippet.html`): author header, Options panel, themes, sortable and filterable tables, column tools, tooltips with history, summary cards and chips, signed rulings, ask cards, named tabs, a Log tab and a Method tab, a detail slider with one Pin to top button, a list of shortcuts that can be rebound, drafts that survive a refresh, and layout rules that make a page fit its window.
- A catalog of 49 settings in nine groups (`options/catalog.json`) and the script that reads and saves them (`scripts/options.py`), in three layers: the catalog's defaults, your own file, a project file.
- The injector (`scripts/inject_stagecraft.py`) that adds the include file to an existing page and replaces the older header of the parley skill when a page carries one.
- The optional publish check (`hooks/stagecraft_gate.py`): reminds or refuses, as `check.mode` and `method.tab` say.
- References for layout, components and publishing, a demo page on made-up data with a self-test that runs in a browser, and the seven-section Method tab skeleton.

Changed from the last internal draft (0.3.4), for the public release:

- The version is 0.4.0 in `SKILL.md`, the include file and the demo page.
- A README with install, the one command, the settings layers and the limits.
- Three small checks in `tests/`: the palette's contrast, the syntax of every inline script, and a smoke test that runs the scripts against an empty temporary home.
- The demo page and the include file no longer name a person, a session or a real page: the demo's sample link and session id are made up, and the test fixtures for link handling are written in two pieces.
- `SKILL.md` no longer points to the internal build log; the reference for every part is `references/components.md`.
- No setting's default changed.
