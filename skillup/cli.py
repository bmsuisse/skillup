import json
import shutil
from importlib.metadata import version as pkg_version
from pathlib import Path
from typing import Any, List, Literal, Optional
from urllib.parse import urlparse

import questionary
import requests
import typer
from rich.console import Console

from .github import get_repo_source, parse_github_repo
from .install import download_release, ensure_dirs, get_skill_paths, install_skill
from .local import get_skill_paths_local, install_skill_local, is_local_path, resolve_local_path
from .lock import apply_source, get_sync_source, load_lock, normalize_repo_data, save_lock
from .settings import RepoSource, format_source_label, settings
from ._tree_ui import tree_checkbox

app = typer.Typer(help="Minimal CLI to manage agent skills from GitHub releases or branches.")
console = Console()


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(pkg_version("skillup"))
        raise typer.Exit()


def _detect_provider(repo_or_url: str) -> Literal["local", "azdevops", "github"]:
    """Return 'local', 'azdevops', or 'github' based on the input format."""
    if is_local_path(repo_or_url):
        return "local"
    parsed = urlparse(repo_or_url)
    if not parsed.scheme:
        return "github"
    host = parsed.netloc.split("@")[-1]
    if host == "dev.azure.com" or host.endswith(".visualstudio.com"):
        return "azdevops"
    return "github"


def _parse_repo_input(repo_or_url: str) -> tuple[str, str]:
    """Return (lock_key, short_ref) for a GitHub or Azure DevOps repo input.

    For GitHub: lock_key == short_ref == 'owner/repo'.
    For Azure DevOps: lock_key == 'azdo:org/project/repo', short_ref == 'org/project/repo'.
    """
    provider = _detect_provider(repo_or_url)
    if provider == "azdevops":
        from .azdevops import parse_azdevops_repo

        short_ref = parse_azdevops_repo(repo_or_url)
        return f"azdo:{short_ref}", short_ref
    short_ref = parse_github_repo(repo_or_url)
    return short_ref, short_ref


def _resolve_source(lock_key: str, short_ref: str, branch: Optional[str] = None) -> RepoSource:
    if lock_key.startswith("azdo:"):
        from .azdevops import get_azdevops_repo_source

        return get_azdevops_repo_source(short_ref, branch)
    return get_repo_source(short_ref, branch)


def _download(lock_key: str, source: RepoSource) -> Path:
    if source.provider == "azdevops":
        from .azdevops import get_azdevops_headers

        return download_release(lock_key, source.cache_key, source.zip_url, get_azdevops_headers())
    return download_release(lock_key, source.cache_key, source.zip_url)


@app.callback()
def main(
    is_global: bool = typer.Option(False, "--global", "-g", help="Use home directory instead of current directory"),
    lock_file: Optional[Path] = typer.Option(None, "--lock-file", "-l", help="Path to lock file (overrides default location)"),
    version: Optional[bool] = typer.Option(None, "--version", "-V", callback=_version_callback, is_eager=True, help="Show version and exit."),
):
    """Minimal CLI to manage agent skills from GitHub releases or branches."""
    settings.is_global = is_global
    if lock_file is not None:
        settings.lock_file_override = lock_file


config_app = typer.Typer(help="Manage skillup configuration.")
app.add_typer(config_app, name="config")


@config_app.command("set-dirs")
def config_set_dirs(
    dirs: List[str] = typer.Argument(..., help="Target directories for skill installation (space-separated)"),
):
    """Set the target directories where skills are installed. Persisted in the lock file."""
    lock = load_lock()
    settings.target_dirs_override = [Path(d) for d in dirs]
    save_lock(lock)
    console.print("[green]Target directories updated:[/green]")
    for d in settings.target_dirs_override:
        console.print(f"  {d}")


@config_app.command("show")
def config_show():
    """Show current skillup configuration."""
    lock = load_lock()
    console.print(f"Lock file:    [cyan]{settings.lock_file}[/cyan]")
    console.print("Target dirs:")
    source = " [dim](from lock file)[/dim]" if lock.get("config", {}).get("target_dirs") else " [dim](default)[/dim]"
    for d in settings.target_dirs:
        console.print(f"  {d}{source}")


@app.command()
def add(
    repo: str = typer.Argument(
        ...,
        help=(
            "GitHub 'owner/repo', a full GitHub URL, a full Azure DevOps URL "
            "(https://dev.azure.com/… or https://org.visualstudio.com/…), "
            "or a local path (/path/to/repo, C:\\path\\to\\repo, or file:///path)."
        ),
    ),
    skills: Optional[List[str]] = typer.Option(None, "--skill", "-s", help="Specific skill(s) to add (non-interactive)"),
    branch: Optional[str] = typer.Option(None, "--branch", "-b", help="Branch to install from instead of the latest release"),
    search: Optional[str] = typer.Option(None, "--search", "-f", help="Filter skills shown in the tree (matches skill name or path, case-insensitive)"),
    all_skills: bool = typer.Option(False, "--all-skills", help="Install all available skills non-interactively"),
):
    """Add skills from a GitHub repository, Azure DevOps repository, or local path."""
    lock = load_lock()
    ensure_dirs()

    if is_local_path(repo):
        _add_local(repo, lock, skills, search, all_skills)
        return

    lock_key, short_ref = _parse_repo_input(repo)

    try:
        source = _resolve_source(lock_key, short_ref, branch)
    except Exception as e:
        console.print(f"[red]Error fetching source info for {short_ref}:[/red] {e}")
        raise typer.Exit(1)

    try:
        zip_path = _download(lock_key, source)
    except requests.HTTPError as e:
        console.print(f"[red]HTTP error downloading {short_ref}:[/red] {e}")
        print(e.response.text)
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error downloading {short_ref}:[/red] {e}")
        raise typer.Exit(1)

    skill_paths = get_skill_paths(zip_path)
    available_skills = sorted(skill_paths.keys())
    repo_data = normalize_repo_data(lock["repos"].get(lock_key, {"skills": []}))
    installed_skills = set(repo_data["skills"])

    if all_skills:
        selected = [s for s in available_skills if s not in installed_skills]
        if not selected:
            console.print(f"[yellow]No new skills available to add from {short_ref}.[/yellow]")
            return
    elif skills:
        selected = [s for s in skills if s in available_skills and s not in installed_skills]
        invalid = [s for s in skills if s not in available_skills]
        already_installed = [s for s in skills if s in installed_skills]

        if invalid:
            console.print(f"[yellow]Warning: Skills not found in {short_ref}: {', '.join(invalid)}[/yellow]")
        if already_installed:
            console.print(f"[blue]Note: Skills already installed from {short_ref}: {', '.join(already_installed)}[/blue]")
    else:
        available_paths = {k: v for k, v in skill_paths.items() if k not in installed_skills}

        if search:
            needle = search.casefold()
            available_paths = {k: v for k, v in available_paths.items() if needle in k.casefold() or needle in v.casefold()}
            if not available_paths:
                console.print(f"[yellow]No skills matching '{search}' found in {short_ref}.[/yellow]")
                return

        if not available_paths:
            console.print(f"[yellow]No new skills available to add from {short_ref}.[/yellow]")
            return

        prompt = f"Select skills to add from {short_ref}:"
        if search:
            prompt += f"  [filter: '{search}']"
        selected = tree_checkbox(prompt, available_paths)

    if not selected:
        console.print("No skills selected or available for installation.")
        return

    for skill in selected:
        console.print(f"Installing [cyan]{skill}[/cyan]...")
        install_skill(skill, zip_path)
        if skill not in repo_data["skills"]:
            repo_data["skills"].append(skill)

    repo_data = apply_source(repo_data, source)
    lock["repos"][lock_key] = repo_data
    save_lock(lock)
    console.print(f"[green]Skills from {short_ref} installed successfully![/green]")


def _add_local(repo: str, lock: dict, skills: Optional[List[str]], search: Optional[str], all_skills: bool = False) -> None:
    local_path = resolve_local_path(repo)
    if not local_path.is_dir():
        console.print(f"[red]Local path does not exist or is not a directory: {local_path}[/red]")
        raise typer.Exit(1)

    lock_key = f"local:{local_path}"
    display = str(local_path)
    skill_paths = get_skill_paths_local(local_path)
    available_skills = sorted(skill_paths.keys())
    repo_data = lock["repos"].get(lock_key, {"skills": [], "source": "local", "path": str(local_path)})
    installed_skills = set(repo_data.get("skills", []))

    if all_skills:
        selected = [s for s in available_skills if s not in installed_skills]
        if not selected:
            console.print(f"[yellow]No new skills available to add from {display}.[/yellow]")
            return
    elif skills:
        selected = [s for s in skills if s in available_skills and s not in installed_skills]
        invalid = [s for s in skills if s not in available_skills]
        already_installed = [s for s in skills if s in installed_skills]

        if invalid:
            console.print(f"[yellow]Warning: Skills not found in {display}: {', '.join(invalid)}[/yellow]")
        if already_installed:
            console.print(f"[blue]Note: Skills already installed from {display}: {', '.join(already_installed)}[/blue]")
    else:
        available_paths = {k: v for k, v in skill_paths.items() if k not in installed_skills}

        if search:
            needle = search.casefold()
            available_paths = {k: v for k, v in available_paths.items() if needle in k.casefold() or needle in v.casefold()}
            if not available_paths:
                console.print(f"[yellow]No skills matching '{search}' found in {display}.[/yellow]")
                return

        if not available_paths:
            console.print(f"[yellow]No new skills available to add from {display}.[/yellow]")
            return

        prompt = f"Select skills to add from {display}:"
        if search:
            prompt += f"  [filter: '{search}']"
        selected = tree_checkbox(prompt, available_paths)

    if not selected:
        console.print("No skills selected or available for installation.")
        return

    for skill in selected:
        console.print(f"Installing [cyan]{skill}[/cyan]...")
        install_skill_local(skill, local_path)
        if skill not in repo_data["skills"]:
            repo_data["skills"].append(skill)

    repo_data["source"] = "local"
    repo_data["path"] = str(local_path)
    lock["repos"][lock_key] = repo_data
    save_lock(lock)
    console.print(f"[green]Skills from {display} installed successfully![/green]")


@app.command()
def remove():
    """Interactively remove installed skills across all repositories."""
    lock = load_lock()

    all_installed = []
    for repo, data in lock["repos"].items():
        for skill in data["skills"]:
            all_installed.append(f"{repo}: {skill}")

    if not all_installed:
        console.print("[yellow]No skills installed.[/yellow]")
        return

    selected = questionary.checkbox(
        "Select skills to remove:",
        choices=all_installed,
    ).ask()

    if not selected:
        console.print("No skills selected.")
        return

    for item in selected:
        repo, skill = item.split(": ", 1)
        console.print(f"Removing [red]{skill}[/red] from {repo}...")
        for target_dir in settings.target_dirs:
            dest = target_dir / skill
            if dest.exists():
                shutil.rmtree(dest)

        lock["repos"][repo]["skills"].remove(skill)
        if not lock["repos"][repo]["skills"]:
            del lock["repos"][repo]

    save_lock(lock)
    console.print("[green]Skills removed successfully![/green]")


@app.command()
def update(repo: Optional[str] = typer.Option(None, "--repo", help="Specific repository to update (lock-file key)")):
    """Update installed skills to the latest tracked release or branch commit."""
    lock = load_lock()
    repos_to_update = [repo] if repo else list(lock["repos"].keys())

    if not repos_to_update:
        console.print("[yellow]No skills installed to update.[/yellow]")
        return

    for r in repos_to_update:
        if r not in lock["repos"]:
            if repo:
                console.print(f"[red]Repository {r} is not tracked.[/red]")
            continue

        if r.startswith("local:"):
            console.print(f"[dim]Skipping local path {r[6:]} (no remote to update from).[/dim]")
            continue

        repo_data = normalize_repo_data(lock["repos"][r])
        short_ref = r[5:] if r.startswith("azdo:") else r
        console.print(f"Checking updates for [cyan]{short_ref}[/cyan]...")

        try:
            tracked_branch = repo_data.get("branch") if repo_data.get("source") == "branch" else None
            source = _resolve_source(r, short_ref, tracked_branch)
        except Exception as e:
            console.print(f"[red]Error fetching source info for {short_ref}:[/red] {e}")
            continue

        current_version = repo_data.get("commit") or repo_data.get("tag") or repo_data.get("branch")
        new_version = source.commit or source.ref
        if current_version == new_version:
            console.print(f"  [green]{short_ref} is already up-to-date ({format_source_label(source)}).[/green]")
            continue

        previous_label = repo_data.get("tag") or repo_data.get("branch") or repo_data.get("commit", "unknown")
        next_label = format_source_label(source)
        console.print(f"  Updating from {previous_label} to [cyan]{next_label}[/cyan]...", highlight=False)
        zip_path = _download(r, source)

        for skill in repo_data["skills"]:
            console.print(f"  Updating [cyan]{skill}[/cyan]...")
            install_skill(skill, zip_path)

        repo_data = apply_source(repo_data, source)
        lock["repos"][r] = repo_data
        save_lock(lock)
        console.print(f"  [green]Successfully updated {short_ref} to {next_label}![/green]")


@app.command()
def sync():
    """Install all skills as defined in the lock file."""
    lock = load_lock()
    ensure_dirs()

    if not lock["repos"]:
        console.print("[yellow]No skills defined in lock file. Use 'add' to add skills.[/yellow]")
        return

    for repo, repo_data in lock["repos"].items():
        skills = repo_data["skills"]

        if repo.startswith("local:"):
            local_path = Path(repo_data.get("path", repo[6:]))
            console.print(f"Syncing [cyan]{local_path}[/cyan] (local)...")
            if not local_path.is_dir():
                console.print(f"[red]  Local path not found: {local_path}[/red]")
                continue
            for skill in skills:
                console.print(f"  Installing [cyan]{skill}[/cyan]...")
                install_skill_local(skill, local_path)
            continue

        source = get_sync_source(repo, repo_data)
        short_ref = repo[5:] if repo.startswith("azdo:") else repo
        console.print(f"Syncing [cyan]{short_ref}[/cyan] at [green]{format_source_label(source)}[/green]...")

        try:
            zip_path = _download(repo, source)
            for skill in skills:
                console.print(f"  Installing [cyan]{skill}[/cyan]...")
                install_skill(skill, zip_path)
        except Exception as e:
            console.print(f"[red]Error syncing {short_ref}:[/red] {e}")
            continue

    console.print("[green]Synchronization complete![/green]")


@app.command()
def migrate(
    input_file: Optional[Path] = typer.Argument(None, help="Path to skills-lock.json (defaults to .claude/skills-lock.json)"),
):
    """Migrate a Claude Code skills-lock.json to the skillup lock format."""
    resolved = input_file if input_file is not None else settings.base_dir / "skills-lock.json"

    if not resolved.exists():
        console.print(f"[red]File not found: {resolved}[/red]")
        raise typer.Exit(1)

    try:
        data = json.loads(resolved.read_text())
    except Exception as e:
        console.print(f"[red]Failed to parse {resolved}:[/red] {e}")
        raise typer.Exit(1)

    skills_map: dict[str, Any] = data.get("skills", {})
    if not skills_map:
        console.print("[yellow]No skills found in the input file.[/yellow]")
        return

    repos: dict[str, list[str]] = {}
    for skill_name, skill_data in skills_map.items():
        if skill_data.get("sourceType") != "github":
            console.print(f"[yellow]Skipping {skill_name}: unsupported sourceType '{skill_data.get('sourceType')}'[/yellow]")
            continue
        repo = skill_data["source"]
        repos.setdefault(repo, []).append(skill_name)

    if not repos:
        console.print("[yellow]No GitHub skills found to migrate.[/yellow]")
        return

    lock = load_lock()

    for repo, skill_names in repos.items():
        console.print(f"Resolving [cyan]{repo}[/cyan]...")
        try:
            source = get_repo_source(repo)
        except Exception as e:
            console.print(f"[red]Error fetching source info for {repo}:[/red] {e}")
            continue

        repo_data = lock["repos"].get(repo, {"skills": []})
        existing = set(repo_data.get("skills", []))
        for skill in skill_names:
            if skill not in existing:
                repo_data.setdefault("skills", []).append(skill)

        repo_data = apply_source(repo_data, source)
        lock["repos"][repo] = repo_data
        console.print(f"  [green]Migrated {len(skill_names)} skill(s) at {format_source_label(source)}[/green]")

    ensure_dirs()
    save_lock(lock)
    console.print(f"[green]Migration complete! Lock file saved to {settings.lock_file}[/green]")


if __name__ == "__main__":
    app()
