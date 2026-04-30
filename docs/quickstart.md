# Quick Start

## 1. Install skillup

=== "pip"

    ```bash
    pip install skillup
    ```

=== "uv"

    ```bash
    uv tool install skillup
    ```

## 2. Add your first skills

Point skillup at any GitHub repo that publishes skills:

```bash
skillup add google/gemini-cli-skills
```

An interactive checkbox picker appears — select the skills you want and press Enter. skillup downloads the release, installs each skill, and writes the result to your lock file.

??? note "No releases? Falls back to main automatically."
    If the repo has no GitHub releases, skillup fetches from the `main` branch instead. You can also pin a branch explicitly:

    ```bash
    skillup add myorg/my-skills --branch dev
    ```

## 3. Install a specific skill non-interactively

Skip the picker by naming skills directly:

```bash
skillup add anthropics/skills --skill pdf --skill code-review
```

## 4. Keep skills up to date

```bash
skillup update
```

Updates all tracked repos to their latest release or branch head.

## 5. Reproduce your setup on another machine

Commit or copy your lock file (`~/.agents/skills.lock.json`), then run:

```bash
skillup sync
```

Installs every skill at the exact pinned commit SHA recorded in the lock file.

---

## Where skills land

After installation, each skill folder is placed in both:

- `~/.agents/skills/<skill-name>/`
- `~/.claude/skills/<skill-name>/`

Both directories are populated automatically — no extra configuration needed.

---

## Next steps

- [All commands →](commands.md)
- [What makes a valid skill →](skill-definition.md)
- [Lock file format →](lock-file.md)
