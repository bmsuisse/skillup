<p align="center">
  <img src="assets/logo-wordmark.svg" alt="skillup" height="72" />
</p>

<p align="center">
  <strong>Skill your agents up.</strong><br/>
  A minimal CLI to install, version, and sync skills for your AI agents.<br/>
  Local-first · GitHub &amp; Azure DevOps · Works with Claude, Gemini, and more.
</p>

<p align="center">
  <code>uv tool install skillup</code>
</p>

---

## Features

- **Interactive install** — pick skills from any GitHub repo release
- **Multi-repo** — manage skills from multiple sources independently
- **Lock file** — pins commit SHAs for reproducible installs (`~/.agents/skills.lock.json`)
- **Auto-update** — upgrade all or specific repos to their latest release or branch head
- **Smart cache** — skips redundant downloads; override with `SKILLUP_CACHE_DIR`
- **gh integration** — uses `gh` CLI when available, falls back to `requests`
- **Azure DevOps** — install skills from private Azure DevOps Git repos via `DefaultAzureCredential` or a PAT

## Installation

```bash
uv tool install skillup
```

To use Azure DevOps sources, install the `azure` extra:

```bash
uv tool install 'skillup[azure]'
```

## Usage

### Add skills from GitHub

```bash
skillup add google/gemini-cli-skills
```

No releases? Falls back to `main` automatically. Pin a branch or add specific skills non-interactively:

```bash
skillup add anthropics/skills --branch main --skill pdf
```

Full GitHub URLs are also accepted:

```bash
skillup add https://github.com/anthropics/skills
```

### Add skills from Azure DevOps

Pass the full Azure DevOps clone URL — the provider is detected automatically from the domain:

```bash
skillup add https://dev.azure.com/myorg/myproject/_git/myrepo
skillup add https://myorg.visualstudio.com/myproject/_git/myrepo   # legacy URL format

# pin a branch or add specific skills non-interactively
skillup add https://dev.azure.com/myorg/myproject/_git/myrepo --branch develop --skill my-skill
```

Azure DevOps repos are stored in the lock file under the key `azdo:org/project/repo` and participate in the shared `update` and `sync` commands just like GitHub repos.

#### Authentication

Authentication is resolved in this order:

1. **`AZURE_DEVOPS_TOKEN` env var** — a Personal Access Token (PAT) with *Code → Read* scope, or any valid bearer token.
2. **`DefaultAzureCredential`** (requires the `azure` extra) — tries, in order: environment variables (`AZURE_CLIENT_ID` / `AZURE_CLIENT_SECRET` / `AZURE_TENANT_ID`), workload identity, managed identity, Azure CLI (`az login`), Azure Developer CLI, and interactive browser login.

The recommended approach for developer machines is `DefaultAzureCredential` via `az login`:

```bash
uv tool install 'skillup[azure]'
az login
skillup add https://dev.azure.com/myorg/myproject/_git/myrepo
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
