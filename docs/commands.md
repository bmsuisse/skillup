# Commands

## Global options

All commands accept these options before the subcommand name:

| Option | Short | Description |
|--------|-------|-------------|
| `--global` | `-g` | Use home directory instead of current working directory. |
| `--lock-file PATH` | `-l` | Use a custom lock file path instead of the default. |

```bash
skillup --global add myorg/skills
skillup --lock-file /path/to/my.lock.json sync
```

---

## `config`

Manage skillup configuration. Settings are persisted in the lock file.

### `config set-dirs`

Set the target directories where skills are installed.

```bash
skillup config set-dirs <DIR> [DIR...]
```

**Examples**

```bash
# Replace the two defaults with a single custom directory
skillup config set-dirs /home/user/my-skills

# Use custom paths for both agent frameworks
skillup config set-dirs .agents/skills .vscode/skills
```

**Behavior**

- Accepts one or more directory paths (space-separated).
- Paths can be absolute or relative (resolved from the current working directory).
- Saves the directories to the `config.target_dirs` key in the lock file.
- All subsequent commands (`add`, `remove`, `update`, `sync`) install to and remove from these directories.

### `config show`

Display the current configuration.

```bash
skillup config show
```

Shows the active lock file path and target directories, including whether each was read from the lock file or is the built-in default.

---

## `add`

Add skills from a GitHub release or branch.

```bash
skillup add <owner/repo> [OPTIONS]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--skill TEXT` | `-s` | Skill name to add (repeatable). Skips interactive picker. |
| `--branch TEXT` | `-b` | Install from this branch instead of the latest release. |

**Examples**

```bash
# Interactive picker — choose from all available skills
skillup add google/gemini-cli-skills

# Add one skill non-interactively
skillup add anthropics/skills --skill pdf

# Add multiple skills at once
skillup add anthropics/skills --skill pdf --skill code-review

# Pin to a branch
skillup add myorg/skills --branch main
```

**Behavior**

- Fetches the latest GitHub release. If none exists, falls back to `main`.
- Downloads the release zip (cached in `TEMP`/`/tmp` or `SKILLUP_CACHE_DIR`).
- Installs selected skills to `~/.agents/skills` and `~/.claude/skills`.
- Writes the resolved tag/commit to the lock file.

---

## `remove`

Interactively remove installed skills.

```bash
skillup remove
```

Shows a checkbox list of all installed skills across all tracked repos. Selected skills are deleted from disk and removed from the lock file. Repos with no remaining skills are dropped from the lock file entirely.

---

## `update`

Update installed skills to the latest release or branch head.

```bash
skillup update [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--repo TEXT` | Update only this repository (`owner/repo`). |

**Examples**

```bash
# Update everything
skillup update

# Update one repo
skillup update --repo google/gemini-cli-skills
```

**Behavior**

- Resolves the current latest source for each repo (release or branch head).
- If the resolved commit/tag matches what's in the lock file, skips with "already up-to-date".
- Re-installs all skills from the new source and updates the lock file.

---

## `sync`

Install all skills exactly as defined in the lock file.

```bash
skillup sync
```

Uses the pinned commit SHAs from the lock file — no network resolution of "latest". Useful for:

- Setting up a new machine from a shared or committed lock file.
- CI environments that need deterministic installs.

---

## `migrate`

Import a `skills-lock.json` from the Claude Code NPX skills CLI.

```bash
skillup migrate [INPUT_FILE]
```

| Argument | Description |
|----------|-------------|
| `INPUT_FILE` | Path to `skills-lock.json`. Defaults to `<base_dir>/skills-lock.json`. |

**Example**

```bash
# Default path
skillup migrate

# Custom path
skillup migrate path/to/skills-lock.json
```

**Behavior**

- Reads each GitHub-sourced skill from the input file.
- Resolves the current latest release/branch for each repo.
- Merges into the skillup lock file without overwriting existing entries.
- Skips skills with unsupported `sourceType` (non-GitHub).
