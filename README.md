<p align="center">
  <img src="assets/logo-wordmark.svg" alt="skillup" height="72" />
</p>

<p align="center">
  <strong>Skill your agents up.</strong><br/>
  A minimal CLI to install, version, and sync skills for your AI agents.<br/>
  Local-first · GitHub-backed · Works with Claude, Gemini, and more.
</p>

<p align="center">
  <code>pip install skillup</code> &nbsp;·&nbsp; <code>uv tool install skillup</code>
</p>

---

## Features

- **Interactive install** — pick skills from any GitHub repo release
- **Multi-repo** — manage skills from multiple sources independently
- **Lock file** — pins commit SHAs for reproducible installs (`~/.agents/skills.lock.json`)
- **Auto-update** — upgrade all or specific repos to their latest release or branch head
- **Smart cache** — skips redundant downloads; override with `SKILLUP_CACHE_DIR`
- **gh integration** — uses `gh` CLI when available, falls back to `requests`

## Installation

```bash
pip install skillup
# or
uv tool install skillup
```

## Usage

### Add skills

```bash
skillup add google/gemini-cli-skills
```

No releases? Falls back to `main` automatically. Pin a branch explicitly:

```bash
skillup add anthropics/skills --branch main --skill pdf
```

### Remove skills

```bash
skillup remove
```

### Update skills

```bash
skillup update                              # all repos
skillup update --repo google/gemini-cli-skills  # one repo
```

### Sync (restore from lock file)

```bash
skillup sync
```

Installs skills at the exact pinned SHAs from the lock file — useful for new machines.

### Migrate from NPX skills CLI

```bash
skillup migrate                       # reads skills-lock.json from repo root
skillup migrate path/to/skills-lock.json
```

## Skill definition

A folder is recognized as a skill when it lives inside a `skills/` directory at the repo root and contains a `SKILL.md` file.

## Development

```bash
uv sync          # install deps
uv run skillup --help
uv run pytest
uv run pyright skillup
```

## License

MIT
