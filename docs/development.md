# Development

## Setup

This project uses [uv](https://github.com/astral-sh/uv) for dependency management.

```bash
git clone https://github.com/bmsuisse/skillup
cd skillup
uv sync
```

## Running locally

```bash
uv run skillup --help
```

## Tests

```bash
uv run pytest
```

Run a specific test file:

```bash
uv run pytest tests/test_cli.py
```

## Type checking

```bash
uv run pyright skillup
```

## Project structure

```
skillup/
├── skillup/
│   ├── cli.py        # Typer commands (add, remove, update, sync, migrate)
│   ├── install.py    # Download, unzip, and copy skill folders
│   ├── lock.py       # Lock file read/write and source normalization
│   ├── settings.py   # Paths and environment config
│   └── github.py     # GitHub release/branch resolution
├── tests/
├── docs/             # This documentation (built with Zensical)
├── zensical.toml     # Docs config
└── pyproject.toml
```

## Building the docs locally

```bash
pip install zensical
zensical serve       # live-reload dev server
zensical build       # static output → site/
```

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SKILLUP_CACHE_DIR` | system temp | Override the download cache directory. |
