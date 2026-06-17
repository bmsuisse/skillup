# Lock File

skillup tracks installed skills in a lock file at:

```
~/.agents/skills.lock.json
```

## Format

```json
{
  "config": {
    "target_dirs": ["/custom/agents/skills", "/custom/claude/skills"]
  },
  "repos": {
    "google/gemini-cli-skills": {
      "skills": ["code-review", "pdf"],
      "source": "release",
      "tag": "v1.2.0",
      "commit": "a3f8c21d..."
    },
    "myorg/custom-skills": {
      "skills": ["my-tool"],
      "source": "branch",
      "branch": "main",
      "commit": "b9e1d04f..."
    }
  }
}
```

The `config` section is optional and only written when you change settings from their defaults via `skillup config set-dirs`.

## Fields — `config`

| Field | Description |
|-------|-------------|
| `config.target_dirs` | List of directories where skills are installed. Omitted when using the built-in defaults. |

## Fields — `repos`

| Field | Description |
|-------|-------------|
| `skills` | List of installed skill names from this repo. |
| `source` | `"release"` or `"branch"` — how the skills were fetched. |
| `tag` | Release tag (present when `source` is `"release"`). |
| `branch` | Branch name (present when `source` is `"branch"`). |
| `commit` | Exact commit SHA. Used by `skillup sync` for deterministic installs. |

## Sharing the lock file

Commit your lock file to get reproducible setups across machines:

```bash
# On a new machine
cp path/to/skills.lock.json ~/.agents/skills.lock.json
skillup sync
```

`skillup sync` reads the pinned commit SHAs and installs every skill exactly — no "latest" resolution, no surprises.

## Location override

The `--global` / `-g` flag switches the base directory (and therefore the lock file location) to your home directory. Without it, skillup uses the current working directory.

For full control over the lock file path, use `--lock-file` / `-l`:

```bash
skillup --lock-file /shared/team.lock.json sync
```
