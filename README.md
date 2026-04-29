# bms-skills-cli

A minimal, user-friendly Python CLI to manage agent skills from GitHub releases. It installs skills to both `~/.agents/skills` and `~/.claude/skills` for seamless integration across platforms.

## Features

-   **Interactive Installation:** Select specific skills to add from any GitHub repository.
-   **Multi-Repo Support:** Manage skills from multiple repositories independently.
-   **Lock File State:** Tracks installed versions (release tags) and skills in `~/.agents/skills.lock.json` for reproducibility.
-   **Automated Updates:** Easily upgrade all or specific repositories to their latest GitHub release.
-   **Smart Caching:** Downloads are cached in `~/.agents/cache` to avoid redundant network usage.
-   **GitHub CLI Integration:** Uses the `gh` tool for fast downloads if available, with a reliable `requests` fallback.

## Installation

Install using `pip` or `uv`:

```bash
pip install bms-skills-cli
# or
uv tool install bms-skills-cli
```

## Usage

### 1. Add Skills
Interactively select skills to add from a GitHub repository's latest release:

```bash
bms-skills add google/gemini-cli-skills
```

### 2. Remove Skills
Interactively select installed skills to remove from your system:

```bash
bms-skills remove
```

### 3. Update Skills
Update all installed skills to their latest versions:

```bash
bms-skills update
```

Or update a specific repository:

```bash
bms-skills update --repo google/gemini-cli-skills
```

## Skill Definition
A folder is recognized as a valid skill if it resides within a `skills/` directory at the repository root and contains a `SKILL.md` file.

## Development

This project uses [uv](https://github.com/astral-sh/uv) for dependency management.

```bash
# Install dependencies
uv sync

# Run locally
uv run bms-skills --help

# Run tests
uv run pytest

# Type check
uv run pyright bms_skills
```

## License
MIT
