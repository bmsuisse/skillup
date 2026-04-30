# Skill Definition

A **skill** is a folder that an AI agent can load to gain new capabilities. skillup installs these folders from GitHub repositories onto your local machine.

## What makes a valid skill

A folder is recognized as a skill when it meets **both** conditions:

1. It lives inside a `skills/` directory at the root of the GitHub repository.
2. It contains a `SKILL.md` file.

```
my-skills-repo/
└── skills/
    ├── code-review/       ← valid skill
    │   └── SKILL.md
    ├── pdf/               ← valid skill
    │   ├── SKILL.md
    │   └── tool.py
    └── draft/             ← NOT a skill (no SKILL.md)
        └── notes.txt
```

## Where skills are installed

skillup copies each selected skill folder to two locations:

| Path | Used by |
|------|---------|
| `~/.agents/skills/<skill-name>/` | Generic agent runtimes |
| `~/.claude/skills/<skill-name>/` | Claude Code |

Both locations are always populated — no configuration required.

## Publishing skills

To make your own skills installable via skillup:

1. Create a `skills/` directory at your repo root.
2. Add one sub-folder per skill, each containing at least a `SKILL.md`.
3. Cut a GitHub release (or let users install from a branch with `--branch`).

skillup will discover all valid skill folders from the release zip automatically.
