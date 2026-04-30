# skillup

**Install, version, and sync skills for your AI agents.**

Give Claude, Gemini, or any agent new capabilities in seconds — pull from any GitHub repo, pin exact versions, and reproduce your setup on any machine.

[Get started](quickstart.md){ .md-button .md-button--primary } [GitHub](https://github.com/bmsuisse/skillup){ .md-button }

---

## Install

=== "pip"

    ```bash
    pip install skillup
    ```

=== "uv"

    ```bash
    uv tool install skillup
    ```

---

## What it does

```bash
# Add skills from a GitHub release — interactive picker
skillup add google/gemini-cli-skills

# Or pin a specific skill from a branch
skillup add anthropics/skills --branch main --skill pdf

# Keep everything up to date
skillup update

# Restore an exact setup on a new machine
skillup sync
```

---

## Features

**Interactive selection** — checkbox picker shows available skills; select what you need, skip the rest.

**Multi-repo** — track skills from as many GitHub repos as you like, each independently versioned.

**Reproducible lock file** — `~/.agents/skills.lock.json` pins every repo to a release tag or commit SHA so `skillup sync` reproduces your exact setup anywhere.

**Works everywhere** — installs to both `~/.agents/skills` and `~/.claude/skills` for seamless integration across platforms.

**Smart cache** — downloads are cached to avoid redundant network requests. Override with `SKILLUP_CACHE_DIR`.

**gh integration** — uses the `gh` CLI for fast authenticated downloads when available, with a `requests` fallback.

**Migration path** — import an existing `skills-lock.json` from the Claude Code NPX skills CLI with one command.
