# Public diary

A repo to manage deployment of my obsidian notes to github pages.

## Commands

- All commands should be run through `makefiles`.
- `Makefile` in the root of the repository should be minimal.
- Helper makefile are in ./dev/makefiles/

## Hosting

- The obsidian vault is stored in google drive. It can be downloaded with using `rsync` by running `make quartz-stage`
- The obsidian vault is converted to html using the quartz static site generator. Generate the pages with `make quartz-build`

## Coding

- Tools and scripts should be written in `Python` under `./dev/scripts/`.
- Python tests should live alongside the Python package under `./dev/scripts/public_diary_tools/tests/`.
- Code must be linted with `ruff` the `make lint` command on change.
- Code must be tested with `make pytests`.
