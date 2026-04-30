# Changelog

## Unreleased

- Added Zensical documentation site
- Added brand assets (`assets/logo.svg`, `assets/logo-wordmark.svg`)

## v0.4.1

- Renamed CLI from `bms-skills` to `skillup`
- Added `migrate` command to import `skills-lock.json` from the NPX skills CLI
- Fixed `migrate` default input path to repo root
- Refactored `cli.py` into focused modules (`install`, `lock`, `settings`, `github`)
